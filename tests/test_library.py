import copy
import json

import pytest
from fastapi.testclient import TestClient

from tms_vision import exercises, library, mailer, storage
from tms_vision.api import app

IDS = {exercise["id"] for exercise in exercises.load_catalog()}


def _valid():
    return {
        "status": "draft",
        "zones": [
            {
                "id": "neck",
                "label": "Cou",
                "pathologies": [
                    {"id": "p1", "label": "Pathologie", "exercises": ["neck-lateral-stretch"]}
                ],
            }
        ],
    }


def test_shipped_library_is_valid_and_covers_known_exercises():
    data = library.load_library()
    used = {
        exercise_id
        for zone in data["zones"]
        for pathology in zone["pathologies"]
        for exercise_id in pathology["exercises"]
    }
    assert used <= IDS
    assert data["status"] == "draft"


def test_every_catalog_exercise_is_reachable_from_the_library():
    data = library.load_library()
    used = {e for z in data["zones"] for p in z["pathologies"] for e in p["exercises"]}
    assert IDS - used == set()


def test_validate_accepts_minimal_library():
    library.validate_library(_valid(), IDS)


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["zones"][0]["pathologies"][0].update(exercises=["inconnu"]), "inconnu"),
        (lambda d: d["zones"][0]["pathologies"][0].update(exercises=[]), "au moins un exercice"),
        (lambda d: d["zones"].append(copy.deepcopy(d["zones"][0])), "en double"),
        (lambda d: d.update(status="autre"), "status"),
        (lambda d: d.update(zones=[]), "au moins une zone"),
        (lambda d: d["zones"][0].update(label=" "), "label"),
        (
            lambda d: d["zones"][0]["pathologies"][0].update(
                exercises=["neck-lateral-stretch", "neck-lateral-stretch"]
            ),
            "double",
        ),
    ],
)
def test_validate_rejects_bad_library(mutate, fragment):
    data = _valid()
    mutate(data)
    with pytest.raises(ValueError, match=fragment):
        library.validate_library(data, IDS)


def test_load_library_names_the_file_on_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="broken.json"):
        library.load_library(path)


class _RecordingMailer(mailer.Mailer):
    sent: list = []

    def send(self, message):
        type(self).sent.append(message)


class _FailingMailer(mailer.Mailer):
    def send(self, message):
        raise mailer.MailerError("boom")


def test_get_mailer_defaults_to_null(monkeypatch):
    monkeypatch.delenv("TMS_MAILER", raising=False)
    assert isinstance(mailer.get_mailer(), mailer.NullMailer)


def test_get_mailer_loads_custom_class(monkeypatch):
    monkeypatch.setenv("TMS_MAILER", "tests.test_library:_RecordingMailer")
    assert isinstance(mailer.get_mailer(), _RecordingMailer)


@pytest.mark.parametrize(
    "value", ["bidon", "module.introuvable:X", "tests.test_library:Absent", "tests.test_library:IDS"]
)
def test_get_mailer_rejects_bad_configuration(monkeypatch, value):
    monkeypatch.setenv("TMS_MAILER", value)
    with pytest.raises(mailer.MailerError):
        mailer.get_mailer()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    monkeypatch.delenv("TMS_MAILER", raising=False)
    monkeypatch.setenv("TMS_PUBLIC_WEB_URL", "https://cabinet.example/")
    _RecordingMailer.sent = []
    return TestClient(app)


def _payload(**overrides):
    body = {
        "recipient_email": "patient@example.com",
        "practitioner_name": "Dr Martin",
        "message": "À faire matin et soir.",
        "items": [
            {"exercise_id": "neck-lateral-stretch", "note": "10 répétitions"},
            {"exercise_id": "head-chin-tuck", "note": "  "},
        ],
    }
    body.update(overrides)
    return body


def test_get_library_returns_zones(client):
    body = client.get("/library").json()
    assert body["status"] == "draft"
    assert {zone["id"] for zone in body["zones"]} >= {"neck", "elbow", "lower_back"}


def test_share_without_mailer_is_saved_and_readable(client):
    response = client.post("/library/shares", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["email_status"] == "not_configured"
    assert body["share_path"] == f"/bibliotheque/envoi/{body['token']}"

    share = client.get(f"/library/shares/{body['token']}").json()
    assert share["practitioner_name"] == "Dr Martin"
    assert [item["exercise"]["id"] for item in share["items"]] == [
        "neck-lateral-stretch",
        "head-chin-tuck",
    ]
    assert share["items"][0]["note"] == "10 répétitions"
    assert share["items"][1]["note"] is None
    assert "poses" in share["items"][0]["exercise"]
    assert "recipient_email" not in share


def test_share_with_mailer_sends_message_with_link(client, monkeypatch):
    monkeypatch.setenv("TMS_MAILER", "tests.test_library:_RecordingMailer")
    body = client.post("/library/shares", json=_payload()).json()
    assert body["email_status"] == "sent"
    (message,) = _RecordingMailer.sent
    assert message.to == "patient@example.com"
    assert f"https://cabinet.example/bibliotheque/envoi/{body['token']}" in message.text
    assert "Dr Martin" in message.text
    assert "À faire matin et soir." in message.text


def test_share_survives_a_failing_mailer(client, monkeypatch):
    monkeypatch.setenv("TMS_MAILER", "tests.test_library:_FailingMailer")
    body = client.post("/library/shares", json=_payload()).json()
    assert body["email_status"] == "failed"
    assert client.get(f"/library/shares/{body['token']}").status_code == 200


def test_share_survives_a_misconfigured_mailer(client, monkeypatch):
    monkeypatch.setenv("TMS_MAILER", "bidon")
    assert client.post("/library/shares", json=_payload()).json()["email_status"] == "failed"


@pytest.mark.parametrize(
    "overrides",
    [
        {"recipient_email": "pas-un-email"},
        {"items": []},
        {"items": [{"exercise_id": "inconnu"}]},
        {"items": [{"exercise_id": "head-chin-tuck"}, {"exercise_id": "head-chin-tuck"}]},
        {"message": "x" * 2001},
    ],
)
def test_share_rejects_invalid_payload(client, overrides):
    assert client.post("/library/shares", json=_payload(**overrides)).status_code == 422


def test_unknown_share_is_404(client):
    assert client.get("/library/shares/inconnu").status_code == 404
