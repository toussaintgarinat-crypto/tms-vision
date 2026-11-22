"""Envoi des exercices au patient par email. Rien n'est câblé en dur : le fournisseur est
choisi par la variable d'environnement TMS_MAILER, et la valeur par défaut est « aucun »
(l'envoi est enregistré, le lien reste à transmettre au patient à la main). Pour brancher
un vrai service, écrire une classe qui hérite de Mailer et la désigner par
`TMS_MAILER=module.chemin:Classe` ; aucun autre fichier n'est à modifier.

Variables :
- TMS_MAILER : `none` (défaut), `smtp` (envoi par un serveur SMTP, voir smtp_mailer.py ;
  variables TMS_SMTP_*) ou `module.chemin:Classe`.
- TMS_PUBLIC_WEB_URL : adresse publique du site, utilisée pour le lien vers la page du
  patient (défaut : http://localhost:3000)."""
import importlib
import os
from html import escape
from abc import ABC, abstractmethod
from dataclasses import dataclass

DEFAULT_PUBLIC_WEB_URL = "http://localhost:3000"
RELEASES_PAGE_URL = "https://github.com/toussaintgarinat-crypto/tms-vision/releases/latest"


class MailerError(RuntimeError):
    """Configuration invalide ou échec d'un fournisseur d'envoi."""


@dataclass(frozen=True)
class OutgoingMessage:
    to: str
    subject: str
    text: str
    html: str | None = None
    reply_to: str | None = None


class Mailer(ABC):
    name = "custom"

    @abstractmethod
    def send(self, message: OutgoingMessage) -> None:
        """Envoie le message ; lève MailerError en cas d'échec."""


class NullMailer(Mailer):
    name = "none"

    def send(self, message: OutgoingMessage) -> None:
        raise MailerError("Aucun service d'envoi n'est configuré (variable TMS_MAILER).")


def get_mailer() -> Mailer:
    value = os.environ.get("TMS_MAILER", "").strip()
    if not value or value.lower() == "none":
        return NullMailer()
    if value.lower() == "smtp":
        from tms_vision.smtp_mailer import SmtpMailer

        return SmtpMailer()
    if ":" not in value:
        raise MailerError(
            f"TMS_MAILER : valeur '{value}' invalide (attendu : none, smtp ou module.chemin:Classe)."
        )
    module_name, _, class_name = value.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise MailerError(f"TMS_MAILER : module '{module_name}' introuvable ({error}).") from error
    mailer_class = getattr(module, class_name, None)
    if mailer_class is None:
        raise MailerError(f"TMS_MAILER : classe '{class_name}' introuvable dans '{module_name}'.")
    if not (isinstance(mailer_class, type) and issubclass(mailer_class, Mailer)):
        raise MailerError(f"TMS_MAILER : '{value}' n'est pas un Mailer.")
    return mailer_class()


def public_web_url() -> str:
    return os.environ.get("TMS_PUBLIC_WEB_URL", "").strip().rstrip("/") or DEFAULT_PUBLIC_WEB_URL


def _html_body(lines: list[str], share_url: str) -> str:
    """Version HTML du message : mêmes lignes que le texte, échappées, avec le lien cliquable
    et la liste des exercices en puces."""
    parts: list[str] = []
    bullets: list[str] = []

    def flush() -> None:
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in bullets) + "</ul>")
            bullets.clear()

    for line in lines:
        if line.startswith("- "):
            bullets.append(escape(line[2:]))
            continue
        flush()
        if not line:
            continue
        safe = escape(line).replace("\n", "<br>")
        link = escape(share_url)
        # Hors de l'f-string : un antislash dans une expression d'f-string n'existe qu'à partir de
        # Python 3.12, et l'application de bureau est construite en 3.11.
        anchor = f'<a href="{link}">{link}</a>'
        parts.append(f"<p>{safe.replace(link, anchor)}</p>")
    flush()
    return "<div style=\"font-family:sans-serif;max-width:560px\">" + "".join(parts) + "</div>"


