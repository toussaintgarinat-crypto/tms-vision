import copy
import json
import re
from pathlib import Path

import pytest

from tms_vision import metiers

TASK_FORM = Path(__file__).resolve().parents[1] / "web" / "app" / "bilans" / "taskForm.ts"


def _options(name: str) -> set[str]:
    source = TASK_FORM.read_text(encoding="utf-8")
    block = re.search(rf"export const {name} = \[(.*?)\] as const;", source, re.S).group(1)
    return set(re.findall(r'"([^"]+)"', block))


def _model(**overrides) -> dict:
    return {
        "id": "test-metier", "title": "Test", "description": "Un métier de test.",
        "domain": "tertiaire-autres", "status": "draft", "source": "human", "validated_by": None, "validated_on": None,
        "workday_hours": 8,
        "tasks": [{"name": "Tâche", "zones": ["neck"], "activity_hours": 2.0}],
        **overrides,
    }


def test_the_shipped_library_is_valid_and_complete():
    library = metiers.load_library()

    assert len(library) >= 10
    assert len({model["id"] for model in library}) == len(library)
    # Rien ne se présente comme validé sans avoir été relu par un professionnel.
    assert all(model["status"] == "draft" for model in library)
    assert all(model["source"] == "ai" or model["validated_by"] for model in library)


def test_library_domains_match_the_page_labels_and_each_one_has_jobs():
    source = (Path(__file__).resolve().parents[1] / "web" / "app" / "metiers" / "types.ts")
    block = re.search(r"DOMAIN_LABELS[^{]*\{(.*?)\};", source.read_text(encoding="utf-8"), re.S)
    labelled = set(re.findall(r'"([a-z-]+)":', block.group(1)))

    assert labelled == set(metiers.DOMAINS)
    assert {model["domain"] for model in metiers.load_library()} == set(metiers.DOMAINS)


def test_library_workstations_and_breaks_match_the_task_form_lists():
    workstations = _options("WORKSTATION_OPTIONS")
    breaks = _options("BREAK_OPTIONS")
    for model in metiers.load_library():
        for task in model["tasks"]:
            assert task.get("workstation") in workstations, (model["id"], task["name"])
            assert task.get("breaks") in breaks, (model["id"], task["name"])


def test_library_covers_sitting_and_standing_jobs():
    stations = {
        task["workstation"] for model in metiers.load_library() for task in model["tasks"]
    }
    assert {"Assis devant écran", "Conduite", "Manutention et port de charges"} <= stations


def test_validate_model_accepts_a_minimal_model_and_normalizes_tasks():
    model = _model(tasks=[{"name": " Tâche ", "zones": ["neck", "neck"], "activity_hours": 2}])

    clean = metiers.validate_model(model)

    assert clean["tasks"] == [{"name": "Tâche", "zones": ["neck"], "activity_hours": 2}]


@pytest.mark.parametrize("change, message", [
    ({"id": "Mauvais Id"}, "id"),
    ({"domain": "autre"}, "domain"),
    ({"status": "ok"}, "status"),
    ({"source": "robot"}, "source"),
    ({"workday_hours": 0}, "workday_hours"),
    ({"workday_hours": 25}, "workday_hours"),
    ({"tasks": []}, "tasks"),
    ({"status": "validated"}, "validated_by"),
    ({"tasks": [{"name": "", "zones": ["neck"], "activity_hours": 1}]}, "nom"),
    ({"tasks": [{"name": "A", "zones": [], "activity_hours": 1}]}, "zones"),
    ({"tasks": [{"name": "A", "zones": ["knee"], "activity_hours": 1}]}, "zones"),
    ({"tasks": [{"name": "A", "zones": ["neck"], "activity_hours": 0}]}, "activity_hours"),
    ({"tasks": [{"name": "A", "zones": ["neck"], "activity_hours": 1, "load_kg": -1}]}, "load_kg"),
    ({"tasks": [{"name": "A", "zones": ["neck"], "activity_hours": 1, "x": 1}]}, "inconnus"),
    ({"tasks": [{"name": "A", "zones": ["neck"], "activity_hours": 1,
                 "zone_cycles": {"hand": 3}}]}, "zone_cycles"),
    ({"workday_hours": 2, "tasks": [{"name": "A", "zones": ["neck"], "activity_hours": 3}]},
     "dépassent"),
])
def test_validate_model_rejects_bad_models(change, message):
    with pytest.raises(ValueError, match=message):
        metiers.validate_model(_model(**change))


def test_load_library_names_the_faulty_file(tmp_path):
    (tmp_path / "bon.json").write_text(json.dumps(_model(id="bon")), encoding="utf-8")
    (tmp_path / "mauvais.json").write_text(json.dumps(_model(id="mauvais", tasks=[])),
                                            encoding="utf-8")

    with pytest.raises(ValueError, match="mauvais.json"):
        metiers.load_library(tmp_path)


def test_load_library_requires_the_id_to_match_the_file_name(tmp_path):
    (tmp_path / "autre.json").write_text(json.dumps(_model(id="test-metier")), encoding="utf-8")

    with pytest.raises(ValueError, match="nom du fichier"):
        metiers.load_library(tmp_path)


def test_task_to_stored_applies_one_frequency_to_every_zone_and_allows_overrides():
    task = {"name": "A", "zones": ["neck", "hand"], "activity_hours": 2, "cycles_per_minute": 10,
            "zone_cycles": {"hand": 30}, "load_kg": 3}

    stored = metiers.task_to_stored(copy.deepcopy(task))

    assert stored["zone_cycles"] == {"neck": 10, "hand": 30}
    assert stored["load_kg"] == 3
    assert stored["analysis_id"] is None
    assert stored["source"] == "practitioner"
