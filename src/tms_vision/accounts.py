"""Comptes, connexions et journal (phase 1 du chantier « comptes, validation et fiches »).

- `users` : un compte par personne, avec un ou plusieurs rôles (praticien, ostéopathe,
  administrateur). Mot de passe haché avec Argon2id, jamais stocké ni journalisé.
- `sessions` : une ligne par connexion ouverte ; seule l'empreinte (SHA-256) du jeton est en base,
  le jeton lui-même ne vit que dans le cookie du navigateur.
- `login_failures` : échecs de connexion, pour ralentir les tentatives répétées (par compte et par
  adresse).
- `audit_log` : journal des connexions, échecs, créations et changements de droits.

Les identifiants sont des UUID, pour rester compatibles avec un futur échange entre cabinets.
Chaque fonction ouvre sa propre connexion à la base de `storage.DB_PATH`, comme le reste de la
persistance."""
import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import duckdb
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from tms_vision import storage

ROLES = ("praticien", "osteopathe", "administrateur")
LANGUAGES = ("fr", "en")

MIN_PASSWORD_LENGTH = 12
# Durée d'une session : glissante (prolongée à l'usage) mais plafonnée en absolu.
SESSION_IDLE_HOURS = 12
SESSION_MAX_DAYS = 30
# Ralentissement des tentatives : au-delà de ces échecs récents, on impose une attente qui double.
FAILURE_WINDOW_MINUTES = 15
ACCOUNT_FREE_ATTEMPTS = 5
ADDRESS_FREE_ATTEMPTS = 20
MAX_DELAY_SECONDS = 15 * 60

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Mots de passe courants refusés quelle que soit leur longueur (liste volontairement courte : elle
# écarte les pires choix, elle ne remplace pas un vrai dictionnaire).
COMMON_PASSWORDS = frozenset(
    {
        "motdepasse123", "motdepasse1234", "azertyuiop12", "azertyazerty", "azerty123456",
        "password1234", "password12345", "passwordpassword", "123456789012", "1234567890123",
        "qwertyuiop12", "qwertyqwerty", "iloveyou1234", "administrateur", "administrator",
        "tmsvision1234", "changeme1234", "bienvenue1234", "letmein123456",
    }
)

_hasher = PasswordHasher()
# Haché factice : vérifié quand le compte n'existe pas, pour que la durée de la réponse ne révèle
# pas si une adresse est inscrite.
_DUMMY_HASH = _hasher.hash("mot de passe factice, jamais utilisé")

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR NOT NULL UNIQUE,
    name VARCHAR NOT NULL,
    password_hash VARCHAR NOT NULL,
    roles VARCHAR NOT NULL,
    language VARCHAR,
    active BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL,
    password_changed_at TIMESTAMP NOT NULL
)
"""

CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP
)
"""

CREATE_LOGIN_FAILURES_TABLE = """
CREATE TABLE IF NOT EXISTS login_failures (
    account VARCHAR NOT NULL,
    address VARCHAR NOT NULL,
    attempted_at TIMESTAMP NOT NULL
)
"""

