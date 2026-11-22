"""Validation des exercices par un ostéopathe (phase 2 du chantier « comptes, validation et fiches »).

Règles (section 5 du plan, vérifiées par tests/test_validation.py) :
- une validation porte sur une VERSION précise, identifiée par l'empreinte (SHA-256) du contenu
  complet de la fiche : texte, dosage, poses, poses clés. Une seule lettre modifiée = autre version ;
- seul un compte avec le rôle ostéopathe, connecté, valide en son nom (ni administrateur, ni
  praticien, ni assistant) ;
- la validation exige l'empreinte vue à l'écran (une validation ne se rejoue pas sur une version
  modifiée), la confirmation de l'animation lancée en entier et la formule cochée, enregistrée telle
  quelle ;
- `exercise_validations` n'est jamais modifiée ni supprimée : un retrait est une nouvelle ligne ;
- les exercices de fichier (`exercises/`) ne passent en base que lorsqu'un ostéopathe en valide un :
  sa version 1 est alors créée depuis le fichier. Les champs `status`, `validated_by`, `validated_on`
  des fichiers ne décident plus de rien ici.

Identifiants en UUID, pour un futur échange entre cabinets."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

import duckdb

from tms_vision import exercises, storage

OSTEOPATH_ROLE = "osteopathe"
FORMULAS = {
    "fr": "J'ai vérifié le texte et l'animation de cette fiche.",
    "en": "I have checked the text and the animation of this sheet.",
}
DEFAULT_AUTHOR = "TMS Vision"
# Champs de fichier qui n'entrent pas dans l'empreinte : l'ancien statut global n'est plus utilisé.
_FINGERPRINT_EXCLUDED = ("status", "validated_by", "validated_on")
_FICHE_AUTHOR = re.compile(r"^Fiche de (.+?)\s*(?:,|—|$)")

CREATE_EXERCISES_TABLE = """
CREATE TABLE IF NOT EXISTS exercises (
    id VARCHAR PRIMARY KEY,
    origin VARCHAR NOT NULL,
    original_author VARCHAR NOT NULL,
    copied_from_exercise VARCHAR,
    copied_from_version VARCHAR,
    created_at TIMESTAMP NOT NULL
)
"""
CREATE_VERSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS exercise_versions (
    id VARCHAR PRIMARY KEY,
    exercise_id VARCHAR NOT NULL,
    number INTEGER NOT NULL,
    content VARCHAR NOT NULL,
    fingerprint VARCHAR NOT NULL,
    author_id VARCHAR,
    created_at TIMESTAMP NOT NULL
)
"""
CREATE_VALIDATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS exercise_validations (
    id VARCHAR PRIMARY KEY,
    version_id VARCHAR NOT NULL,
    exercise_id VARCHAR NOT NULL,
    fingerprint VARCHAR NOT NULL,
    osteo_id VARCHAR NOT NULL,
    osteo_name VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    formula VARCHAR,
    recorded_at TIMESTAMP NOT NULL
)
"""


class ValidationError(ValueError):
    """Demande refusée ; `status` est le code HTTP à renvoyer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat()


def _connect() -> "duckdb.DuckDBPyConnection":
    storage.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(storage.DB_PATH))
    conn.execute(CREATE_EXERCISES_TABLE)
    conn.execute(CREATE_VERSIONS_TABLE)
    conn.execute(CREATE_VALIDATIONS_TABLE)
    return conn


def fingerprint(exercise: dict) -> str:
    """Empreinte du contenu complet de la fiche (JSON canonique, hors ancien statut de fichier)."""
    content = {key: value for key, value in exercise.items() if key not in _FINGERPRINT_EXCLUDED}
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def original_author(exercise: dict) -> str:
    """Auteur d'origine d'un exercice de fichier, déduit du champ `fiche`."""
    match = _FICHE_AUTHOR.match(exercise.get("fiche") or "")
    return match.group(1) if match else DEFAULT_AUTHOR


def is_osteopath(user: dict | None) -> bool:
    return bool(user) and OSTEOPATH_ROLE in user.get("roles", [])


# --- Catalogue : fichiers puis base (la base l'emporte) -------------------------------------------


