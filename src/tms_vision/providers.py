"""Fournisseurs optionnels pour la génération des modules d'étirement : voix,
reformulation des consignes, proposition d'exercices (voir
docs/superpowers/plans/2026-10-21-generation-modules-etirement-plan.md).

Rien ici n'est câblé en dur : chaque fournisseur est choisi par une variable
d'environnement, et la valeur par défaut est « aucun » (le texte reste celui écrit
à la main, aucune voix, aucun exercice généré). Aucun appel réseau n'est fait par ce
module ; un fournisseur distant n'existe que si l'on configure explicitement une
classe ou une commande qui en fait un.

Variables :
- TMS_NARRATION_PROVIDER, TMS_INSTRUCTION_PROVIDER, TMS_EXERCISE_PROVIDER :
  `none` (défaut), `command` (voix seulement) ou `module.chemin:Classe`.
- TMS_NARRATION_COMMAND : commande locale de synthèse vocale (voir
  CommandNarrationProvider) ; TMS_NARRATION_TIMEOUT : délai maximal en secondes."""
import importlib
import io
import os
import shlex
import subprocess
import wave
from abc import ABC, abstractmethod

# Silence minimal entre deux consignes dites, pour ne pas les enchaîner sans respiration.
GAP_SECONDS = 0.25
DEFAULT_COMMAND_TIMEOUT_SECONDS = 120.0


class ProviderError(RuntimeError):
    """Configuration invalide ou échec d'un fournisseur."""


class ProviderNotConfigured(ProviderError):
    """Un fournisseur est nécessaire mais aucun n'est configuré."""


class NarrationProvider(ABC):
    name = "custom"

    @abstractmethod
    def synthesize(self, text: str, language: str) -> bytes | None:
        """Voix de synthèse d'une consigne : un fichier WAV, ou None s'il n'y en a pas."""


class InstructionProvider(ABC):
    name = "custom"

    @abstractmethod
    def rewrite(self, exercise: dict, language: str) -> list[dict] | None:
        """Consignes reformulées, au format `[{"t": ..., "text": ...}]`, ou None pour
        garder celles écrites à la main."""


class ExerciseProvider(ABC):
    name = "custom"

    @abstractmethod
    def propose(self, zone: str, constraints: dict) -> dict:
        """Définition d'exercice proposée (format de exercises.py). Toujours traitée comme
        un brouillon `source: "ai"`, jamais comme un exercice du catalogue."""


class NullNarrationProvider(NarrationProvider):
    name = "none"

    def synthesize(self, text: str, language: str) -> None:
        return None


class NullInstructionProvider(InstructionProvider):
    name = "none"

    def rewrite(self, exercise: dict, language: str) -> None:
        return None


class NullExerciseProvider(ExerciseProvider):
    name = "none"

    def propose(self, zone: str, constraints: dict) -> dict:
        raise ProviderNotConfigured(
            "Aucun fournisseur d'exercices n'est configuré (variable TMS_EXERCISE_PROVIDER)."
        )