CREATE_AUDIT_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id VARCHAR PRIMARY KEY,
    logged_at TIMESTAMP NOT NULL,
    user_id VARCHAR,
    email VARCHAR,
    action VARCHAR NOT NULL,
    target VARCHAR,
    detail VARCHAR,
    address VARCHAR
)
"""


class AccountError(ValueError):
    """Demande refusée ; `code` est stable (pour le site), le message est en français."""

    def __init__(self, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _connect() -> "duckdb.DuckDBPyConnection":
    storage.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(storage.DB_PATH))
    conn.execute(CREATE_USERS_TABLE)
    conn.execute(CREATE_SESSIONS_TABLE)
    conn.execute(CREATE_LOGIN_FAILURES_TABLE)
    conn.execute(CREATE_AUDIT_LOG_TABLE)
    return conn


def normalize_email(email: str) -> str:
    cleaned = (email or "").strip().lower()
    if len(cleaned) > 254 or not _EMAIL_PATTERN.match(cleaned):
        raise AccountError("invalid_email", "Adresse email invalide.")
    return cleaned


def check_password_strength(password: str, email: str = "") -> None:
    """Lève AccountError si le mot de passe est trop court, trop courant ou calqué sur l'email."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(
            "password_too_short",
            f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères.",
        )
    if len(password) > 256:
        raise AccountError("password_too_long", "Le mot de passe est trop long (256 caractères au plus).")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or len(set(lowered)) < 4:
        raise AccountError("password_too_common", "Ce mot de passe est trop courant : choisissez-en un autre.")
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) >= 4 and (lowered == email.lower() or lowered == local):
        raise AccountError("password_is_email", "Le mot de passe ne doit pas être l'adresse email.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _validate_roles(roles: list[str]) -> list[str]:
    unique = [role for role in ROLES if role in set(roles)]
    unknown = set(roles) - set(ROLES)
    if unknown or not unique:
        raise AccountError("invalid_roles", f"Rôles attendus parmi : {', '.join(ROLES)}.")
    return unique


def _public_user(row: tuple) -> dict:
    user_id, email, name, roles, language, active, created_at = row
    return {
        "id": user_id,
        "email": email,
        "name": name,
        "roles": json.loads(roles),
        "language": language,
        "active": bool(active),
        "created_at": created_at.isoformat() if created_at else None,
    }


_USER_COLUMNS = "id, email, name, roles, language, active, created_at"


def has_users() -> bool:
    conn = _connect()
    try:
        return conn.execute("SELECT count(*) FROM users").fetchone()[0] > 0
    finally:
        conn.close()


def audit(
    action: str,
    *,
    user_id: str | None = None,
    email: str | None = None,
    target: str | None = None,
    detail: str | None = None,
    address: str | None = None,
) -> None:
    """Ajoute une ligne au journal. Jamais de mot de passe ni de jeton dans `detail`."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO audit_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [str(uuid.uuid4()), _now(), user_id, email, action, target, detail, address],
        )
    finally:
        conn.close()


def list_audit(limit: int = 200) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT logged_at, user_id, email, action, target, detail, address FROM audit_log "
            "ORDER BY logged_at DESC, id LIMIT ?",
            [max(1, min(limit, 1000))],
        ).fetchall()
    finally:
        conn.close()
    keys = ("at", "user_id", "email", "action", "target", "detail", "address")
    return [{**dict(zip(keys, row)), "at": row[0].isoformat()} for row in rows]


def create_user(
    email: str,
    name: str,
    password: str,
    roles: list[str],
    *,
    language: str | None = None,
    actor: str | None = None,
) -> dict:
    email = normalize_email(email)
    name = (name or "").strip()
    if not name or len(name) > 120:
        raise AccountError("invalid_name", "Le nom est obligatoire (120 caractères au plus).")
    roles = _validate_roles(roles)
    if language is not None and language not in LANGUAGES:
        raise AccountError("invalid_language", f"Langue attendue parmi : {', '.join(LANGUAGES)}.")
    check_password_strength(password, email)
    user_id = str(uuid.uuid4())
    now = _now()
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", [email]).fetchone():
            raise AccountError("email_taken", "Un compte existe déjà avec cette adresse.")
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [user_id, email, name, hash_password(password), json.dumps(roles), language, True, now, now],
        )
        row = conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", [user_id]).fetchone()
    finally:
        conn.close()
    audit("user.create", user_id=actor, target=user_id, detail=",".join(roles))
    return _public_user(row)


def create_first_admin(email: str, name: str, password: str, *, language: str | None = None) -> dict:
    """Crée le tout premier compte (administrateur et praticien). Refuse s'il existe déjà un compte :
    réservé à l'écran de première utilisation de l'application de bureau."""
    if has_users():
        raise AccountError("setup_done", "Un compte existe déjà : connectez-vous.")
    user = create_user(email, name, password, ["praticien", "administrateur"], language=language)
    # Deux créations simultanées : si une autre est passée entre-temps, on retire celle-ci.
    if sum(1 for account in list_users() if "administrateur" in account["roles"]) > 1:
        conn = _connect()
        try:
            conn.execute("DELETE FROM users WHERE id = ?", [user["id"]])
        finally:
            conn.close()
        raise AccountError("setup_done", "Un compte existe déjà : connectez-vous.")
    audit("admin.create_setup", target=user["id"])
    return user


def get_user(user_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", [user_id]).fetchone()
    finally:
        conn.close()
    return _public_user(row) if row else None


def list_users() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(f"SELECT {_USER_COLUMNS} FROM users ORDER BY created_at, email").fetchall()
    finally:
        conn.close()
    return [_public_user(row) for row in rows]


def _active_admin_count(conn, excluding: str | None = None) -> int:
    count = 0
    for user_id, roles, active in conn.execute("SELECT id, roles, active FROM users").fetchall():
        if user_id != excluding and active and "administrateur" in json.loads(roles):
            count += 1
    return count


def update_user(
    user_id: str,
    *,
    roles: list[str] | None = None,
    active: bool | None = None,
    name: str | None = None,
    language: str | None = None,
    email: str | None = None,
    actor: str | None = None,
) -> dict:
    """Modifie un compte. Changer l'adresse (identifiant de connexion) ferme les sessions de ce
    compte, sauf si c'est la personne elle-même qui le fait (`actor` = le compte modifié)."""
    new_email = normalize_email(email) if email is not None else None
    conn = _connect()
    try:
        row = conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", [user_id]).fetchone()
        if not row:
            raise AccountError("not_found", "Compte introuvable.")
        current = _public_user(row)
        new_roles = _validate_roles(roles) if roles is not None else current["roles"]
        new_active = current["active"] if active is None else bool(active)
        # Garde-fou : on ne retire jamais le dernier administrateur actif.
        stays_admin = new_active and "administrateur" in new_roles
        if not stays_admin and "administrateur" in current["roles"] and current["active"]:
            if _active_admin_count(conn, excluding=user_id) == 0:
                raise AccountError("last_admin", "Il doit rester au moins un administrateur actif.")
        new_name = current["name"] if name is None else name.strip()
        if not new_name or len(new_name) > 120:
            raise AccountError("invalid_name", "Le nom est obligatoire (120 caractères au plus).")
        if language is not None and language not in LANGUAGES:
            raise AccountError("invalid_language", f"Langue attendue parmi : {', '.join(LANGUAGES)}.")
        new_language = current["language"] if language is None else language
        email_changed = new_email is not None and new_email != current["email"]
        if email_changed:
            if conn.execute("SELECT 1 FROM users WHERE email = ? AND id <> ?", [new_email, user_id]).fetchone():
                raise AccountError("email_taken", "Un compte existe déjà avec cette adresse.")
            conn.execute("UPDATE users SET email = ? WHERE id = ?", [new_email, user_id])
            if actor != user_id:
                conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                    [_now(), user_id],
                )
        conn.execute(
            "UPDATE users SET roles = ?, active = ?, name = ?, language = ? WHERE id = ?",
            [json.dumps(new_roles), new_active, new_name, new_language, user_id],
        )
        if not new_active:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                [_now(), user_id],
            )
        row = conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", [user_id]).fetchone()
    finally:
        conn.close()
    changes = []
    if new_roles != current["roles"]:
        changes.append("roles=" + ",".join(new_roles))
    if new_active != current["active"]:
        changes.append(f"active={new_active}")
    if email_changed:
        changes.append(f"email={current['email']}->{new_email}")
    audit("user.update", user_id=actor, target=user_id, detail=";".join(changes) or None)
    return _public_user(row)


