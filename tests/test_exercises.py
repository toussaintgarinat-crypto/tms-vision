import copy
import json
from pathlib import Path

import pytest

from tms_vision import exercises
from tms_vision.exercises import (
    BONES,
    REGIONS,
    ZONES,
    load_catalog,
    load_exercise,
    validate_exercise,
)


def _valid():
    return {
        "id": "neck-test",
        "zone": "neck",
        "title": "Étirement de test",
        "description": "Description de test.",
        "status": "draft",
        "source": "human",
        "validated_by": None,
        "validated_on": None,
        "view": "front",
        "target_segments": ["neck"],
        "poses": {
            "neutral": {},
            "tilt_right": {"neck": {"lateral": 30}},
        },
        "keyframes": [
            {"t": 0, "pose": "neutral"},
            {"t": 8, "pose": "tilt_right"},
            {"t": 20, "pose": "neutral"},
        ],
        "instructions": [{"t": 0, "text": "Debout."}, {"t": 8, "text": "Inclinez."}],
        "duration_seconds": 30,
    }


def _write(directory, data, name=None):
    path = Path(directory) / f"{name or data['id']}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_valid_exercise_passes():
    validate_exercise(_valid())


def _mutate(path, value):
    data = _valid()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return data


INVALID_CASES = {
    "uppercase id": (_mutate(["id"], "Neck_Test"), "id"),
    "unknown zone": (_mutate(["zone"], "knee"), "zone"),
    "unknown status": (_mutate(["status"], "published"), "status"),
    "unknown source": (_mutate(["source"], "robot"), "source"),
    "unknown view": (_mutate(["view"], "top"), "view"),
    "empty title": (_mutate(["title"], "  "), "title"),
    "empty description": (_mutate(["description"], ""), "description"),
    "no target segment": (_mutate(["target_segments"], []), "target_segments"),
    "unknown target segment": (_mutate(["target_segments"], ["knee"]), "target_segments"),
    "duplicated target segment": (_mutate(["target_segments"], ["neck", "neck"]), "target_segments"),
    "unknown bone": (_mutate(["poses", "tilt_right"], {"tail": {"lateral": 5}}), "tail"),
    "unknown angle key": (_mutate(["poses", "tilt_right"], {"neck": {"roll": 5}}), "roll"),
    "angle too large": (_mutate(["poses", "tilt_right"], {"neck": {"lateral": 181}}), "lateral"),
    "angle not a number": (_mutate(["poses", "tilt_right"], {"neck": {"lateral": "30"}}), "lateral"),
    "angle is a boolean": (_mutate(["poses", "tilt_right"], {"neck": {"lateral": True}}), "lateral"),
    "keyframe on unknown pose": (
        _mutate(["keyframes"], [{"t": 0, "pose": "neutral"}, {"t": 5, "pose": "ghost"}]), "ghost"),
    "single keyframe": (_mutate(["keyframes"], [{"t": 0, "pose": "neutral"}]), "keyframes"),
    "first keyframe not at zero": (
        _mutate(["keyframes"], [{"t": 1, "pose": "neutral"}, {"t": 5, "pose": "tilt_right"}]), "keyframes"),
    "keyframes not increasing": (
        _mutate(["keyframes"], [{"t": 0, "pose": "neutral"}, {"t": 5, "pose": "tilt_right"},
                                {"t": 5, "pose": "neutral"}]), "keyframes"),
    "last keyframe after duration": (
        _mutate(["keyframes"], [{"t": 0, "pose": "neutral"}, {"t": 31, "pose": "tilt_right"}]), "keyframes"),
    "no instruction": (_mutate(["instructions"], []), "instructions"),
    "empty instruction text": (_mutate(["instructions"], [{"t": 0, "text": " "}]), "instructions"),
    "instructions not increasing": (
        _mutate(["instructions"], [{"t": 5, "text": "a"}, {"t": 2, "text": "b"}]), "instructions"),
    "instruction after duration": (
        _mutate(["instructions"], [{"t": 0, "text": "a"}, {"t": 99, "text": "b"}]), "instructions"),
    "duration too short": (_mutate(["duration_seconds"], 5), "duration_seconds"),
    "duration too long": (_mutate(["duration_seconds"], 181), "duration_seconds"),
    "validated without reviewer": (
        {**_valid(), "status": "validated", "validated_on": "2026-10-21"}, "validated_by"),
    "validated without date": (
        {**_valid(), "status": "validated", "validated_by": "Dr Martin"}, "validated_on"),
    "validated with bad date": (
        {**_valid(), "status": "validated", "validated_by": "Dr Martin", "validated_on": "hier"},
        "validated_on"),
}