def load_effective_catalog() -> list[dict]:
    """Exercices de fichier, puis ceux créés en base (copies, créations des phases 3 et 4) : à id
    égal, la version courante de la base l'emporte. Ne casse pas `exercises.load_catalog`, qui reste
    le chemin « fichiers seuls »."""
    by_id = {exercise["id"]: exercise for exercise in exercises.load_catalog()}
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT v.content FROM exercises e JOIN exercise_versions v ON v.exercise_id = e.id "
            "WHERE e.origin != 'file' AND v.number = "
            "(SELECT max(number) FROM exercise_versions WHERE exercise_id = e.id)"
        ).fetchall()
    finally:
        conn.close()
    for (content,) in rows:
        exercise = json.loads(content)
        by_id[exercise["id"]] = exercise
    return sorted(by_id.values(), key=lambda exercise: exercise["id"])


def get_exercise(exercise_id: str) -> dict | None:
    for exercise in load_effective_catalog():
        if exercise["id"] == exercise_id:
            return exercise
    return None


# --- Lecture de l'état de validation --------------------------------------------------------------


def _active_validations(rows: list[tuple]) -> list[dict]:
    """`rows` : lignes d'une même version, par ordre d'enregistrement. Un ostéopathe est valideur
    tant que sa dernière ligne n'est pas un retrait. Plus récent en premier."""
    last_by_osteo: dict[str, tuple] = {}
    for row in rows:
        last_by_osteo[row[0]] = row
    active = [
        {"osteo_id": osteo_id, "osteo_name": name, "validated_on": _iso(recorded_at)}
        for osteo_id, name, kind, recorded_at in last_by_osteo.values()
        if kind == "validate"
    ]
    return sorted(active, key=lambda item: item["validated_on"], reverse=True)


def _label(exercise: dict, active: list[dict], osteo_id: str | None) -> dict:
    latest = active[0] if active else None
    return {
        "created_by": original_author(exercise),
        "validated_by": latest["osteo_name"] if latest else None,
        "validated_on": latest["validated_on"] if latest else None,
        "validator_ids": [item["osteo_id"] for item in active],
        "validated_by_selected": (
            any(item["osteo_id"] == osteo_id for item in active) if osteo_id else None
        ),
        "fingerprint": fingerprint(exercise),
    }


def labels_for(exercise_list: list[dict], osteo_id: str | None = None) -> dict[str, dict]:
    """Étiquette de chaque exercice : « créé par … » et « validé par … le … » si sa version
    COURANTE est validée, sinon `validated_by` vaut None (« non validé »). `osteo_id` : ostéopathe
    choisi sur le bilan, pour `validated_by_selected`."""
    prints = {exercise["id"]: fingerprint(exercise) for exercise in exercise_list}
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT exercise_id, fingerprint, osteo_id, osteo_name, kind, recorded_at "
            "FROM exercise_validations ORDER BY recorded_at, rowid"
        ).fetchall()
    finally:
        conn.close()
    grouped: dict[tuple[str, str], list[tuple]] = {}
    for exercise_id, print_, osteo, name, kind, recorded_at in rows:
        if prints.get(exercise_id) == print_:
            grouped.setdefault((exercise_id, print_), []).append((osteo, name, kind, recorded_at))
    return {
        exercise["id"]: _label(
            exercise,
            _active_validations(grouped.get((exercise["id"], prints[exercise["id"]]), [])),
            osteo_id,
        )
        for exercise in exercise_list
    }


def label_for(exercise: dict, osteo_id: str | None = None) -> dict:
    return labels_for([exercise], osteo_id)[exercise["id"]]