# --- Connexion -------------------------------------------------------------------------------


def _delay_for(failures: int, free: int) -> int:
    if failures < free:
        return 0
    return min(MAX_DELAY_SECONDS, 2 ** (failures - free + 1))


def _throttle_wait(conn, account: str, address: str, now: datetime) -> int:
    """Secondes à attendre avant une nouvelle tentative (0 : autorisée)."""
    since = now - timedelta(minutes=FAILURE_WINDOW_MINUTES)
    wait = 0
    for column, value, free in (("account", account, ACCOUNT_FREE_ATTEMPTS), ("address", address, ADDRESS_FREE_ATTEMPTS)):
        count, last = conn.execute(
            f"SELECT count(*), max(attempted_at) FROM login_failures WHERE {column} = ? AND attempted_at >= ?",
            [value, since],
        ).fetchone()
        if count and last is not None:
            remaining = _delay_for(count, free) - (now - last).total_seconds()
            wait = max(wait, int(remaining) + 1 if remaining > 0 else 0)
    return wait


def authenticate(email: str, password: str, address: str = "") -> dict:
    """Vérifie l'identifiant et le mot de passe ; renvoie le compte. Lève AccountError sinon.

    Le message est le même pour un compte inconnu, désactivé ou un mauvais mot de passe."""
    account = (email or "").strip().lower()[:254]
    address = address or "-"
    now = _now()
    conn = _connect()
    try:
        wait = _throttle_wait(conn, account, address, now)
        if wait:
            audit("login.throttled", email=account, address=address)
            raise AccountError(
                "too_many_attempts", "Trop de tentatives : patientez avant de réessayer.", retry_after=wait
            )
        row = conn.execute(
            "SELECT id, password_hash, active FROM users WHERE email = ?", [account]
        ).fetchone()
        stored = row[1] if row else _DUMMY_HASH
        valid = verify_password(stored, password or "")
        if not (row and valid and row[2]):
            conn.execute("INSERT INTO login_failures VALUES (?, ?, ?)", [account, address, now])
            conn.execute("DELETE FROM login_failures WHERE attempted_at < ?", [now - timedelta(days=1)])
            user_id = row[0] if row else None
            conn.close()
            conn = None
            audit("login.failed", user_id=user_id, email=account, address=address)
            raise AccountError("invalid_credentials", "Adresse ou mot de passe incorrect.")
        conn.execute("DELETE FROM login_failures WHERE account = ?", [account])
        # Un haché créé avec d'anciens paramètres est recalculé à la volée.
        if _hasher.check_needs_rehash(row[1]):
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", [hash_password(password), row[0]])
        user = _public_user(conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", [row[0]]).fetchone())
    finally:
        if conn is not None:
            conn.close()
    audit("login.success", user_id=user["id"], email=account, address=address)
    return user


# --- Sessions --------------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: str) -> str:
    """Ouvre une session et renvoie le jeton (à poser dans le cookie ; non récupérable ensuite)."""
    token = secrets.token_urlsafe(32)
    now = _now()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, NULL)",
            [_token_hash(token), user_id, now, now + timedelta(hours=SESSION_IDLE_HOURS)],
        )
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", [now - timedelta(days=1)])
    finally:
        conn.close()
    return token


