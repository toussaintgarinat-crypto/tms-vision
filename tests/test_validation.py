"""Phase 2 : validation des exercices par un ostéopathe. Un test par règle de la section 5 du plan,
dont les cas d'abus (praticien qui valide, validation rejouée sur une version modifiée...)."""
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
    yield TestClient(app)
    auth_api.reset_cache()


def _user(email, roles, name=None):
    return accounts.create_user(email, name or email.split("@")[0].title(), GOOD, roles)


def _login(client, email):
    response = client.post("/auth/login", json={"email": email, "password": GOOD}, headers=ORIGIN)
    assert response.status_code == 200, response.text


def _logout(client):
    client.cookies.clear()


def _exercise_id():
    return exercises.load_catalog()[0]["id"]


def _fingerprint(client, exercise_id):
    return client.get(f"/exercises/{exercise_id}/validation").json()["fingerprint"]


def _validate(client, exercise_id, **overrides):
    body = {
        "fingerprint": _fingerprint(client, exercise_id), "formula": FORMULA,
        "animation_completed": True,
    }
    body.update(overrides)
    return client.post(f"/exercises/{exercise_id}/validate", json=body, headers=ORIGIN)


@pytest.fixture
def accounts_ready(client):
    _user("admin@x.fr", ["administrateur"])
    _user("osteo@x.fr", ["osteopathe"], "Léa Osteo")
    _user("praticien@x.fr", ["praticien"])
    _user("autre@x.fr", ["osteopathe"], "Paul Autre")
    return client


# --- Qui peut valider -----------------------------------------------------------------------------


