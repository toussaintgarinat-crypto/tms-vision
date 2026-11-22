"""Invitation à installer l'application de bureau (envoi par l'administrateur) et déclaration du rôle
ostéopathe au premier lancement."""
import pytest
from fastapi.testclient import TestClient

from tms_vision import accounts, auth_api, mailer, storage, updates
from tms_vision.api import app

GOOD = "correct horse battery"
ORIGIN = {"Origin": "http://testserver"}
RELEASE = {
    "version": "2.1.0",
    "url": "https://github.com/toussaintgarinat-crypto/tms-vision/releases/tag/v2.1.0",
    "assets": [
        {"name": "TMS-Vision-Setup.exe", "url": "https://github.com/x/releases/download/v2.1.0/TMS-Vision-Setup.exe"},
        {"name": "TMS-Vision-Mac-Apple-Silicon.dmg", "url": "https://github.com/x/releases/download/v2.1.0/a.dmg"},
        {"name": "TMS-Vision-Mac-Intel.dmg", "url": "https://evil.example/i.dmg"},
        {"name": "notes.txt", "url": "https://github.com/x/releases/download/v2.1.0/notes.txt"},
    ],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    monkeypatch.delenv("TMS_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("TMS_LOCAL_SETUP", raising=False)
    auth_api.reset_cache()
    yield TestClient(app)
    auth_api.reset_cache()


def _login(client, email):
    client.cookies.clear()
    assert client.post("/auth/login", json={"email": email, "password": GOOD}, headers=ORIGIN).status_code == 200


@pytest.fixture
def sent(monkeypatch):
    outbox = []
    monkeypatch.setattr(
        "tms_vision.user_email.mailer_for",
        lambda user: (type("S", (), {"send": lambda self, message: outbox.append(message)})(), user["email"]),
    )
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: RELEASE)
    return outbox


def _accounts():
    accounts.create_user("admin@x.fr", "Toussaint", GOOD, ["administrateur"])
    accounts.create_user("prat@x.fr", "Prat", GOOD, ["praticien"])


def test_an_admin_sends_the_invitation_with_direct_links_and_the_guide(client, sent):
    _accounts()
    _login(client, "admin@x.fr")
    response = client.post(
        "/admin/invitations", headers=ORIGIN,
        json={"email": "theo@cabinet.fr", "name": "Théo", "message": "Bienvenue !", "osteopath": True},
    )
    assert response.status_code == 200 and response.json() == {"email_status": "sent"}
    [message] = sent
    assert message.to == "theo@cabinet.fr" and message.reply_to == "admin@x.fr"
    assert "Bonjour Théo," in message.text and "Bienvenue !" in message.text
    assert "TMS-Vision-Setup.exe" in message.text
    assert "a.dmg" in message.text
    assert "Je suis ostéopathe" in message.text
    assert "code de récupération" in message.text
    assert 'href="https://github.com/x/releases/download/v2.1.0/TMS-Vision-Setup.exe"' in message.html


def test_only_github_hosted_installers_and_known_files_are_linked(client, sent):
    _accounts()
    _login(client, "admin@x.fr")
    client.post("/admin/invitations", headers=ORIGIN, json={"email": "theo@cabinet.fr"})
    text = sent[0].text
    assert "evil.example" not in text and "notes.txt" not in text
    assert mailer.installer_links(RELEASE["assets"]) == [
        ("Windows", RELEASE["assets"][0]["url"]),
        ("Mac avec puce Apple (M1, M2, M3…)", RELEASE["assets"][1]["url"]),
    ]


def test_the_invitation_carries_no_password_nor_token(client, sent):
    _accounts()
    _login(client, "admin@x.fr")
    client.post("/admin/invitations", headers=ORIGIN, json={"email": "theo@cabinet.fr", "osteopath": False})
    text = sent[0].text
    assert "Je suis ostéopathe" not in text
    assert "mot de passe d'au moins 12" in text and GOOD not in text


def test_without_network_the_email_points_to_the_releases_page(client, sent, monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: None)
    _accounts()
    _login(client, "admin@x.fr")
    assert client.post("/admin/invitations", headers=ORIGIN, json={"email": "theo@cabinet.fr"}).status_code == 200
    assert mailer.RELEASES_PAGE_URL in sent[0].text


@pytest.mark.parametrize("email", ["prat@x.fr"])
def test_only_admins_can_invite(client, sent, email):
    _accounts()
    _login(client, email)
    assert client.post("/admin/invitations", headers=ORIGIN, json={"email": "t@x.fr"}).status_code == 403
    assert sent == []
    client.cookies.clear()
    assert client.post("/admin/invitations", headers=ORIGIN, json={"email": "t@x.fr"}).status_code == 401


def test_an_invalid_address_is_refused_and_the_invitation_is_journaled(client, sent):
    _accounts()
    _login(client, "admin@x.fr")
    assert client.post("/admin/invitations", headers=ORIGIN, json={"email": "pas-un-email"}).status_code == 422
    client.post("/admin/invitations", headers=ORIGIN, json={"email": "theo@cabinet.fr"})
    actions = [(entry["action"], entry["target"]) for entry in accounts.list_audit()]
    assert ("invitation.send", "theo@cabinet.fr") in actions


def test_a_failed_send_is_reported_not_raised(client, monkeypatch):
    def broken(user):
        raise mailer.MailerError("boom")

    monkeypatch.setattr("tms_vision.user_email.mailer_for", broken)
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: RELEASE)
    _accounts()
    _login(client, "admin@x.fr")
    response = client.post("/admin/invitations", headers=ORIGIN, json={"email": "t@x.fr"})
    assert response.status_code == 200 and response.json() == {"email_status": "failed"}


# --- Premier lancement : rôle ostéopathe déclaré ---------------------------------------------------


def _desktop(monkeypatch):
    monkeypatch.setenv("TMS_LOCAL_SETUP", "1")
    auth_api.reset_cache()


def test_first_launch_gives_the_osteopath_role_only_when_declared(client, monkeypatch):
    _desktop(monkeypatch)
    response = client.post(
        "/auth/setup", headers=ORIGIN,
        json={"email": "theo@x.fr", "name": "Théo", "password": GOOD, "osteopath": True},
    )
    assert response.status_code == 200
    assert sorted(response.json()["user"]["roles"]) == ["administrateur", "osteopathe", "praticien"]
    assert any("ostéopathe" in (entry["detail"] or "") for entry in accounts.list_audit())


def test_first_launch_without_the_declaration_stays_practitioner_and_admin(client, monkeypatch):
    _desktop(monkeypatch)
    response = client.post(
        "/auth/setup", headers=ORIGIN, json={"email": "kine@x.fr", "name": "Kiné", "password": GOOD}
    )
    assert sorted(response.json()["user"]["roles"]) == ["administrateur", "praticien"]