def user_for_token(token: str | None) -> dict | None:
    """Compte de la session ouverte avec ce jeton, ou None (inconnue, expirée, révoquée, compte
    désactivé). Prolonge la session glissante, dans la limite du plafond absolu."""
    if not token:
        return None
    now = _now()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT user_id, created_at, expires_at, revoked_at FROM sessions WHERE token_hash = ?",
            [_token_hash(token)],
        ).fetchone()
        if not row or row[3] is not None or row[2] <= now or row[1] + timedelta(days=SESSION_MAX_DAYS) <= now:
            return None
        user_row = conn.execute(
            f"SELECT {_USER_COLUMNS} FROM users WHERE id = ? AND active", [row[0]]
        ).fetchone()
        if not user_row:
            return None
        extended = min(now + timedelta(hours=SESSION_IDLE_HOURS), row[1] + timedelta(days=SESSION_MAX_DAYS))
        if extended - row[2] > timedelta(minutes=10):
            conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", [extended, _token_hash(token)])
    finally:
        conn.close()
    return _public_user(user_row)


def revoke_session(token: str | None) -> None:
    if not token:
        return
    conn = _connect()
    try:
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            [_now(), _token_hash(token)],
        )
    finally:
        conn.close()


def revoke_user_sessions(user_id: str, *, except_token: str | None = None) -> None:
    keep = _token_hash(except_token) if except_token else ""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL AND token_hash <> ?",
            [_now(), user_id, keep],
        )
    finally:
        conn.close()


def change_password(user_id: str, current: str, new: str, *, keep_token: str | None = None) -> None:
    """Change le mot de passe après vérification de l'ancien ; ferme les autres sessions."""
    conn = _connect()
    try:
        row = conn.execute("SELECT password_hash, email FROM users WHERE id = ?", [user_id]).fetchone()
        if not row:
            raise AccountError("not_found", "Compte introuvable.")
        if not verify_password(row[0], current or ""):
            raise AccountError("invalid_credentials", "Le mot de passe actuel est incorrect.")
        check_password_strength(new, row[1])
        conn.execute(
            "UPDATE users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
            [hash_password(new), _now(), user_id],
        )
    finally:
        conn.close()
    revoke_user_sessions(user_id, except_token=keep_token)
    audit("password.change", user_id=user_id, target=user_id)


def admin_set_password(user_id: str, new: str, *, actor: str | None = None) -> None:
    """Pose un nouveau mot de passe (commande d'administration) et ferme toutes les sessions."""
    conn = _connect()
    try:
        row = conn.execute("SELECT email FROM users WHERE id = ?", [user_id]).fetchone()
        if not row:
            raise AccountError("not_found", "Compte introuvable.")
        check_password_strength(new, row[0])
        conn.execute(
            "UPDATE users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
            [hash_password(new), _now(), user_id],
        )
    finally:
        conn.close()
    revoke_user_sessions(user_id)
    audit("password.reset", user_id=actor, target=user_id)
