"""Envoi d'emails par SMTP (bibliothèque standard, sans service tiers imposé).

Choisi par `TMS_MAILER=smtp`. Fonctionne avec le serveur du cabinet, Gmail (mot de passe
d'application), Outlook, OVH, Brevo, Resend, etc. : tout ce qui parle SMTP.

Variables (dans `.env`) :
- TMS_SMTP_HOST     : serveur SMTP (obligatoire), ex. smtp.gmail.com.
- TMS_SMTP_PORT     : port (défaut 587 ; 465 si TMS_SMTP_SECURE).
- TMS_SMTP_SECURE   : `true` pour TLS dès la connexion (port 465). Défaut : false.
- TMS_SMTP_STARTTLS : `true` (défaut) pour passer en TLS après la connexion (port 587).
                      `false` pour un relais interne sans TLS (ex. Mailpit en développement).
- TMS_SMTP_USER     : identifiant (vide = pas d'authentification).
- TMS_SMTP_PASS     : mot de passe ou mot de passe d'application. Ne passe QUE par le `.env`.
- TMS_SMTP_FROM     : expéditeur (obligatoire, ex. `Cabinet Martin <contact@cabinet.fr>`).
- TMS_SMTP_TIMEOUT  : délai en secondes (défaut 15).

Le mot de passe n'est jamais écrit dans un message d'erreur ni renvoyé. La vérification du
certificat du serveur est toujours active : un serveur dont le certificat est invalide est refusé.
"""
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from tms_vision.mailer import Mailer, MailerError, OutgoingMessage

DEFAULT_PORT = 587
DEFAULT_SECURE_PORT = 465
DEFAULT_TIMEOUT = 15.0

_TRUE = {"1", "true", "yes", "oui", "on"}
_FALSE = {"0", "false", "no", "non", "off"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise MailerError(f"{name} : valeur '{raw}' invalide (attendu : true ou false).")


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    secure: bool
    starttls: bool
    user: str
    password: str
    sender: str
    timeout: float

    @classmethod
    def from_env(cls) -> "SmtpSettings":
        host = os.environ.get("TMS_SMTP_HOST", "").strip()
        if not host:
            raise MailerError("TMS_SMTP_HOST : serveur SMTP non renseigné.")
        sender = os.environ.get("TMS_SMTP_FROM", "").strip()
        if not sender:
            raise MailerError("TMS_SMTP_FROM : adresse d'expédition non renseignée.")
        address = parseaddr(sender)[1]
        if "@" not in address or any(char in sender for char in "\r\n"):
            raise MailerError("TMS_SMTP_FROM : adresse d'expédition invalide.")
        secure = _env_bool("TMS_SMTP_SECURE", False)
        raw_port = os.environ.get("TMS_SMTP_PORT", "").strip()
        try:
            port = int(raw_port) if raw_port else (DEFAULT_SECURE_PORT if secure else DEFAULT_PORT)
        except ValueError:
            raise MailerError(f"TMS_SMTP_PORT : '{raw_port}' n'est pas un nombre.") from None
        if not 1 <= port <= 65535:
            raise MailerError("TMS_SMTP_PORT : port hors limites (1 à 65535).")
        raw_timeout = os.environ.get("TMS_SMTP_TIMEOUT", "").strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT
        except ValueError:
            raise MailerError(f"TMS_SMTP_TIMEOUT : '{raw_timeout}' n'est pas un nombre.") from None
        if timeout <= 0:
            raise MailerError("TMS_SMTP_TIMEOUT : doit être positif.")
        return cls(
            host=host,
            port=port,
            secure=secure,
            starttls=_env_bool("TMS_SMTP_STARTTLS", True),
            user=os.environ.get("TMS_SMTP_USER", "").strip(),
            password=os.environ.get("TMS_SMTP_PASS", ""),
            sender=sender,
            timeout=timeout,
        )


def build_mime(settings: SmtpSettings, message: OutgoingMessage) -> EmailMessage:
    mime = EmailMessage()
    mime["From"] = settings.sender
    mime["To"] = message.to
    mime["Subject"] = message.subject
    if message.reply_to:
        mime["Reply-To"] = message.reply_to
    mime["Date"] = formatdate(localtime=True)
    domain = parseaddr(settings.sender)[1].rpartition("@")[2] or None
    mime["Message-ID"] = make_msgid(domain=domain)
    mime.set_content(message.text)
    if message.html:
        mime.add_alternative(message.html, subtype="html")
    return mime


class SmtpMailer(Mailer):
    name = "smtp"

    def __init__(self) -> None:
        self.settings = SmtpSettings.from_env()

    def send(self, message: OutgoingMessage) -> None:
        settings = self.settings
        try:
            mime = build_mime(settings, message)
        except ValueError as error:
            raise MailerError(f"Message invalide : {error}") from error

        context = ssl.create_default_context()
        try:
            if settings.secure:
                server = smtplib.SMTP_SSL(
                    settings.host, settings.port, timeout=settings.timeout, context=context
                )
            else:
                server = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout)
            with server:
                if not settings.secure and settings.starttls:
                    server.starttls(context=context)
                if settings.user:
                    server.login(settings.user, settings.password)
                server.send_message(mime)
        except smtplib.SMTPAuthenticationError as error:
            raise MailerError(
                f"Identifiant ou mot de passe refusé par {settings.host} "
                "(avec Gmail ou Outlook, utiliser un mot de passe d'application)."
            ) from error
        except smtplib.SMTPRecipientsRefused as error:
            raise MailerError("Adresse du destinataire refusée par le serveur.") from error
        except (smtplib.SMTPException, OSError) as error:
            # Le nom de l'erreur suffit à diagnostiquer ; son texte pourrait citer des identifiants.
            raise MailerError(
                f"Envoi impossible via {settings.host}:{settings.port} ({type(error).__name__})."
            ) from error
