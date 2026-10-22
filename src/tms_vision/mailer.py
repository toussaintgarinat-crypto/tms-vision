"""Envoi des exercices au patient par email. Rien n'est câblé en dur : le fournisseur est
choisi par la variable d'environnement TMS_MAILER, et la valeur par défaut est « aucun »
(l'envoi est enregistré, le lien reste à transmettre au patient à la main). Pour brancher
un vrai service, écrire une classe qui hérite de Mailer et la désigner par
`TMS_MAILER=module.chemin:Classe` ; aucun autre fichier n'est à modifier.

Variables :
- TMS_MAILER : `none` (défaut) ou `module.chemin:Classe`.
- TMS_PUBLIC_WEB_URL : adresse publique du site, utilisée pour le lien vers la page du
  patient (défaut : http://localhost:3000)."""
import importlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

DEFAULT_PUBLIC_WEB_URL = "http://localhost:3000"


class MailerError(RuntimeError):
    """Configuration invalide ou échec d'un fournisseur d'envoi."""


@dataclass(frozen=True)
class OutgoingMessage:
    to: str
    subject: str
    text: str


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
    if ":" not in value:
        raise MailerError(
            f"TMS_MAILER : valeur '{value}' invalide (attendu : none ou module.chemin:Classe)."
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


def build_share_message(
    *, to: str, share_url: str, practitioner_name: str | None, message: str | None,
    exercise_titles: list[str],
) -> OutgoingMessage:
    sender = practitioner_name or "Votre praticien"
    lines = [f"{sender} vous a préparé une série d'exercices.", ""]
    if message:
        lines += [message, ""]
    lines += [f"- {title}" for title in exercise_titles]
    lines += [
        "",
        f"Retrouvez chaque exercice animé et les consignes ici : {share_url}",
        "",
        "Ces exercices sont donnés à titre indicatif : arrêtez en cas de douleur et "
        "parlez-en à votre praticien.",
    ]
    return OutgoingMessage(to=to, subject="Vos exercices", text="\n".join(lines))