@pytest.mark.parametrize("case", INVALID_CASES, ids=list(INVALID_CASES))
def test_invalid_exercises_raise_value_error_naming_the_problem(case):
    data, expected_word = INVALID_CASES[case]

    with pytest.raises(ValueError) as error:
        validate_exercise(data)

    assert expected_word in str(error.value)


def test_missing_required_key_is_reported():
    data = _valid()
    del data["poses"]

    with pytest.raises(ValueError, match="poses"):
        validate_exercise(data)


def test_unknown_top_level_key_is_rejected_to_catch_typos():
    data = {**_valid(), "titel": "faute de frappe"}

    with pytest.raises(ValueError, match="titel"):
        validate_exercise(data)


def test_validated_exercise_with_reviewer_and_date_passes():
    validate_exercise(
        {**_valid(), "status": "validated", "validated_by": "Dr Martin", "validated_on": "2026-10-21"}
    )


def test_ai_exercise_is_rejected_outside_the_drafts_directory():
    with pytest.raises(ValueError, match="drafts"):
        validate_exercise({**_valid(), "source": "ai"})


def test_ai_exercise_is_accepted_inside_the_drafts_directory():
    validate_exercise({**_valid(), "source": "ai"}, in_drafts=True)


def test_id_must_match_the_file_name():
    with pytest.raises(ValueError, match="nom du fichier"):
        validate_exercise(_valid(), filename_stem="autre-nom")


def test_load_exercise_reads_validates_and_returns_the_definition(tmp_path):
    path = _write(tmp_path, _valid())

    assert load_exercise(path)["title"] == "Étirement de test"


def test_load_exercise_reports_the_file_name_on_invalid_json(tmp_path):
    path = tmp_path / "neck-test.json"
    path.write_text("{ pas du json", encoding="utf-8")

    with pytest.raises(ValueError, match="neck-test.json"):
        load_exercise(path)


