"""Adresse d'envoi de chaque compte (« Mon email »).

Chaque praticien ou ostéopathe peut renseigner l'adresse depuis laquelle partent ses exercices :
le patient reçoit un message de son praticien, et ses réponses lui reviennent. Sans réglage, le
message part de l'adresse du cabinet (`TMS_SMTP_*` dans le `.env`) avec le nom du praticien dans le
texte, et l'adresse du praticien en Reply-To : l'envoi n'est jamais bloqué.

Le mot de passe (de préférence un mot de passe d'application) est chiffré en base avec AES-GCM, clé
secrète `TMS_SECRET_KEY` du `.env`. Il n'est jamais renvoyé au navigateur ni écrit dans le journal.
Si la clé est perdue, chacun ressaisit son mot de passe : la conserver à part des sauvegardes de
data/."""
import base64
import hashlib
import ipaddress
import os
import socket
from datetime import datetime, timezone
from email.utils import formataddr

import duckdb
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tms_vision import accounts
from tms_vision.mailer import Mailer, MailerError, OutgoingMessage
from tms_vision.smtp_mailer import SmtpMailer, SmtpSettings

SECURITY_MODES = ("starttls", "ssl", "none")
ALLOWED_PORTS = (25, 465, 587, 2525)
_TRUE = {"1", "true", "yes", "oui", "on"}

