import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tms_vision import accounts, auth_api, storage

GOOD = "correct horse battery"
ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    monkeypatch.delenv("TMS_REQUIRE_AUTH", raising=False)
    auth_api.reset_cache()
    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(auth_api.admin_router)
    app.add_middleware(auth_api.AuthMiddleware)

    @app.get("/bilans")
    def bilans():
        return ["b"]

    @app.post("/bilans")
    def create_bilan():
        return {"ok": True}

    @app.get("/library/shares/{token}")
    def share(token: str):
        return {"token": token}

    @app.get("/capsules/{capsule}/video")
    def video(capsule: str):
        return {"v": capsule}

    @app.post("/library/shares")
    def make_share():
        return {"ok": True}

    @app.get("/osteo-only")
    def osteo(user=Depends(auth_api.require_roles("osteopathe"))):
        return {"by": user["email"]}

    yield TestClient(app)
    auth_api.reset_cache()


def _admin():
    return accounts.create_user("admin@x.fr", "Admin", GOOD, ["administrateur"])


def _login(client, email="admin@x.fr", password=GOOD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_without_any_account_the_api_stays_open_and_asks_for_setup(client):
    assert client.get("/bilans").status_code == 200
    status = client.get("/auth/status").json()
    assert status["auth_required"] is False and status["setup_required"] is True


def test_require_auth_variable_closes_the_api_before_the_first_account(client, monkeypatch):
    monkeypatch.setenv("TMS_REQUIRE_AUTH", "true")
    assert client.get("/bilans").status_code == 401
    assert client.get("/auth/status").json()["setup_required"] is True


def test_once_an_account_exists_everything_needs_a_session(client):
    _admin()
    response = client.get("/bilans")
    assert response.status_code == 401 and response.json()["code"] == "login_required"
    assert client.post("/bilans", headers=ORIGIN).status_code == 401


def test_login_sets_a_secure_cookie_and_opens_the_api(client):
    _admin()
    response = _login(client)
    assert response.status_code == 200 and response.json()["user"]["email"] == "admin@x.fr"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie.split(";")[0]
    assert client.get("/bilans").status_code == 200
    assert client.get("/auth/me").json()["user"]["roles"] == ["administrateur"]


def test_cookie_is_secure_behind_https(client):
    _admin()
    response = client.post(
        "/auth/login", json={"email": "admin@x.fr", "password": GOOD}, headers={"X-Forwarded-Proto": "https"}
    )
    assert "secure" in response.headers["set-cookie"].lower()


def test_wrong_password_is_401_and_throttling_is_429_with_retry_after(client):
    _admin()
    for _ in range(accounts.ACCOUNT_FREE_ATTEMPTS):
        assert _login(client, password="faux faux faux").status_code == 401
    blocked = _login(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json()["detail"]["code"] == "too_many_attempts"


def test_logout_ends_the_session(client):
    _admin()
    _login(client)
    assert client.post("/auth/logout", headers=ORIGIN).status_code == 200
    assert client.get("/bilans").status_code == 401


def test_patient_pages_stay_public_but_only_for_reading(client):
    _admin()
    assert client.get("/library/shares/abc123").status_code == 200
    assert client.get("/capsules/neck-stretch/video").status_code == 200
    assert client.post("/library/shares", headers=ORIGIN).status_code == 401


def test_writes_from_a_foreign_origin_are_refused(client):
    _admin()
    _login(client)
    assert client.post("/bilans", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/bilans", headers=ORIGIN).status_code == 200
    assert client.post("/bilans").status_code == 200  # pas d'Origin : appel direct (curl, tests)


def test_roles_are_enforced_by_the_api(client):
    _admin()
    accounts.create_user("osteo@x.fr", "Ostéo", GOOD, ["osteopathe"])
    accounts.create_user("prat@x.fr", "Prat", GOOD, ["praticien"])
    _login(client, "prat@x.fr")
    assert client.get("/osteo-only").status_code == 403
    assert client.get("/admin/users").status_code == 403
    client.post("/auth/logout", headers=ORIGIN)
    _login(client, "osteo@x.fr")
    assert client.get("/osteo-only").json() == {"by": "osteo@x.fr"}
    assert client.get("/admin/users").status_code == 403


def test_admin_manages_accounts_and_reads_the_journal(client):
    _admin()
    _login(client)
    created = client.post(
        "/admin/users",
        headers=ORIGIN,
        json={"email": "new@x.fr", "name": "Nouveau", "password": GOOD, "roles": ["praticien"]},
    )
    assert created.status_code == 201
    assert "password" not in created.text
    user_id = created.json()["id"]
    assert client.post("/admin/users", headers=ORIGIN, json={"email": "NEW@x.fr", "name": "x", "password": GOOD, "roles": ["praticien"]}).status_code == 409
    assert client.post("/admin/users", headers=ORIGIN, json={"email": "w@x.fr", "name": "x", "password": "court", "roles": ["praticien"]}).status_code == 422
    patched = client.patch(f"/admin/users/{user_id}", headers=ORIGIN, json={"roles": ["praticien", "osteopathe"]})
    assert patched.json()["roles"] == ["praticien", "osteopathe"]
    assert len(client.get("/admin/users").json()) == 2
    actions = {entry["action"] for entry in client.get("/admin/audit").json()}
    assert {"login.success", "user.create", "user.update"} <= actions


def test_user_changes_own_password_and_keeps_the_current_session(client):
    _admin()
    _login(client)
    assert client.post("/auth/password", headers=ORIGIN, json={"current": "faux", "new": "un autre mot de passe"}).status_code == 422
    assert client.post("/auth/password", headers=ORIGIN, json={"current": GOOD, "new": "un autre mot de passe"}).status_code == 200
    assert client.get("/bilans").status_code == 200
    client.post("/auth/logout", headers=ORIGIN)
    assert _login(client, password="un autre mot de passe").status_code == 200