def build_share_message(
    *, to: str, share_url: str, practitioner_name: str | None, message: str | None,
    exercise_titles: list[str], exercise_labels: list[str] | None = None,
) -> OutgoingMessage:
    sender = practitioner_name or "Votre praticien"
    lines = [f"{sender} vous a préparé une série d'exercices.", ""]
    if message:
        lines += [message, ""]
    labels = exercise_labels or [None] * len(exercise_titles)
    lines += [
        f"- {title} ({label})" if label else f"- {title}"
        for title, label in zip(exercise_titles, labels, strict=True)
    ]
    lines += [
        "",
        f"Retrouvez chaque exercice animé et les consignes ici : {share_url}",
        "",
        "Ces exercices sont donnés à titre indicatif : arrêtez en cas de douleur et "
        "parlez-en à votre praticien.",
    ]
    return OutgoingMessage(
        to=to, subject="Vos exercices", text="\n".join(lines), html=_html_body(lines, share_url)
    )


def installer_links(assets: list[dict]) -> list[tuple[str, str]]:
    """(libellé, adresse) des installateurs d'une version : Windows, Mac Apple Silicon, Mac Intel.
    Seuls les fichiers hébergés par GitHub sont repris."""
    labels = (
        ("TMS-Vision-Setup.exe", "Windows"),
        ("TMS-Vision-Mac-Apple-Silicon.dmg", "Mac avec puce Apple (M1, M2, M3…)"),
        ("TMS-Vision-Mac-Intel.dmg", "Mac avec processeur Intel"),
    )
    by_name = {asset["name"]: asset["url"] for asset in assets}
    return [
        (label, by_name[name]) for name, label in labels
        if by_name.get(name, "").startswith("https://github.com/")
    ]


def _linkify(lines: list[str]) -> str:
    import re

    parts = []
    for line in lines:
        if not line:
            continue
        safe = escape(line).replace("\n", "<br>")
        safe = re.sub(r"(https://[^\s<]+)", r'<a href="\1">\1</a>', safe)
        parts.append(f"<p>{safe}</p>")
    return "<div style=\"font-family:sans-serif;max-width:560px\">" + "".join(parts) + "</div>"


def build_invitation_message(
    *, to: str, inviter_name: str, invitee_name: str | None, message: str | None,
    osteopath: bool, release_url: str, downloads: list[tuple[str, str]],
) -> OutgoingMessage:
    """Invitation à installer l'application de bureau. Aucun mot de passe ni jeton n'y figure : le
    compte se crée sur l'ordinateur de la personne, au premier lancement."""
    lines = [f"Bonjour{' ' + invitee_name if invitee_name else ''},", ""]
    lines.append(f"{inviter_name} vous invite à utiliser TMS Vision, l'application d'analyse des postures de travail.")
    if message:
        lines += ["", message]
    lines += ["", "1. Téléchargez l'application pour votre ordinateur :"]
    lines += [f"{label} : {url}" for label, url in downloads] or [f"Page de téléchargement : {release_url}"]
    if downloads:
        lines.append(f"Autres fichiers et versions : {release_url}")
    lines += [
        "",
        "2. Installez-la (double-clic). Si votre ordinateur affiche un avertissement de sécurité, "
        "choisissez « Exécuter quand même » (Windows) ou « Ouvrir » après un clic droit (Mac).",
        "",
        "3. Au premier lancement, l'application vous demande de créer votre compte : votre adresse email, "
        "votre nom et un mot de passe d'au moins 12 caractères.",
    ]
    if osteopath:
        lines += [
            "",
            "Vous êtes ostéopathe ? Cochez « Je suis ostéopathe » : cela vous permettra de relire et valider "
            "des fiches d'exercices sous votre nom (menus « Relecture des fiches » et « Mes fiches »).",
        ]
    lines += [
        "",
        "4. Notez le code de récupération affiché : il sert à retrouver l'accès si vous oubliez votre mot de passe.",
        "",
        "Vos données restent sur votre ordinateur.",
    ]
    text = "\n".join(lines)
    return OutgoingMessage(
        to=to, subject="Invitation à installer TMS Vision", text=text, html=_linkify(lines)
    )