def _is_wav(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def wav_duration_seconds(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            return handle.getnframes() / handle.getframerate()
    except (wave.Error, EOFError, ZeroDivisionError) as error:
        raise ProviderError(f"Fichier audio WAV illisible : {error}") from error


class CommandNarrationProvider(NarrationProvider):
    """Voix par une commande locale, sans écrire de code : le texte est envoyé sur
    l'entrée standard, un WAV est lu sur la sortie standard, la langue est transmise
    dans TMS_NARRATION_LANGUAGE. La commande est exécutée SANS shell (découpée avec
    `shlex`), par exemple un moteur de synthèse local open source comme piper."""

    name = "command"

    def __init__(self, command: str, timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS):
        self.command = command
        self.timeout_seconds = timeout_seconds

    def synthesize(self, text: str, language: str) -> bytes:
        arguments = shlex.split(self.command)
        if not arguments:
            raise ProviderError("La commande de synthèse vocale est vide.")
        try:
            result = subprocess.run(
                arguments,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=self.timeout_seconds,
                env={**os.environ, "TMS_NARRATION_LANGUAGE": language},
            )
        except FileNotFoundError as error:
            raise ProviderError(f"Commande de synthèse vocale introuvable : {arguments[0]}") from error
        except subprocess.TimeoutExpired as error:
            raise ProviderError(
                f"La synthèse vocale a dépassé le délai de {self.timeout_seconds:g} s."
            ) from error

        if result.returncode != 0:
            details = result.stderr.decode("utf-8", errors="replace").strip()[:300]
            raise ProviderError(
                f"La commande de synthèse vocale a échoué (code {result.returncode}) : {details}"
            )
        if not _is_wav(result.stdout):
            raise ProviderError("La commande de synthèse vocale n'a pas produit de fichier WAV valide.")
        return result.stdout


def _load_provider(env_var: str, base: type, null_class: type, command_factory=None):
    value = os.environ.get(env_var, "").strip()
    if not value or value.lower() == "none":
        return null_class()

    if value.lower() == "command":
        if command_factory is None:
            raise ProviderError(f"{env_var} : la valeur 'command' n'est valable que pour la voix.")
        return command_factory()

    if ":" not in value:
        raise ProviderError(
            f"{env_var} : valeur '{value}' invalide (attendu : none, command ou module.chemin:Classe)."
        )
    module_name, _, class_name = value.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise ProviderError(f"{env_var} : module '{module_name}' introuvable ({error}).") from error
    provider_class = getattr(module, class_name, None)
    if provider_class is None:
        raise ProviderError(f"{env_var} : classe '{class_name}' introuvable dans '{module_name}'.")
    if not (isinstance(provider_class, type) and issubclass(provider_class, base)):
        raise ProviderError(f"{env_var} : '{value}' n'est pas un {base.__name__}.")
    return provider_class()


def _command_narration_from_environment() -> CommandNarrationProvider:
    command = os.environ.get("TMS_NARRATION_COMMAND", "").strip()
    if not command:
        raise ProviderError(
            "TMS_NARRATION_PROVIDER=command exige TMS_NARRATION_COMMAND (commande de synthèse vocale)."
        )
    raw_timeout = os.environ.get("TMS_NARRATION_TIMEOUT", "").strip()
    if not raw_timeout:
        return CommandNarrationProvider(command)
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = 0.0
    if timeout <= 0:
        raise ProviderError(f"TMS_NARRATION_TIMEOUT : '{raw_timeout}' n'est pas un nombre de secondes positif.")
    return CommandNarrationProvider(command, timeout_seconds=timeout)


def get_narration_provider() -> NarrationProvider:
    return _load_provider(
        "TMS_NARRATION_PROVIDER", NarrationProvider, NullNarrationProvider,
        _command_narration_from_environment,
    )


def get_instruction_provider() -> InstructionProvider:
    return _load_provider("TMS_INSTRUCTION_PROVIDER", InstructionProvider, NullInstructionProvider)


def get_exercise_provider() -> ExerciseProvider:
    return _load_provider("TMS_EXERCISE_PROVIDER", ExerciseProvider, NullExerciseProvider)


def schedule_narration(instructions: list[dict], durations: list[float]) -> list[tuple[float, int]]:
    """Instant de départ de chaque consigne dite, sous la forme `(départ, indice)`.
    Une consigne démarre à son instant `t`, sauf si la précédente n'est pas finie :
    elle attend alors la fin de celle-ci plus GAP_SECONDS. Jamais de chevauchement,
    ordre conservé."""
    if len(instructions) != len(durations):
        raise ValueError("Il faut exactement une durée audio par consigne.")

    schedule: list[tuple[float, int]] = []
    previous_end = None
    for index, (instruction, duration) in enumerate(zip(instructions, durations)):
        start = instruction["t"]
        if previous_end is not None:
            start = max(start, previous_end + GAP_SECONDS)
        schedule.append((start, index))
        previous_end = start + duration
    return schedule