def test_an_osteopath_can_validate_in_their_name(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    response = _validate(accounts_ready, exercise_id)
    assert response.status_code == 200
    assert response.json()["validated_by"] == "Léa Osteo"
    listed = {e["id"]: e for e in accounts_ready.get("/exercises").json()}
    assert listed[exercise_id]["validation"]["validated_by"] == "Léa Osteo"


@pytest.mark.parametrize("email", ["admin@x.fr", "praticien@x.fr"])
def test_neither_admin_nor_practitioner_can_validate(accounts_ready, email):
    _login(accounts_ready, email)
    exercise_id = _exercise_id()
    assert _validate(accounts_ready, exercise_id).status_code == 403
    assert accounts_ready.get(f"/exercises/{exercise_id}/validation").json()["validated_by"] is None
    assert validation.history(exercise_id) == []


def test_anonymous_cannot_validate(accounts_ready):
    exercise_id = _exercise_id()
    fingerprint = validation.fingerprint(validation.get_exercise(exercise_id))
    response = accounts_ready.post(
        f"/exercises/{exercise_id}/validate",
        json={"fingerprint": fingerprint, "formula": FORMULA, "animation_completed": True},
        headers=ORIGIN,
    )
    assert response.status_code == 401


def test_cumulating_osteopath_and_admin_roles_can_validate(accounts_ready):
    _user("double@x.fr", ["administrateur", "osteopathe"], "Double")
    _login(accounts_ready, "double@x.fr")
    assert _validate(accounts_ready, _exercise_id()).status_code == 200


def test_unknown_exercise_is_404(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    response = accounts_ready.post(
        "/exercises/n-existe-pas/validate",
        json={"fingerprint": "x", "formula": FORMULA, "animation_completed": True},
        headers=ORIGIN,
    )
    assert response.status_code == 404


# --- Comment : animation vue, formule cochée, version précise -------------------------------------


def test_validation_requires_the_animation_played_in_full(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    assert _validate(accounts_ready, _exercise_id(), animation_completed=False).status_code == 422


def test_an_accelerated_animation_is_accepted_and_its_speed_recorded(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    assert _validate(accounts_ready, exercise_id, playback_speed=4).status_code == 200
    assert validation.history(exercise_id)[0]["playback_speed"] == 4


@pytest.mark.parametrize("speed", [0, -1, 4.5, 50])
def test_a_playback_speed_beyond_the_limit_is_refused(accounts_ready, speed):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    assert _validate(accounts_ready, exercise_id, playback_speed=speed).status_code == 422
    assert validation.history(exercise_id) == []


@pytest.mark.parametrize("formula", ["", "ok", "J'ai tout vérifié."])
def test_validation_requires_the_exact_confirmation_formula(accounts_ready, formula):
    _login(accounts_ready, "osteo@x.fr")
    assert _validate(accounts_ready, _exercise_id(), formula=formula).status_code == 422


def test_the_formula_is_recorded_with_the_validation(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    _validate(accounts_ready, exercise_id)
    [row] = validation.history(exercise_id)
    assert row["formula"] == FORMULA and row["kind"] == "validate"
    assert row["osteo_name"] == "Léa Osteo"
    assert row["fingerprint"] == validation.fingerprint(validation.get_exercise(exercise_id))


def test_a_validation_cannot_be_replayed_on_a_modified_version(accounts_ready, monkeypatch):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    seen = _fingerprint(accounts_ready, exercise_id)
    original = exercises.load_catalog()

    def changed():
        return [
            {**e, "title": e["title"] + "!"} if e["id"] == exercise_id else e for e in original
        ]

    monkeypatch.setattr(exercises, "load_catalog", changed)
    response = _validate(accounts_ready, exercise_id, fingerprint=seen)
    assert response.status_code == 409
    assert validation.history(exercise_id) == []


def test_one_letter_changes_the_fingerprint():
    exercise = dict(exercises.load_catalog()[0])
    modified = {**exercise, "description": exercise["description"] + "."}
    assert validation.fingerprint(exercise) != validation.fingerprint(modified)


def test_the_old_file_status_does_not_change_the_fingerprint():
    exercise = dict(exercises.load_catalog()[0])
    assert validation.fingerprint(exercise) == validation.fingerprint(
        {**exercise, "status": "validated", "validated_by": "X", "validated_on": "2026-01-01"}
    )


def test_modifying_a_sheet_drops_the_validation_but_keeps_the_history(accounts_ready, monkeypatch):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    _validate(accounts_ready, exercise_id)
    original = exercises.load_catalog()
    monkeypatch.setattr(
        exercises, "load_catalog",
        lambda: [{**e, "benefit": "Autre"} if e["id"] == exercise_id else e for e in original],
    )
    label = accounts_ready.get(f"/exercises/{exercise_id}/validation").json()
    assert label["validated_by"] is None
    assert len(label["history"]) == 1  # l'ancienne validation reste consultable


# --- Retrait ----------------------------------------------------------------------------------------


def test_withdrawal_is_a_new_row_and_the_old_one_stays(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    _validate(accounts_ready, exercise_id)
    response = accounts_ready.post(
        f"/exercises/{exercise_id}/withdraw-validation", headers=ORIGIN
    )
    assert response.status_code == 200 and response.json()["validated_by"] is None
    assert [row["kind"] for row in validation.history(exercise_id)] == ["validate", "withdraw"]
    # elle peut être redonnée ensuite
    assert _validate(accounts_ready, exercise_id).json()["validated_by"] == "Léa Osteo"


def test_one_cannot_withdraw_someone_elses_validation(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    _validate(accounts_ready, exercise_id)
    _logout(accounts_ready)
    _login(accounts_ready, "autre@x.fr")
    response = accounts_ready.post(
        f"/exercises/{exercise_id}/withdraw-validation", headers=ORIGIN
    )
    assert response.status_code == 409
    assert accounts_ready.get(f"/exercises/{exercise_id}/validation").json()["validated_by"] == "Léa Osteo"


def test_a_practitioner_cannot_withdraw(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    _validate(accounts_ready, exercise_id)
    _logout(accounts_ready)
    _login(accounts_ready, "praticien@x.fr")
    response = accounts_ready.post(
        f"/exercises/{exercise_id}/withdraw-validation", headers=ORIGIN
    )
    assert response.status_code == 403


def test_the_validation_history_cannot_be_changed_through_the_api(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    _validate(accounts_ready, exercise_id)
    for method in ("put", "patch", "delete"):
        response = getattr(accounts_ready, method)(
            f"/exercises/{exercise_id}/validation", headers=ORIGIN
        )
        assert response.status_code in (404, 405)
    assert len(validation.history(exercise_id)) == 1


# --- Étiquette ---------------------------------------------------------------------------------------


def test_label_says_created_by_and_not_validated_by_default(client):
    fiche = next(e for e in exercises.load_catalog() if e.get("fiche"))
    label = validation.label_for(fiche)
    assert label["created_by"] == "Théo MARTIN" and label["validated_by"] is None
    assert "non validé" in validation.describe_label(label)


def test_label_for_an_exercise_without_fiche_names_the_library(client):
    plain = next(e for e in exercises.load_catalog() if not e.get("fiche"))
    assert validation.label_for(plain)["created_by"] == validation.DEFAULT_AUTHOR


def test_label_shows_the_latest_validator_and_date(accounts_ready):
    exercise_id = _exercise_id()
    for email in ("osteo@x.fr", "autre@x.fr"):
        _login(accounts_ready, email)
        _validate(accounts_ready, exercise_id)
        _logout(accounts_ready)
    label = validation.label_for(validation.get_exercise(exercise_id))
    assert label["validated_by"] == "Paul Autre"
    text = validation.describe_label(label)
    assert "validé par Paul Autre le " in text


def test_the_patient_page_and_email_carry_the_label(accounts_ready, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "tms_vision.api.user_email.mailer_for",
        lambda user: (type("S", (), {"send": lambda self, message: sent.append(message)})(), None),
    )
    _login(accounts_ready, "osteo@x.fr")
    exercise_id = _exercise_id()
    _validate(accounts_ready, exercise_id)
    response = accounts_ready.post(
        "/library/shares", headers=ORIGIN,
        json={"recipient_email": "pat@x.fr", "items": [{"exercise_id": exercise_id}]},
    )
    assert response.status_code == 200
    assert "validé par Léa Osteo le" in sent[0].text
    _logout(accounts_ready)
    page = accounts_ready.get(f"/library/shares/{response.json()['token']}").json()
    assert page["items"][0]["validation"]["validated_by"] == "Léa Osteo"
    assert "validator_ids" not in page["items"][0]["validation"]


# --- Ostéopathe du bilan et filtre du programme -----------------------------------------------------


def _bilan_with_task(client, zone="neck"):
    bilan = client.post("/bilans", json={"label": "Poste", "workday_hours": 8}, headers=ORIGIN).json()
    response = client.post(
        f"/bilans/{bilan['id']}/tasks", headers=ORIGIN,
        json={"name": "Saisie", "zones": [zone], "activity_hours": 4, "source": "practitioner"},
    )
    assert response.status_code == 200, response.text
    return bilan["id"]


def _program(client, bilan_id):
    return client.get(f"/bilans/{bilan_id}/program").json()


def test_only_osteopaths_can_be_chosen_on_a_bilan(accounts_ready):
    _login(accounts_ready, "praticien@x.fr")
    bilan_id = _bilan_with_task(accounts_ready)
    users = {u["email"]: u["id"] for u in accounts.list_users()}
    names = [o["name"] for o in accounts_ready.get("/osteopaths").json()]
    assert sorted(names) == ["Léa Osteo", "Paul Autre"]
    for email in ("praticien@x.fr", "admin@x.fr"):
        response = accounts_ready.put(
            f"/bilans/{bilan_id}/osteo", json={"osteo_id": users[email]}, headers=ORIGIN
        )
        assert response.status_code == 422
    response = accounts_ready.put(
        f"/bilans/{bilan_id}/osteo", json={"osteo_id": users["osteo@x.fr"]}, headers=ORIGIN
    )
    assert response.status_code == 200 and response.json()["osteo_id"] == users["osteo@x.fr"]
    cleared = accounts_ready.put(f"/bilans/{bilan_id}/osteo", json={"osteo_id": None}, headers=ORIGIN)
    assert cleared.json()["osteo_id"] is None


def test_without_an_osteopath_the_program_is_unchanged(accounts_ready):
    _login(accounts_ready, "praticien@x.fr")
    bilan_id = _bilan_with_task(accounts_ready)
    unfiltered = _program(accounts_ready, bilan_id)
    assert unfiltered["osteo_id"] is None
    assert unfiltered["program"]
    users = {u["email"]: u["id"] for u in accounts.list_users()}
    accounts_ready.put(f"/bilans/{bilan_id}/osteo", json={"osteo_id": users["osteo@x.fr"]}, headers=ORIGIN)
    accounts_ready.put(f"/bilans/{bilan_id}/osteo", json={"osteo_id": None}, headers=ORIGIN)
    again = _program(accounts_ready, bilan_id)
    assert [i["capsule"]["id"] for i in again["program"]] == [
        i["capsule"]["id"] for i in unfiltered["program"]
    ]


def test_the_program_keeps_only_exercises_validated_by_the_chosen_osteopath(accounts_ready):
    users = {u["email"]: u["id"] for u in accounts.list_users()}
    _login(accounts_ready, "praticien@x.fr")
    bilan_id = _bilan_with_task(accounts_ready, "neck")
    neck = [
        e for e in exercises.load_catalog()
        if e["zone"] == "neck" and e.get("position", "standing") != "lying"
    ]
    assert len(neck) >= 2
    chosen = neck[-1]["id"]  # pas le premier : le filtre doit changer l'ordre habituel
    _logout(accounts_ready)
    _login(accounts_ready, "osteo@x.fr")
    _validate(accounts_ready, chosen)
    # Paul valide un autre exercice : il ne compte pas pour Léa
    _logout(accounts_ready)
    _login(accounts_ready, "autre@x.fr")
    _validate(accounts_ready, neck[0]["id"])
    _logout(accounts_ready)
    _login(accounts_ready, "praticien@x.fr")
    accounts_ready.put(f"/bilans/{bilan_id}/osteo", json={"osteo_id": users["osteo@x.fr"]}, headers=ORIGIN)
    program = _program(accounts_ready, bilan_id)
    neck_items = [i for i in program["program"] if i["zone"] == "neck"]
    assert [i["capsule"]["id"] for i in neck_items] == [chosen]
    assert neck_items[0]["capsule"]["validation"]["validated_by"] == "Léa Osteo"


def test_a_zone_without_exercise_validated_by_the_osteopath_is_empty_and_flagged(accounts_ready):
    users = {u["email"]: u["id"] for u in accounts.list_users()}
    _login(accounts_ready, "praticien@x.fr")
    bilan_id = _bilan_with_task(accounts_ready, "neck")
    accounts_ready.put(f"/bilans/{bilan_id}/osteo", json={"osteo_id": users["osteo@x.fr"]}, headers=ORIGIN)
    program = _program(accounts_ready, bilan_id)
    assert not [i for i in program["program"] if i["zone"] == "neck"]
    assert any("Léa Osteo" in w and "revalider" in w for w in program["warnings"])


def test_a_colleagues_validation_does_not_stand_in_for_the_chosen_osteopath(accounts_ready):
    users = {u["email"]: u["id"] for u in accounts.list_users()}
    _login(accounts_ready, "praticien@x.fr")
    bilan_id = _bilan_with_task(accounts_ready, "neck")
    neck = [
        e for e in exercises.load_catalog()
        if e["zone"] == "neck" and e.get("position", "standing") != "lying"
    ]
    _logout(accounts_ready)
    _login(accounts_ready, "autre@x.fr")
    _validate(accounts_ready, neck[0]["id"])
    _logout(accounts_ready)
    _login(accounts_ready, "praticien@x.fr")
    accounts_ready.put(f"/bilans/{bilan_id}/osteo", json={"osteo_id": users["osteo@x.fr"]}, headers=ORIGIN)
    assert not [i for i in _program(accounts_ready, bilan_id)["program"] if i["zone"] == "neck"]


def test_duplicating_a_bilan_keeps_its_osteopath(accounts_ready):
    users = {u["email"]: u["id"] for u in accounts.list_users()}
    _login(accounts_ready, "praticien@x.fr")
    bilan_id = _bilan_with_task(accounts_ready)
    accounts_ready.put(f"/bilans/{bilan_id}/osteo", json={"osteo_id": users["osteo@x.fr"]}, headers=ORIGIN)
    copy = accounts_ready.post(f"/bilans/{bilan_id}/duplicate", json={}, headers=ORIGIN).json()
    assert copy["osteo_id"] == users["osteo@x.fr"]


# --- Chargement : fichiers puis base ----------------------------------------------------------------


def test_effective_catalog_equals_the_files_when_nothing_is_in_the_database(client):
    assert [e["id"] for e in validation.load_effective_catalog()] == [
        e["id"] for e in exercises.load_catalog()
    ]


def test_database_exercises_win_over_files(client):
    base = exercises.load_catalog()[0]
    conn = validation._connect()
    try:
        conn.execute(
            "INSERT INTO exercises (id, origin, original_author, created_at) "
            "VALUES (?, 'osteopathe', 'Léa', now())", [base["id"]]
        )
        content = {**base, "title": "Titre de la base"}
        import json

        conn.execute(
            "INSERT INTO exercise_versions VALUES ('v1', ?, 1, ?, 'x', NULL, now())",
            [base["id"], json.dumps(content)],
        )
    finally:
        conn.close()
    assert validation.get_exercise(base["id"])["title"] == "Titre de la base"
    assert exercises.load_catalog()[0]["title"] == base["title"]


# --- File de relecture ----------------------------------------------------------------------------


def test_review_queue_is_for_osteopaths_only(accounts_ready):
    assert accounts_ready.get("/validation/queue").status_code == 401
    for email in ("praticien@x.fr", "admin@x.fr"):
        _login(accounts_ready, email)
        assert accounts_ready.get("/validation/queue").status_code == 403
        _logout(accounts_ready)


def test_review_queue_lists_unvalidated_sheets_and_drops_the_one_just_validated(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    queue = accounts_ready.get("/validation/queue").json()
    assert queue["total"] == len(exercises.load_catalog())
    first = queue["items"][0]["id"]
    assert _validate(accounts_ready, first).status_code == 200
    after = accounts_ready.get("/validation/queue").json()
    assert after["total"] == queue["total"] - 1
    assert first not in [item["id"] for item in after["items"]]
    # un confrère voit toujours la fiche : sa propre validation n'existe pas
    _logout(accounts_ready)
    _login(accounts_ready, "autre@x.fr")
    assert first in [i["id"] for i in accounts_ready.get("/validation/queue").json()["items"]]


def test_review_queue_filters_by_zone_and_fiches(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    zone = accounts_ready.get("/validation/queue").json()["items"][0]["zone"]
    items = accounts_ready.get(f"/validation/queue?zone={zone}").json()["items"]
    assert items and all(item["zone"] == zone for item in items)
    fiches = accounts_ready.get("/validation/queue?fiches_only=true").json()
    wanted = {e["id"] for e in exercises.load_catalog() if e.get("fiche")}
    assert {item["id"] for item in fiches["items"]} == wanted
    assert accounts_ready.get("/validation/queue?zone=nimporte").status_code == 422


def test_the_queue_does_not_bypass_the_animation_rule(accounts_ready):
    _login(accounts_ready, "osteo@x.fr")
    first = accounts_ready.get("/validation/queue").json()["items"][0]["id"]
    assert _validate(accounts_ready, first, animation_completed=False).status_code == 422
