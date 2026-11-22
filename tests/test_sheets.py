"""Phases 3 et 4 : copier, modifier, créer et archiver des fiches. Un test par règle de la section 5
du plan, dont les cas d'abus (une copie qui réécrit l'auteur d'origine, un confrère qui modifie la
fiche d'un autre, une validation qui survit à une modification)."""
import pytest
from fastapi.testclient import TestClient

from tms_vision import accounts, auth_api, exercises, storage, validation
from tms_vision.api import app

GOOD = "correct horse battery"
ORIGIN = {"Origin": "http://testserver"}
FORMULA = validation.FORMULAS["fr"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    monkeypatch.delenv("TMS_REQUIRE_AUTH", raising=False)
    auth_api.reset_cache()
    accounts.create_user("admin@x.fr", "Admin", GOOD, ["administrateur"])
    accounts.create_user("lea@x.fr", "Léa Osteo", GOOD, ["osteopathe"])
    accounts.create_user("paul@x.fr", "Paul Autre", GOOD, ["osteopathe"])
    accounts.create_user("prat@x.fr", "Prat", GOOD, ["praticien"])
    yield TestClient(app)
    auth_api.reset_cache()


def _login(client, email):
    client.cookies.clear()
    response = client.post("/auth/login", json={"email": email, "password": GOOD}, headers=ORIGIN)
    assert response.status_code == 200, response.text


def _fiche():
    return next(e for e in exercises.load_catalog() if e.get("fiche"))


def _plain():
    # Zone mesurée (RULA), pour que les programmes de bilan puissent la proposer.
    return next(
        e for e in exercises.load_catalog()
        if not e.get("fiche") and e["zone"] == "neck" and e.get("position", "standing") != "lying"
    )


def _copy(client, source_id):
    response = client.post(f"/exercises/{source_id}/copy", headers=ORIGIN)
    assert response.status_code == 200, response.text
    return response.json()


def _validate(client, exercise_id):
    state = client.get(f"/exercises/{exercise_id}/validation").json()
    return client.post(
        f"/exercises/{exercise_id}/validate", headers=ORIGIN,
        json={"fingerprint": state["fingerprint"], "formula": FORMULA, "animation_completed": True},
    )


def _new_content(**overrides):
    base = _plain()
    content = {key: base[key] for key in sheets_keys() if key in base}
    content["title"] = "Ma fiche"
    content.update(overrides)
    return content


def sheets_keys():
    from tms_vision import sheets

    return sheets.EDITABLE_KEYS


# --- Copier ----------------------------------------------------------------------------------------


def test_copy_is_a_new_unvalidated_exercise_with_the_original_author(client):
    _login(client, "lea@x.fr")
    source = _fiche()
    copy = _copy(client, source["id"])
    assert copy["id"] != source["id"]
    assert copy["status"] == "draft" and copy["validated_by"] is None
    label = copy["validation"]
    assert label["created_by"] == "Théo MARTIN"  # l'auteur d'origine, pas Léa
    assert label["copied_from"] == {"id": source["id"], "title": source["title"]}
    assert label["validated_by"] is None
    # l'original n'a pas bougé
    assert validation.get_exercise(source["id"]) == exercises.load_catalog()[
        [e["id"] for e in exercises.load_catalog()].index(source["id"])
    ]


def test_a_copy_of_a_copy_keeps_the_very_first_author(client):
    _login(client, "lea@x.fr")
    first = _copy(client, _fiche()["id"])
    _login(client, "paul@x.fr")
    second = _copy(client, first["id"])
    assert second["validation"]["created_by"] == "Théo MARTIN"
    assert second["validation"]["copied_from"]["id"] == first["id"]


def test_copying_does_not_carry_the_validation_over(client):
    _login(client, "lea@x.fr")
    source = _plain()["id"]
    assert _validate(client, source).status_code == 200
    copy = _copy(client, source)
    assert copy["validation"]["validated_by"] is None
    assert validation.label_for(validation.get_exercise(source))["validated_by"] == "Léa Osteo"


@pytest.mark.parametrize("email", ["prat@x.fr", "admin@x.fr"])
def test_only_osteopaths_can_copy(client, email):
    _login(client, email)
    assert client.post(f"/exercises/{_plain()['id']}/copy", headers=ORIGIN).status_code == 403


def test_anonymous_cannot_copy_and_unknown_source_is_404(client):
    assert client.post(f"/exercises/{_plain()['id']}/copy", headers=ORIGIN).status_code == 401
    _login(client, "lea@x.fr")
    assert client.post("/exercises/nope/copy", headers=ORIGIN).status_code == 404


# --- Modifier ----------------------------------------------------------------------------------------


def test_editing_creates_a_new_unvalidated_version_and_keeps_the_old_validation(client):
    _login(client, "lea@x.fr")
    copy = _copy(client, _plain()["id"])
    assert _validate(client, copy["id"]).status_code == 200
    assert client.get(f"/exercises/{copy['id']}/validation").json()["validated_by"] == "Léa Osteo"

    response = client.put(
        f"/exercises/{copy['id']}", json={"description": "Texte revu par Léa."}, headers=ORIGIN
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Texte revu par Léa."
    state = client.get(f"/exercises/{copy['id']}/validation").json()
    assert state["validated_by"] is None  # la validation est annulée
    assert [row["version"] for row in state["history"]] == [1]  # et reste consultable
    # la nouvelle version doit être revalidée
    assert _validate(client, copy["id"]).status_code == 200
    assert [r["version"] for r in client.get(f"/exercises/{copy['id']}/validation").json()["history"]] == [1, 2]


def test_an_edit_that_changes_nothing_creates_no_version(client):
    _login(client, "lea@x.fr")
    copy = _copy(client, _plain()["id"])
    assert _validate(client, copy["id"]).status_code == 200
    client.put(f"/exercises/{copy['id']}", json={"title": copy["title"]}, headers=ORIGIN)
    assert client.get(f"/exercises/{copy['id']}/validation").json()["validated_by"] == "Léa Osteo"


def test_a_colleague_cannot_edit_someone_elses_sheet(client):
    _login(client, "lea@x.fr")
    copy = _copy(client, _plain()["id"])
    _login(client, "paul@x.fr")
    response = client.put(f"/exercises/{copy['id']}", json={"title": "Piraté"}, headers=ORIGIN)
    assert response.status_code == 403
    assert validation.get_exercise(copy["id"])["title"] == copy["title"]


def test_a_file_sheet_cannot_be_edited_only_copied(client):
    _login(client, "lea@x.fr")
    response = client.put(f"/exercises/{_fiche()['id']}", json={"title": "X"}, headers=ORIGIN)
    assert response.status_code == 409


def test_an_edit_cannot_rewrite_the_author_status_or_validation(client):
    _login(client, "lea@x.fr")
    copy = _copy(client, _fiche()["id"])
    for forbidden in ({"fiche": "Fiche de Moi"}, {"status": "validated"}, {"validated_by": "Léa"}, {"source": "ai"}):
        response = client.put(f"/exercises/{copy['id']}", json=forbidden, headers=ORIGIN)
        assert response.status_code == 422, forbidden
    assert client.get(f"/exercises/{copy['id']}/validation").json()["created_by"] == "Théo MARTIN"


def test_an_invalid_edit_is_refused_with_the_field_name(client):
    _login(client, "lea@x.fr")
    copy = _copy(client, _plain()["id"])
    response = client.put(f"/exercises/{copy['id']}", json={"duration_seconds": 5}, headers=ORIGIN)
    assert response.status_code == 422 and "duration_seconds" in response.json()["detail"]


# --- Créer -------------------------------------------------------------------------------------------


def test_an_osteopath_creates_a_sheet_and_is_its_author(client):
    _login(client, "lea@x.fr")
    response = client.post("/exercises", json=_new_content(), headers=ORIGIN)
    assert response.status_code == 200, response.text
    sheet = response.json()
    assert sheet["id"].startswith("ma-fiche-") and sheet["source"] == "human"
    assert sheet["validation"]["created_by"] == "Léa Osteo"
    assert sheet["validation"]["copied_from"] is None and sheet["validation"]["validated_by"] is None
    assert _validate(client, sheet["id"]).status_code == 200


@pytest.mark.parametrize("email", ["prat@x.fr", "admin@x.fr"])
def test_only_osteopaths_can_create(client, email):
    _login(client, email)
    assert client.post("/exercises", json=_new_content(), headers=ORIGIN).status_code == 403


def test_a_creation_cannot_claim_validation_or_an_id(client):
    _login(client, "lea@x.fr")
    content = _new_content(status="validated", validated_by="Léa", validated_on="2026-11-22")
    assert client.post("/exercises", json=content, headers=ORIGIN).status_code == 422
    sheet = client.post("/exercises", json=_new_content(id="ecrase-un-id"), headers=ORIGIN).json()
    assert sheet["id"] != "ecrase-un-id"


def test_an_invalid_new_sheet_is_refused(client):
    _login(client, "lea@x.fr")
    assert client.post("/exercises", json=_new_content(zone="foie"), headers=ORIGIN).status_code == 422
    assert client.post("/exercises", json={"title": "Seul"}, headers=ORIGIN).status_code == 422


# --- Archiver, lister --------------------------------------------------------------------------------


def test_a_sheet_is_archived_not_deleted_and_copies_stay(client):
    _login(client, "lea@x.fr")
    original = _copy(client, _plain()["id"])
    _login(client, "paul@x.fr")
    copy = _copy(client, original["id"])
    _login(client, "lea@x.fr")
    assert client.delete(f"/exercises/{original['id']}", headers=ORIGIN).status_code in (404, 405)
    response = client.post(f"/exercises/{original['id']}/archive", headers=ORIGIN)
    assert response.status_code == 200 and response.json()["validation"]["archived"] is True
    ids = [e["id"] for e in client.get("/exercises").json()]
    assert original["id"] not in ids and copy["id"] in ids
    # toujours lisible (envois déjà faits, filiation)
    assert client.get(f"/exercises/{original['id']}").status_code == 200
    assert client.get(f"/exercises/{copy['id']}/validation").json()["copied_from"]["id"] == original["id"]
    # modifier une fiche archivée est refusé ; désarchiver la remet au catalogue
    assert client.put(f"/exercises/{original['id']}", json={"title": "X"}, headers=ORIGIN).status_code == 409
    client.post(f"/exercises/{original['id']}/unarchive", headers=ORIGIN)
    assert original["id"] in [e["id"] for e in client.get("/exercises").json()]


def test_only_the_owner_archives(client):
    _login(client, "lea@x.fr")
    sheet = _copy(client, _plain()["id"])
    _login(client, "paul@x.fr")
    assert client.post(f"/exercises/{sheet['id']}/archive", headers=ORIGIN).status_code == 403


def test_my_sheets_lists_only_mine(client):
    _login(client, "lea@x.fr")
    mine = _copy(client, _plain()["id"])
    _login(client, "paul@x.fr")
    _copy(client, _plain()["id"])
    _login(client, "lea@x.fr")
    assert [s["id"] for s in client.get("/sheets/mine").json()] == [mine["id"]]
    _login(client, "prat@x.fr")
    assert client.get("/sheets/mine").status_code == 403


def test_the_validation_state_tells_who_can_edit(client):
    _login(client, "lea@x.fr")
    sheet = _copy(client, _plain()["id"])
    state = client.get(f"/exercises/{sheet['id']}/validation").json()
    assert state["can_edit"] is True and state["can_copy"] is True
    _login(client, "paul@x.fr")
    state = client.get(f"/exercises/{sheet['id']}/validation").json()
    assert state["can_edit"] is False and state["can_copy"] is True
    assert "owner_id" not in state
    _login(client, "prat@x.fr")
    assert client.get(f"/exercises/{sheet['id']}/validation").json()["can_copy"] is False


# --- Programmes et bibliothèque ----------------------------------------------------------------------


def _bilan(client, zone):
    bilan = client.post("/bilans", json={"label": "P", "workday_hours": 8}, headers=ORIGIN).json()
    client.post(
        f"/bilans/{bilan['id']}/tasks", headers=ORIGIN,
        json={"name": "T", "zones": [zone], "activity_hours": 4, "source": "practitioner"},
    )
    return bilan["id"]


def test_a_validated_sheet_enters_the_library_and_programs_but_a_draft_does_not(client):
    _login(client, "lea@x.fr")
    draft = _copy(client, _plain()["id"])
    zone = draft["zone"]
    body_zone = {"neck": "neck", "foot": "ankle_foot", "hand": "wrist_hand"}.get(zone)
    if body_zone is None:
        pytest.skip("zone sans équivalent simple dans la carte du corps")

    def library_ids():
        return {
            e for z in client.get("/library").json()["zones"] for p in z["pathologies"]
            for e in p["exercises"]
        }

    assert draft["id"] not in library_ids()
    _login(client, "prat@x.fr")
    bilan_id = _bilan(client, zone)
    assert draft["id"] not in [i["capsule"]["id"] for i in client.get(f"/bilans/{bilan_id}/program?size=20").json()["program"]]
    _login(client, "lea@x.fr")
    assert _validate(client, draft["id"]).status_code == 200
    assert draft["id"] in library_ids()
    program = client.get(f"/bilans/{bilan_id}/program?size=20").json()
    assert draft["id"] in [i["capsule"]["id"] for i in program["program"]]
    # ajout à la main : même un brouillon se propose au praticien dans la liste
    assert draft["id"] in [a["id"] for a in program["available"]]


def test_the_osteopath_filter_keeps_only_her_validated_copy(client):
    users = {u["email"]: u["id"] for u in accounts.list_users()}
    _login(client, "lea@x.fr")
    mine = _copy(client, _plain()["id"])
    assert _validate(client, mine["id"]).status_code == 200
    _login(client, "prat@x.fr")
    bilan_id = _bilan(client, mine["zone"])
    client.put(f"/bilans/{bilan_id}/osteo", json={"osteo_id": users["lea@x.fr"]}, headers=ORIGIN)
    items = [
        i for i in client.get(f"/bilans/{bilan_id}/program?size=20").json()["program"]
        if i["zone"] == mine["zone"]
    ]
    assert [i["capsule"]["id"] for i in items] == [mine["id"]]
    assert items[0]["capsule"]["validation"]["validated_by"] == "Léa Osteo"
    assert items[0]["capsule"]["validation"]["copied_from"]["id"] == _plain()["id"]


def test_old_share_links_keep_working_after_archiving(client, monkeypatch):
    monkeypatch.setattr(
        "tms_vision.api.user_email.mailer_for",
        lambda user: (type("S", (), {"send": lambda self, message: None})(), None),
    )
    _login(client, "lea@x.fr")
    sheet = _copy(client, _plain()["id"])
    token = client.post(
        "/library/shares", headers=ORIGIN,
        json={"recipient_email": "pat@x.fr", "items": [{"exercise_id": sheet["id"]}]},
    ).json()["token"]
    client.post(f"/exercises/{sheet['id']}/archive", headers=ORIGIN)
    client.cookies.clear()
    page = client.get(f"/library/shares/{token}").json()
    assert [i["exercise"]["id"] for i in page["items"]] == [sheet["id"]]
    assert page["items"][0]["validation"]["copied_from"]["id"] == _plain()["id"]
