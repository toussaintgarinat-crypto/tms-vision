import base64
import io
import subprocess
import sys
import textwrap
import wave

import pytest

from tms_vision import providers
from tms_vision.providers import (
    GAP_SECONDS,
    CommandNarrationProvider,
    ExerciseProvider,
    InstructionProvider,
    NarrationProvider,
    NullExerciseProvider,
    NullInstructionProvider,
    NullNarrationProvider,
    ProviderError,
    ProviderNotConfigured,
    get_exercise_provider,
    get_instruction_provider,
    get_narration_provider,
    schedule_narration,
    wav_duration_seconds,
)

ENV_VARS = (
    "TMS_NARRATION_PROVIDER", "TMS_INSTRUCTION_PROVIDER", "TMS_EXERCISE_PROVIDER",
    "TMS_NARRATION_COMMAND", "TMS_NARRATION_TIMEOUT",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_wav(seconds: float = 0.5, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


def python_command(script: str) -> str:
    """Commande « python -c <script> » sans shell, avec des chemins entre guillemets."""
    return f'"{sys.executable}" -c "{script}"'


# --- Valeurs par défaut : aucune IA ---------------------------------------------------

def test_by_default_no_provider_is_configured():
    assert isinstance(get_narration_provider(), NullNarrationProvider)
    assert isinstance(get_instruction_provider(), NullInstructionProvider)
    assert isinstance(get_exercise_provider(), NullExerciseProvider)


def test_the_value_none_selects_the_null_providers(monkeypatch):
    monkeypatch.setenv("TMS_NARRATION_PROVIDER", "none")
    monkeypatch.setenv("TMS_INSTRUCTION_PROVIDER", "none")
    monkeypatch.setenv("TMS_EXERCISE_PROVIDER", "NONE")

    assert isinstance(get_narration_provider(), NullNarrationProvider)
    assert isinstance(get_instruction_provider(), NullInstructionProvider)
    assert isinstance(get_exercise_provider(), NullExerciseProvider)


def test_null_narration_and_instruction_providers_produce_nothing():
    assert NullNarrationProvider().synthesize("Bonjour", "fr") is None
    assert NullInstructionProvider().rewrite({"id": "x"}, "fr") is None


def test_null_exercise_provider_refuses_to_propose():
    with pytest.raises(ProviderNotConfigured):
        NullExerciseProvider().propose("neck", {})


def test_providers_have_a_readable_name_for_metadata():
    assert NullNarrationProvider().name == "none"
    assert CommandNarrationProvider("echo").name == "command"


def test_default_path_imports_nothing_network_related():
    script = textwrap.dedent("""
        import sys
        before = set(sys.modules)
        import tms_vision.providers as p
        p.get_narration_provider(); p.get_instruction_provider(); p.get_exercise_provider()
        banned = ("socket", "ssl", "http", "urllib", "requests", "httpx")
        new = sorted(m for m in set(sys.modules) - before if m.split(".")[0] in banned)
        print(new)
    """)
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True,
        env={"PYTHONPATH": str(providers.__file__).rsplit("/tms_vision/", 1)[0], "PATH": ""},
    )

    assert result.stdout.strip() == "[]"


# --- Choix d'un fournisseur par la configuration --------------------------------------

class GoodNarration(NarrationProvider):
    name = "good"

    def synthesize(self, text, language):
        return make_wav()


class NotANarrationProvider:
    pass


def test_a_provider_class_can_be_loaded_by_module_path(monkeypatch):
    monkeypatch.setenv("TMS_NARRATION_PROVIDER", f"{__name__}:GoodNarration")

    provider = get_narration_provider()

    assert isinstance(provider, GoodNarration)
    assert provider.synthesize("x", "fr")[:4] == b"RIFF"


@pytest.mark.parametrize(
    "value, fragment",
    [
        ("pas_un_module_du_tout:Classe", "introuvable"),
        (f"{__name__}:ClasseInexistante", "ClasseInexistante"),
        (f"{__name__}:NotANarrationProvider", "NarrationProvider"),
        ("sans-deux-points", "module.chemin:Classe"),
    ],
)
def test_invalid_provider_configuration_names_the_variable(monkeypatch, value, fragment):
    monkeypatch.setenv("TMS_NARRATION_PROVIDER", value)

    with pytest.raises(ProviderError) as error:
        get_narration_provider()

    assert "TMS_NARRATION_PROVIDER" in str(error.value)
    assert fragment in str(error.value)


def test_the_command_value_is_only_valid_for_narration(monkeypatch):
    monkeypatch.setenv("TMS_INSTRUCTION_PROVIDER", "command")
    monkeypatch.setenv("TMS_EXERCISE_PROVIDER", "command")

    with pytest.raises(ProviderError, match="TMS_INSTRUCTION_PROVIDER"):
        get_instruction_provider()
    with pytest.raises(ProviderError, match="TMS_EXERCISE_PROVIDER"):
        get_exercise_provider()


def test_command_provider_requires_a_command(monkeypatch):
    monkeypatch.setenv("TMS_NARRATION_PROVIDER", "command")

    with pytest.raises(ProviderError, match="TMS_NARRATION_COMMAND"):
        get_narration_provider()


def test_command_provider_is_built_from_the_environment(monkeypatch):
    monkeypatch.setenv("TMS_NARRATION_PROVIDER", "command")
    monkeypatch.setenv("TMS_NARRATION_COMMAND", "echo")
    monkeypatch.setenv("TMS_NARRATION_TIMEOUT", "7")

    provider = get_narration_provider()

    assert isinstance(provider, CommandNarrationProvider)
    assert provider.timeout_seconds == 7


def test_invalid_timeout_is_rejected(monkeypatch):
    monkeypatch.setenv("TMS_NARRATION_PROVIDER", "command")
    monkeypatch.setenv("TMS_NARRATION_COMMAND", "echo")
    monkeypatch.setenv("TMS_NARRATION_TIMEOUT", "abc")

    with pytest.raises(ProviderError, match="TMS_NARRATION_TIMEOUT"):
        get_narration_provider()


# --- Fournisseur de voix par commande locale ------------------------------------------

def test_command_provider_sends_the_text_on_stdin_and_reads_a_wav_from_stdout():
    wav_b64 = base64.b64encode(make_wav(0.5)).decode()
    # Le texte reçu est vérifié : la commande échoue si stdin n'est pas « Bonjour ».
    script = (
        "import sys,base64;"
        "assert sys.stdin.read()=='Bonjour', 'texte inattendu';"
        f"sys.stdout.buffer.write(base64.b64decode('{wav_b64}'))"
    )

    audio = CommandNarrationProvider(python_command(script)).synthesize("Bonjour", "fr")

    assert audio[:4] == b"RIFF"
    assert wav_duration_seconds(audio) == pytest.approx(0.5, abs=0.01)


def test_command_provider_passes_the_language_through_the_environment():
    wav_b64 = base64.b64encode(make_wav()).decode()
    script = (
        "import os,sys,base64;"
        "assert os.environ['TMS_NARRATION_LANGUAGE']=='fr';"
        f"sys.stdout.buffer.write(base64.b64decode('{wav_b64}'))"
    )

    assert CommandNarrationProvider(python_command(script)).synthesize("x", "fr")


def test_command_provider_does_not_use_a_shell():
    # Avec un shell, « ; echo injecté » serait exécuté ; sans shell c'est un argument.
    wav_b64 = base64.b64encode(make_wav()).decode()
    script = f"import sys,base64;sys.stdout.buffer.write(base64.b64decode('{wav_b64}'))"
    provider = CommandNarrationProvider(python_command(script) + " ; echo injecte")

    audio = provider.synthesize("x", "fr")

    assert b"injecte" not in audio


def test_command_provider_reports_a_non_zero_exit_code_with_the_error_output():
    provider = CommandNarrationProvider(
        python_command("import sys;sys.stderr.write('voix indisponible');sys.exit(3)")
    )

    with pytest.raises(ProviderError) as error:
        provider.synthesize("x", "fr")

    assert "3" in str(error.value)
    assert "voix indisponible" in str(error.value)


def test_command_provider_reports_a_timeout():
    provider = CommandNarrationProvider(python_command("import time;time.sleep(30)"), timeout_seconds=1)

    with pytest.raises(ProviderError, match="délai"):
        provider.synthesize("x", "fr")


def test_command_provider_rejects_output_that_is_not_a_wav():
    provider = CommandNarrationProvider(python_command("print('pas du wav')"))

    with pytest.raises(ProviderError, match="WAV"):
        provider.synthesize("x", "fr")


def test_command_provider_rejects_an_empty_output():
    with pytest.raises(ProviderError, match="WAV"):
        CommandNarrationProvider(python_command("pass")).synthesize("x", "fr")


def test_command_provider_reports_a_missing_executable():
    with pytest.raises(ProviderError, match="introuvable"):
        CommandNarrationProvider("commande-qui-nexiste-pas-xyz").synthesize("x", "fr")


def test_wav_duration_reads_the_header():
    assert wav_duration_seconds(make_wav(1.5)) == pytest.approx(1.5, abs=0.01)
    with pytest.raises(ProviderError):
        wav_duration_seconds(b"pas un wav")


# --- Planification de la voix ---------------------------------------------------------

def _instructions(*times):
    return [{"t": t, "text": f"consigne {i}"} for i, t in enumerate(times)]


def test_narration_keeps_each_start_time_when_everything_fits():
    schedule = schedule_narration(_instructions(0, 10, 25), [3.0, 4.0, 5.0])

    assert schedule == [(0, 0), (10, 1), (25, 2)]


def test_narration_delays_a_segment_that_would_overlap_the_previous_one():
    # La consigne 0 dure 6 s : la consigne 1, prévue à t=4, attend la fin + l'écart.
    schedule = schedule_narration(_instructions(0, 4, 5), [6.0, 2.0, 1.0])

    assert schedule[0] == (0, 0)
    assert schedule[1] == (6.0 + GAP_SECONDS, 1)
    assert schedule[2] == (6.0 + GAP_SECONDS + 2.0 + GAP_SECONDS, 2)


def test_narration_never_overlaps_and_keeps_the_order():
    durations = [5.0, 5.0, 5.0, 5.0]
    schedule = schedule_narration(_instructions(0, 1, 2, 3), durations)

    assert [index for _, index in schedule] == [0, 1, 2, 3]
    for (start, index), (next_start, _) in zip(schedule, schedule[1:]):
        assert next_start >= start + durations[index]


def test_narration_schedule_is_empty_without_instructions():
    assert schedule_narration([], []) == []


def test_narration_requires_one_duration_per_instruction():
    with pytest.raises(ValueError):
        schedule_narration(_instructions(0, 5), [1.0])