def history(exercise_id: str) -> list[dict]:
    """Toutes les lignes d'enregistrement de l'exercice (validations et retraits), de la plus
    ancienne à la plus récente, toutes versions confondues. Rien n'est jamais effacé."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT v.number, x.fingerprint, x.osteo_id, x.osteo_name, x.kind, x.formula, "
            "x.recorded_at FROM exercise_validations x JOIN exercise_versions v "
            "ON v.id = x.version_id WHERE x.exercise_id = ? ORDER BY x.recorded_at, x.rowid",
            [exercise_id],
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "version": number, "fingerprint": print_, "osteo_id": osteo, "osteo_name": name,
            "kind": kind, "formula": formula, "recorded_at": _iso(recorded_at),
        }
        for number, print_, osteo, name, kind, formula, recorded_at in rows
    ]


# --- Écriture -------------------------------------------------------------------------------------


def _ensure_version(conn, exercise: dict) -> str:
    """Id de la version correspondant au contenu actuel de l'exercice ; la crée au besoin (version 1
    depuis le fichier, ou version suivante si le fichier a changé depuis)."""
    print_ = fingerprint(exercise)
    row = conn.execute(
        "SELECT id FROM exercise_versions WHERE exercise_id = ? AND fingerprint = ?",
        [exercise["id"], print_],
    ).fetchone()
    if row:
        return row[0]
    if conn.execute("SELECT 1 FROM exercises WHERE id = ?", [exercise["id"]]).fetchone() is None:
        conn.execute(
            "INSERT INTO exercises VALUES (?, 'file', ?, NULL, NULL, ?)",
            [exercise["id"], original_author(exercise), _now()],
        )
    number = conn.execute(
        "SELECT coalesce(max(number), 0) + 1 FROM exercise_versions WHERE exercise_id = ?",
        [exercise["id"]],
    ).fetchone()[0]
    version_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO exercise_versions VALUES (?, ?, ?, ?, ?, NULL, ?)",
        [version_id, exercise["id"], number, json.dumps(exercise, ensure_ascii=False), print_, _now()],
    )
    return version_id


def _require_osteopath(user: dict | None) -> dict:
    if user is None:
        raise ValidationError(401, "Connexion requise.")
    if not is_osteopath(user):
        raise ValidationError(403, "Seul un compte ostéopathe peut valider une fiche.")
    return user


def validate(
    user: dict | None, exercise_id: str, *, seen_fingerprint: str, formula: str,
    animation_completed: bool,
) -> dict:
    """Enregistre la validation de la version COURANTE de l'exercice par `user`. Refuse si le
    compte n'est pas ostéopathe, si l'empreinte vue à l'écran n'est plus celle de la fiche (elle a
    changé), si l'animation n'a pas été lancée en entier ou si la formule n'est pas la bonne."""
    user = _require_osteopath(user)
    exercise = get_exercise(exercise_id)
    if exercise is None:
        raise ValidationError(404, "Exercice introuvable.")
    if not animation_completed:
        raise ValidationError(422, "L'animation doit être lancée en entier avant de valider.")
    if formula not in FORMULAS.values():
        raise ValidationError(422, "La confirmation « j'ai vérifié… » doit être cochée.")
    if seen_fingerprint != fingerprint(exercise):
        raise ValidationError(409, "La fiche a changé depuis son affichage : relisez-la.")

    conn = _connect()
    try:
        version_id = _ensure_version(conn, exercise)
        conn.execute(
            "INSERT INTO exercise_validations VALUES (?, ?, ?, ?, ?, ?, 'validate', ?, ?)",
            [
                str(uuid.uuid4()), version_id, exercise_id, fingerprint(exercise), user["id"],
                user["name"], formula, _now(),
            ],
        )
    finally:
        conn.close()
    _audit("exercise.validate", user, exercise_id)
    return label_for(exercise, user["id"])


def withdraw(user: dict | None, exercise_id: str) -> dict:
    """Retrait de SA validation : nouvelle ligne, l'ancienne reste. Seul l'ostéopathe qui a validé
    la version courante peut la retirer."""
    user = _require_osteopath(user)
    exercise = get_exercise(exercise_id)
    if exercise is None:
        raise ValidationError(404, "Exercice introuvable.")
    label = label_for(exercise, user["id"])
    if not label["validated_by_selected"]:
        raise ValidationError(409, "Vous n'avez pas de validation en cours sur cette fiche.")
    conn = _connect()
    try:
        version_id = _ensure_version(conn, exercise)
        conn.execute(
            "INSERT INTO exercise_validations VALUES (?, ?, ?, ?, ?, ?, 'withdraw', NULL, ?)",
            [
                str(uuid.uuid4()), version_id, exercise_id, fingerprint(exercise), user["id"],
                user["name"], _now(),
            ],
        )
    finally:
        conn.close()
    _audit("exercise.withdraw", user, exercise_id)
    return label_for(exercise, user["id"])


def _audit(action: str, user: dict, exercise_id: str) -> None:
    from tms_vision import accounts  # import tardif : accounts importe storage, comme ce module

    accounts.audit(action, user_id=user["id"], email=user.get("email"), target=exercise_id)


def describe_label(label: dict) -> str:
    """Étiquette en texte (email au patient) : « créé par X · validé par Y le JJ/MM/AAAA » ou
    « créé par X · non validé »."""
    if label["validated_by"]:
        day = datetime.fromisoformat(label["validated_on"]).strftime("%d/%m/%Y")
        return f"créé par {label['created_by']} · validé par {label['validated_by']} le {day}"
    return f"créé par {label['created_by']} · non validé"