# Serveurs courants, devinés d'après le domaine de l'adresse : la personne n'a qu'à coller un mot de
# passe d'application. (domaines, serveur, port, sécurité)
PROVIDERS = (
    (("gmail.com", "googlemail.com"), "smtp.gmail.com", 587, "starttls"),
    (("outlook.com", "outlook.fr", "hotmail.com", "hotmail.fr", "live.com", "live.fr", "msn.com"),
     "smtp-mail.outlook.com", 587, "starttls"),
    (("orange.fr", "wanadoo.fr"), "smtp.orange.fr", 465, "ssl"),
    (("free.fr",), "smtp.free.fr", 465, "ssl"),
    (("ovh.net", "ovh.com"), "ssl0.ovh.net", 465, "ssl"),
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS user_email_settings (
    user_id VARCHAR PRIMARY KEY,
    address VARCHAR NOT NULL,
    host VARCHAR NOT NULL,
    port INTEGER NOT NULL,
    security VARCHAR NOT NULL,
    username VARCHAR NOT NULL,
    password_enc VARCHAR NOT NULL,
    last_test_ok_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL
)
"""


def _connect() -> "duckdb.DuckDBPyConnection":
    conn = accounts._connect()
    conn.execute(CREATE_TABLE)
    return conn


# --- Chiffrement -----------------------------------------------------------------------------


def _key() -> bytes:
    secret = os.environ.get("TMS_SECRET_KEY", "").strip()
    if len(secret) < 16:
        raise accounts.AccountError(
            "secret_key_missing",
            "TMS_SECRET_KEY n'est pas renseignée dans le .env (16 caractères au moins) : "
            "le mot de passe ne peut pas être enregistré.",
        )
    return hashlib.sha256(b"tms-vision/user-email/" + secret.encode("utf-8")).digest()


def encrypt_secret(plain: str) -> str:
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(_key()).encrypt(nonce, plain.encode("utf-8"), None)).decode("ascii")


def decrypt_secret(token: str) -> str:
    raw = base64.b64decode(token)
    try:
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")
    except InvalidTag:
        raise accounts.AccountError(
            "secret_key_changed",
            "Le mot de passe enregistré n'est plus lisible (clé TMS_SECRET_KEY modifiée) : ressaisissez-le.",
        ) from None


# --- Réglages --------------------------------------------------------------------------------


def suggest(address: str) -> dict | None:
    domain = address.strip().lower().rpartition("@")[2]
    for domains, host, port, security in PROVIDERS:
        if domain in domains:
            return {"host": host, "port": port, "security": security}
    return None


def _check_host(host: str) -> None:
    """Refuse un serveur interne : sans cela, un compte pourrait faire sonder le réseau du cabinet
    par le serveur. (TMS_SMTP_ALLOW_PRIVATE=true l'autorise, pour un relais interne ou Mailpit.)"""
    if os.environ.get("TMS_SMTP_ALLOW_PRIVATE", "").strip().lower() in _TRUE:
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise accounts.AccountError("host_unknown", f"Serveur « {host} » introuvable.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise accounts.AccountError("host_private", "Ce serveur est interne au réseau : choisissez un serveur de messagerie public.")


def _validate(address: str, host: str, port: int, security: str, username: str) -> tuple[str, str, str]:
    address = accounts.normalize_email(address)
    host = host.strip().lower()
    if not host or len(host) > 253 or any(c.isspace() or c in "/@:" for c in host):
        raise accounts.AccountError("invalid_host", "Nom de serveur invalide.")
    if port not in ALLOWED_PORTS:
        raise accounts.AccountError("invalid_port", f"Port attendu parmi : {', '.join(map(str, ALLOWED_PORTS))}.")
    if security not in SECURITY_MODES:
        raise accounts.AccountError("invalid_security", f"Sécurité attendue parmi : {', '.join(SECURITY_MODES)}.")
    username = (username or address).strip()
    if len(username) > 254 or any(c in username for c in "\r\n"):
        raise accounts.AccountError("invalid_username", "Identifiant invalide.")
    _check_host(host)
    return address, host, username


def get_settings(user_id: str) -> dict:
    """Réglages à montrer au site : jamais le mot de passe, seulement s'il est enregistré."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT address, host, port, security, username, last_test_ok_at FROM user_email_settings WHERE user_id = ?",
            [user_id],
        ).fetchone()
    finally:
        conn.close()
    cabinet = bool(os.environ.get("TMS_SMTP_HOST", "").strip() and os.environ.get("TMS_SMTP_FROM", "").strip())
    base = {
        "configured": row is not None,
        "cabinet_fallback": cabinet and os.environ.get("TMS_MAILER", "").strip().lower() == "smtp",
        "encryption_available": len(os.environ.get("TMS_SECRET_KEY", "").strip()) >= 16,
    }
    if row is None:
        return base
    address, host, port, security, username, tested = row
    return {
        **base, "address": address, "host": host, "port": port, "security": security,
        "username": username, "password_set": True,
        "last_test_ok_at": tested.isoformat() if tested else None,
        "status": "connected" if tested else "untested",
    }


def save_settings(
    user_id: str, *, address: str, host: str, port: int, security: str, username: str, password: str | None
) -> dict:
    """Enregistre les réglages. `password` vide : on garde celui déjà enregistré. Tout changement
    invalide le dernier test réussi."""
    address, host, username = _validate(address, host, port, security, username)
    conn = _connect()
    try:
        existing = conn.execute("SELECT password_enc FROM user_email_settings WHERE user_id = ?", [user_id]).fetchone()
        if password:
            encrypted = encrypt_secret(password)
        elif existing:
            encrypted = existing[0]
        else:
            raise accounts.AccountError("password_required", "Le mot de passe est obligatoire.")
        conn.execute("DELETE FROM user_email_settings WHERE user_id = ?", [user_id])
        conn.execute(
            "INSERT INTO user_email_settings VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)",
            [user_id, address, host, port, security, username, encrypted, _now()],
        )
    finally:
        conn.close()
    accounts.audit("email.settings.save", user_id=user_id, target=user_id, detail=f"{host}:{port}")
    return get_settings(user_id)


def delete_settings(user_id: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM user_email_settings WHERE user_id = ?", [user_id])
    finally:
        conn.close()
    accounts.audit("email.settings.delete", user_id=user_id, target=user_id)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _smtp_settings(user: dict) -> SmtpSettings | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT address, host, port, security, username, password_enc FROM user_email_settings WHERE user_id = ?",
            [user["id"]],
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    address, host, port, security, username, password_enc = row
    return SmtpSettings(
        host=host, port=port, secure=security == "ssl", starttls=security == "starttls",
        user=username, password=decrypt_secret(password_enc),
        sender=formataddr((user["name"], address)), timeout=15.0,
    )


def mailer_for(user: dict | None) -> tuple[Mailer, str | None]:
    """Service d'envoi à utiliser pour ce compte, et l'adresse de réponse (Reply-To) à poser.

    Réglages personnels si le compte en a ; sinon l'adresse du cabinet, avec le compte en Reply-To."""
    if user is not None:
        try:
            settings = _smtp_settings(user)
        except accounts.AccountError as error:
            raise MailerError(str(error)) from error
        if settings is not None:
            return SmtpMailer(settings), parse_address(settings.sender)
    from tms_vision.mailer import get_mailer

    return get_mailer(), (user["email"] if user else None)


def parse_address(sender: str) -> str:
    from email.utils import parseaddr

    return parseaddr(sender)[1]


def send_test(user: dict) -> dict:
    """Envoie un message de test à la propre adresse du compte ; mémorise le succès."""
    settings = _smtp_settings(user)
    if settings is None:
        raise accounts.AccountError("not_configured", "Aucun email personnel n'est configuré.")
    message = OutgoingMessage(
        to=parse_address(settings.sender),
        subject="TMS Vision : message de test",
        text="Ce message confirme que vos exercices peuvent partir depuis cette adresse.",
    )
    try:
        SmtpMailer(settings).send(message)
    except MailerError as error:
        raise accounts.AccountError("send_failed", str(error)) from error
    conn = _connect()
    try:
        conn.execute("UPDATE user_email_settings SET last_test_ok_at = ? WHERE user_id = ?", [_now(), user["id"]])
    finally:
        conn.close()
    accounts.audit("email.test.ok", user_id=user["id"], target=user["id"])
    return get_settings(user["id"])
