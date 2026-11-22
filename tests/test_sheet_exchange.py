"""Échange de fiches entre installations : export et import d'un fichier. Règles : l'import crée de
NOUVELLES fiches sans validation, appartenant à l'importateur, avec l'auteur déclaré par le fichier ;
rien de lié à un compte ne voyage ; un fichier modifié ou invalide est revérifié et refusé."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from tms_vision import accounts, auth_api, exercises, sheets, storage, validation
from tms_vision.api import app

GOOD = "correct horse battery"
ORIGIN = {"Origin": "http://testserver"}
FORMULA = validation.FORMULAS["fr"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    monkeypatch.delenv("TMS_REQUIRE_AUTH", raising=False)
    auth_api.reset_cache()
    accounts.create_user("lea@x.fr", "Léa Osteo", GOOD, ["osteopathe"])
    accounts.create_user("paul@x.fr", "Paul Autre", GOOD, ["osteopathe"])
    accounts.create_user("prat@x.fr", "Prat", GOOD, ["praticien"])
    yield TestClient(app)
    auth_api.reset_cache()


def _login(client, email):
    client.cookies.clear()
    assert client.post("/auth/login", json={"email": email, "password": GOOD}, headers=ORIGIN).status_code == 200


def _mine(client):
    base = next(e for e in exercises.load_catalog() if not e.get("fiche") and e["zone"] == "neck")
    created = client.post(f"/exercises/{base['id']}/copy", headers=ORIGIN).json()
    return created["id"]


def _export(client, ids):
    response = client.get("/sheets/export", params={"ids": ",".join(ids)})
    assert response.status_code == 200, response.text
    return response.json()


def _import(client, bundle):
    return client.post("/sheets/import", json=bundle, headers=ORIGIN)


def test_export_contains_the_content_and_the_author_but_nothing_account_related(client):
    _login(client, "lea@x.fr")
    sheet_id = _mine(client)
    response = client.get("/sheets/export", params={"ids": sheet_id})
    assert "attachment" in response.headers["content-disposition"]
    bundle = response.json()
    assert bundle["format"] == "tms-vision-fiches" and bundle["version"] == 1
    [entry] = bundle["sheets"]
    assert set(entry["content"]) <= set(sheets.EDITABLE_KEYS)
    assert entry["original_author"] == validation.DEFAULT_AUTHOR
    dumped = json.dumps(bundle)
    for forbidden in ("lea@x.fr", "Léa Osteo", "validated_by", "owner", "fingerprint", "formula"):
        assert forbidden not in dumped


def test_a_colleague_imports_a_new_unvalidated_sheet_with_the_declared_author(client):
    _login(client, "lea@x.fr")
    fiche = next(e for e in exercises.load_catalog() if e.get("fiche"))
    bundle = _export(client, [fiche["id"]])
    assert bundle["sheets"][0]["original_author"] == "Théo MARTIN"
    _login(client, "paul@x.fr")
    response = _import(client, bundle)
    assert response.status_code == 200 and response.json()["imported"] == 1
    new_id = response.json()["report"][0]["id"]
    assert new_id != fiche["id"]
    state = client.get(f"/exercises/{new_id}/validation").json()
    assert state["created_by"] == "Théo MARTIN" and state["imported"] is True
    assert state["validated_by"] is None and state["can_edit"] is True  # à lui, à revalider
    assert [s["id"] for s in client.get("/sheets/mine").json()] == [new_id]


def test_validation_does_not_travel_with_the_file(client):
    _login(client, "lea@x.fr")
    sheet_id = _mine(client)
    state = client.get(f"/exercises/{sheet_id}/validation").json()
    client.post(
        f"/exercises/{sheet_id}/validate", headers=ORIGIN,
        json={"fingerprint": state["fingerprint"], "formula": FORMULA, "animation_completed": True},
    )
    bundle = _export(client, [sheet_id])
    bundle["sheets"][0]["content"]["title"] = "Venue d'un autre cabinet"  # pas un doublon ici
    _login(client, "paul@x.fr")
    new_id = _import(client, bundle).json()["report"][0]["id"]
    assert client.get(f"/exercises/{new_id}/validation").json()["validated_by"] is None


def test_importing_the_same_file_twice_creates_no_duplicate(client):
    _login(client, "lea@x.fr")
    bundle = _export(client, [_mine(client)])
    bundle["sheets"][0]["content"]["title"] = "Importée une seule fois"
    _login(client, "paul@x.fr")
    first = _import(client, bundle).json()
    second = _import(client, bundle).json()
    assert first["imported"] == 1 and second["imported"] == 0
    assert second["report"][0]["status"] == "duplicate"
    assert len(client.get("/sheets/mine").json()) == 1


def test_importing_back_into_the_same_installation_is_a_duplicate(client):
    _login(client, "lea@x.fr")
    sheet_id = _mine(client)
    report = _import(client, _export(client, [sheet_id])).json()["report"]
    assert report == [{"title": validation.get_exercise(sheet_id)["title"], "status": "duplicate", "id": sheet_id}]


def test_a_tampered_sheet_is_rechecked_and_refused_without_blocking_the_others(client):
    _login(client, "lea@x.fr")
    a, b = _mine(client), _mine(client)
    bundle = _export(client, [a, b])
    bundle["sheets"][0]["content"]["duration_seconds"] = 9999
    bundle["sheets"][1]["content"]["title"] = "Titre modifié avant l'envoi"
    _login(client, "paul@x.fr")
    response = _import(client, bundle).json()
    assert [r["status"] for r in response["report"]] == ["invalid", "imported"]
    assert "duration_seconds" in response["report"][0]["error"]


@pytest.mark.parametrize(
    "forbidden", [{"status": "validated"}, {"validated_by": "Théo"}, {"fiche": "Fiche de Moi"}, {"source": "ai"}, {"id": "x"}]
)
def test_a_file_cannot_smuggle_a_validation_or_a_badge(client, forbidden):
    _login(client, "lea@x.fr")
    bundle = _export(client, [_mine(client)])
    entry = copy.deepcopy(bundle["sheets"][0])
    entry["content"].update(forbidden)
    entry["content"]["title"] = "Fiche piégée"
    _login(client, "paul@x.fr")
    result = _import(client, {**bundle, "sheets": [entry]}).json()
    if "id" in forbidden:  # l'id du fichier est ignoré : un nouvel id est toujours généré
        assert result["report"][0]["status"] == "imported" and result["report"][0]["id"] != "x"
    else:
        assert result["report"][0]["status"] == "invalid"


@pytest.mark.parametrize(
    "bundle",
    [{}, {"format": "autre", "version": 1, "sheets": [{}]}, {"format": "tms-vision-fiches", "version": 2, "sheets": [{}]},
     {"format": "tms-vision-fiches", "version": 1, "sheets": []}, {"format": "tms-vision-fiches", "version": 1, "sheets": "x"}],
)
def test_a_file_that_is_not_a_valid_exchange_file_is_refused(client, bundle):
    _login(client, "lea@x.fr")
    assert _import(client, bundle).status_code == 422


def test_the_declared_author_is_cleaned_and_defaults_when_missing(client):
    _login(client, "lea@x.fr")
    bundle = _export(client, [_mine(client)])
    bundle["sheets"][0]["original_author"] = "  Dr\x00 Quelqu'un\n" + "x" * 500
    bundle["sheets"][0]["content"]["title"] = "Titre d'ailleurs"
    _login(client, "paul@x.fr")
    new_id = _import(client, bundle).json()["report"][0]["id"]
    author = client.get(f"/exercises/{new_id}/validation").json()["created_by"]
    assert author.startswith("Dr Quelqu'un") and len(author) <= 120 and "\x00" not in author
    del bundle["sheets"][0]["original_author"]
    bundle["sheets"][0]["content"]["title"] = "Autre titre"
    other = _import(client, bundle).json()["report"][0]["id"]
    assert client.get(f"/exercises/{other}/validation").json()["created_by"] == sheets.UNKNOWN_AUTHOR


@pytest.mark.parametrize("email", ["prat@x.fr"])
def test_only_osteopaths_export_and_import(client, email):
    _login(client, "lea@x.fr")
    bundle = _export(client, [_mine(client)])
    _login(client, email)
    assert client.get("/sheets/export", params={"ids": "x"}).status_code == 403
    assert _import(client, bundle).status_code == 403
    client.cookies.clear()
    assert _import(client, bundle).status_code == 401


def test_export_asks_for_known_sheets(client):
    _login(client, "lea@x.fr")
    assert client.get("/sheets/export", params={"ids": ""}).status_code == 422
    assert client.get("/sheets/export", params={"ids": "nope"}).status_code == 404


def test_export_all_my_sheets_or_the_whole_catalog_in_one_file(client):
    _login(client, "lea@x.fr")
    first, second = _mine(client), _mine(client)
    client.post(f"/exercises/{second}/archive", headers=ORIGIN)
    mine = client.get("/sheets/export", params={"scope": "mine"}).json()
    assert len(mine["sheets"]) == 1  # l'archivée n'est pas exportée
    everything = client.get("/sheets/export", params={"scope": "all"}).json()
    catalog = validation.load_effective_catalog()
    assert len(everything["sheets"]) == len(catalog)
    assert len(catalog) > 200  # le catalogue dépasse l'ancienne limite : tout part en un seul fichier
    assert validation.get_exercise(first)["title"] in {e["content"]["title"] for e in everything["sheets"]}
    assert client.get("/sheets/export", params={"scope": "tout"}).status_code == 422


def test_several_sheets_selected_in_one_file_are_imported_together(client):
    _login(client, "lea@x.fr")
    ids = [_mine(client) for _ in range(3)]
    bundle = _export(client, ids)
    for index, entry in enumerate(bundle["sheets"]):
        entry["content"]["title"] = f"Lot {index}"
    _login(client, "paul@x.fr")
    result = _import(client, bundle).json()
    assert result["imported"] == 3
    assert len(client.get("/sheets/mine").json()) == 3


def test_a_whole_catalog_file_imports_the_sheets_not_already_present(client):
    _login(client, "lea@x.fr")
    bundle = client.get("/sheets/export", params={"scope": "all"}).json()
    # même installation : tout est déjà là, rien ne se duplique (les fiches d'origine portent un badge
    # `fiche` que l'export retire : elles sont importées comme copies de cabinet, une fois).
    first = _import(client, bundle).json()
    second = _import(client, bundle).json()
    assert second["imported"] == 0
    assert first["imported"] + sum(1 for r in first["report"] if r["status"] == "duplicate") == len(bundle["sheets"])