def test_load_exercise_treats_a_drafts_directory_as_drafts(tmp_path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    path = _write(drafts, {**_valid(), "source": "ai"})

    assert load_exercise(path)["source"] == "ai"


def test_load_catalog_sorts_by_id_and_ignores_the_drafts_directory(tmp_path):
    _write(tmp_path, {**_valid(), "id": "neck-b"})
    _write(tmp_path, {**_valid(), "id": "neck-a"})
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    _write(drafts, {**_valid(), "id": "neck-draft", "source": "ai"})

    catalog = load_catalog(tmp_path)

    assert [exercise["id"] for exercise in catalog] == ["neck-a", "neck-b"]


def test_load_catalog_rejects_an_ai_exercise_placed_outside_drafts(tmp_path):
    _write(tmp_path, {**_valid(), "source": "ai"})

    with pytest.raises(ValueError, match="drafts"):
        load_catalog(tmp_path)


def test_load_catalog_names_the_invalid_file(tmp_path):
    _write(tmp_path, {**_valid(), "zone": "knee"})

    with pytest.raises(ValueError, match="neck-test.json"):
        load_catalog(tmp_path)


def test_the_whole_body_has_a_skeleton_of_23_bones_besides_the_root():
    assert len(BONES) == 23
    assert set(ZONES) < set(REGIONS)
    assert {"head", "L_hand", "R_fingers", "L_thumb", "R_shin", "L_foot", "R_toes", "L_clavicle"} <= set(BONES)


def test_a_pose_may_use_the_new_bones_and_the_twist_angle():
    data = _mutate(
        ["poses", "tilt_right"],
        {"head": {"twist": 40}, "R_hand": {"flexion": -60, "lateral": 10}, "L_foot": {"flexion": 20}},
    )
    data["zone"] = "head"
    data["target_segments"] = ["head", "hand", "foot"]

    validate_exercise(data)


def test_a_twist_angle_is_bounded_like_the_other_angles():
    data = _mutate(["poses", "tilt_right"], {"neck": {"twist": 181}})

    with pytest.raises(ValueError, match="twist"):
        validate_exercise(data)


def test_shipped_exercises_are_valid_cover_every_region_and_are_unvalidated_drafts():
    catalog = load_catalog()

    assert {exercise["zone"] for exercise in catalog} == set(REGIONS)
    for exercise in catalog:
        assert exercise["status"] == "draft", exercise["id"]
        assert exercise["source"] == "human", exercise["id"]
        assert exercise["validated_by"] is None, exercise["id"]
        assert exercise["zone"] in exercise["target_segments"], exercise["id"]


def test_shipped_exercise_files_do_not_mutate_between_loads():
    first = load_catalog()
    second = load_catalog()

    assert first == second
    assert copy.deepcopy(first) == first


def test_exercises_directory_has_a_drafts_folder_for_ai_proposals():
    assert (exercises.EXERCISES_DIR / "drafts").is_dir()


# --- Propositions d'une IA : toujours des brouillons, jamais au catalogue ------------------

from tms_vision.exercises import main as exercises_main  # noqa: E402
from tms_vision.exercises import propose_draft  # noqa: E402
from tms_vision.providers import ExerciseProvider, NullExerciseProvider, ProviderNotConfigured  # noqa: E402


class FakeExerciseProvider(ExerciseProvider):
    name = "fake"

    def __init__(self, proposal=None):
        self.proposal = proposal
        self.calls = []

    def propose(self, zone, constraints):
        self.calls.append((zone, constraints))
        return copy.deepcopy(self.proposal) if self.proposal is not None else _valid()


@pytest.fixture
def exercises_dir(tmp_path):
    (tmp_path / "drafts").mkdir()
    return tmp_path


def test_propose_without_a_configured_provider_fails_and_writes_nothing(exercises_dir):
    with pytest.raises(ProviderNotConfigured):
        propose_draft("neck", NullExerciseProvider(), directory=exercises_dir)

    assert list((exercises_dir / "drafts").iterdir()) == []


def test_propose_forces_the_draft_status_whatever_the_provider_says(exercises_dir):
    hostile = {**_valid(), "id": "neck-ai", "source": "human", "status": "validated",
               "validated_by": "Dr Fictif", "validated_on": "2026-10-21"}

    path = propose_draft("neck", FakeExerciseProvider(hostile), directory=exercises_dir)

    written = json.loads(path.read_text(encoding="utf-8"))
    assert path == exercises_dir / "drafts" / "neck-ai.json"
    assert written["source"] == "ai"
    assert written["status"] == "draft"
    assert written["validated_by"] is None
    assert written["validated_on"] is None
    validate_exercise(written, in_drafts=True)


def test_a_proposal_never_enters_the_catalog(exercises_dir):
    propose_draft("neck", FakeExerciseProvider({**_valid(), "id": "neck-ai"}), directory=exercises_dir)

    assert load_catalog(exercises_dir) == []


def test_the_provider_receives_the_zone_and_constraints(exercises_dir):
    provider = FakeExerciseProvider({**_valid(), "id": "neck-ai"})

    propose_draft("neck", provider, {"max_duration": 30}, directory=exercises_dir)

    assert provider.calls == [("neck", {"max_duration": 30})]


def test_an_unknown_zone_is_rejected_before_calling_the_provider(exercises_dir):
    provider = FakeExerciseProvider()

    with pytest.raises(ValueError, match="zone"):
        propose_draft("knee", provider, directory=exercises_dir)

    assert provider.calls == []


def test_an_invalid_proposal_is_rejected_and_nothing_is_written(exercises_dir):
    broken = {**_valid(), "id": "neck-ai", "keyframes": []}

    with pytest.raises(ValueError, match="keyframes"):
        propose_draft("neck", FakeExerciseProvider(broken), directory=exercises_dir)

    assert list((exercises_dir / "drafts").iterdir()) == []


def test_a_proposal_for_another_zone_than_requested_is_rejected(exercises_dir):
    with pytest.raises(ValueError, match="zone"):
        propose_draft("trunk", FakeExerciseProvider({**_valid(), "id": "neck-ai"}), directory=exercises_dir)


def test_a_proposal_that_is_not_an_object_is_rejected(exercises_dir):
    class Bad(ExerciseProvider):
        def propose(self, zone, constraints):
            return "pas un dictionnaire"

    with pytest.raises(ValueError):
        propose_draft("neck", Bad(), directory=exercises_dir)


def test_a_proposal_never_overwrites_an_existing_draft_or_catalog_exercise(exercises_dir):
    _write(exercises_dir, {**_valid(), "id": "neck-taken"})
    existing_draft = _write(exercises_dir / "drafts", {**_valid(), "id": "neck-old", "source": "ai"})
    before = existing_draft.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="existe déjà"):
        propose_draft("neck", FakeExerciseProvider({**_valid(), "id": "neck-taken"}), directory=exercises_dir)
    with pytest.raises(ValueError, match="existe déjà"):
        propose_draft("neck", FakeExerciseProvider({**_valid(), "id": "neck-old"}), directory=exercises_dir)

    assert existing_draft.read_text(encoding="utf-8") == before


def test_cli_propose_fails_clearly_without_a_provider(monkeypatch, exercises_dir, capsys):
    monkeypatch.setattr(exercises, "EXERCISES_DIR", exercises_dir)
    monkeypatch.delenv("TMS_EXERCISE_PROVIDER", raising=False)

    assert exercises_main(["propose", "--zone", "neck"]) == 1
    assert "TMS_EXERCISE_PROVIDER" in capsys.readouterr().err


def test_cli_propose_writes_a_draft_with_a_configured_provider(monkeypatch, exercises_dir, capsys):
    monkeypatch.setattr(exercises, "EXERCISES_DIR", exercises_dir)
    monkeypatch.setenv("TMS_EXERCISE_PROVIDER", f"{__name__}:CliProvider")

    assert exercises_main(["propose", "--zone", "neck"]) == 0

    assert (exercises_dir / "drafts" / "neck-cli.json").exists()
    assert "neck-cli.json" in capsys.readouterr().out


def test_cli_requires_a_known_command_and_zone(capsys):
    assert exercises_main([]) == 2
    assert exercises_main(["propose", "--zone", "knee"]) == 2


class CliProvider(ExerciseProvider):
    def propose(self, zone, constraints):
        return {**_valid(), "id": "neck-cli"}


def test_position_is_optional_and_must_be_known():
    data = _valid()
    validate_exercise(data)  # sans `position` : debout par défaut
    for position in ("standing", "seated", "lying"):
        validate_exercise({**data, "position": position})
    with pytest.raises(ValueError, match="position"):
        validate_exercise({**data, "position": "accroupi"})


def test_shipped_exercises_declare_a_known_position_and_include_seated_and_lying_ones():
    positions = {
        exercise.get("position", exercises.DEFAULT_POSITION) for exercise in load_catalog()
    }
    assert positions == {"standing", "seated", "lying"}


def test_every_shipped_exercise_says_what_it_brings_and_a_blank_benefit_is_rejected():
    catalog = load_catalog()

    assert catalog and all(exercise.get("benefit", "").strip() for exercise in catalog)
    with pytest.raises(ValueError, match="benefit"):
        validate_exercise({**_valid(), "benefit": "  "})
