import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tms_vision import accounts, auth_api, mailer, smtp_mailer, storage, user_email

GOOD = "correct horse battery"
ORIGIN = {"Origin": "http://testserver"}
FORM = dict(address="Dr@Gmail.com", host="smtp.gmail.com", port=587, security="starttls", username="", password="abcd efgh ijkl mnop")


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    monkeypatch.setenv("TMS_SECRET_KEY", "une-cle-secrete-assez-longue")
    monkeypatch.setenv("TMS_SMTP_ALLOW_PRIVATE", "true")
    monkeypatch.delenv("TMS_REQUIRE_AUTH", raising=False)
    auth_api.reset_cache()
    yield
    auth_api.reset_cache()


def _user(email="dr@gmail.com", name="Dr Martin"):
    return accounts.create_user(email, name, GOOD, ["osteopathe"])


def test_password_is_encrypted_in_database_and_never_returned():
    user = _user()
    shown = user_email.save_settings(user["id"], **FORM)
    assert shown["configured"] and shown["password_set"] and shown["address"] == "dr@gmail.com"
    assert "abcd" not in str(shown) and "password_enc" not in str(shown)
    conn = user_email._connect()
    stored = conn.execute("SELECT password_enc FROM user_email_settings").fetchone()[0]
    conn.close()
    assert "abcd" not in stored
    assert user_email.decrypt_secret(stored) == "abcd efgh ijkl mnop"
    assert "abcd" not in str(accounts.list_audit())


def test_without_secret_key_nothing_is_stored(monkeypatch):
    monkeypatch.delenv("TMS_SECRET_KEY")
    user = _user()
    with pytest.raises(accounts.AccountError) as error:
        user_email.save_settings(user["id"], **FORM)
    assert error.value.code == "secret_key_missing"
    assert user_email.get_settings(user["id"])["configured"] is False


def test_changed_key_asks_to_retype(monkeypatch):
    user = _user()
    user_email.save_settings(user["id"], **FORM)
    monkeypatch.setenv("TMS_SECRET_KEY", "une-autre-cle-secrete-longue")
    with pytest.raises(mailer.MailerError, match="ressaisissez"):
        user_email.mailer_for(user)


def test_blank_password_keeps_the_saved_one_and_a_change_resets_the_test():
    user = _user()
    user_email.save_settings(user["id"], **FORM)
    assert user_email.save_settings(user["id"], **{**FORM, "password": ""})["password_set"]
    settings = user_email._smtp_settings(user)
    assert settings.password == "abcd efgh ijkl mnop"
    with pytest.raises(accounts.AccountError, match="obligatoire"):
        user_email.save_settings(_user("b@x.fr")["id"], **{**FORM, "password": ""})


@pytest.mark.parametrize(
    "change, code",
    [({"port": 22}, "invalid_port"), ({"security": "magic"}, "invalid_security"),
     ({"host": "smtp.x.fr/evil"}, "invalid_host"), ({"address": "nope"}, "invalid_email")],
)
def test_invalid_settings_are_refused(change, code):
    with pytest.raises(accounts.AccountError) as error:
        user_email.save_settings(_user()["id"], **{**FORM, **change})
    assert error.value.code == code


def test_internal_servers_are_refused_unless_allowed(monkeypatch):
    monkeypatch.delenv("TMS_SMTP_ALLOW_PRIVATE")
    with pytest.raises(accounts.AccountError) as error:
        user_email.save_settings(_user()["id"], **{**FORM, "host": "127.0.0.1"})
    assert error.value.code == "host_private"


def test_suggest_fills_known_providers():
    assert user_email.suggest("x@gmail.com") == {"host": "smtp.gmail.com", "port": 587, "security": "starttls"}
    assert user_email.suggest("x@orange.fr")["security"] == "ssl"
    assert user_email.suggest("x@cabinet-martin.fr") is None


def test_mailer_is_personal_when_configured_else_cabinet_with_reply_to(monkeypatch):
    user = _user()
    monkeypatch.setenv("TMS_MAILER", "none")
    service, reply_to = user_email.mailer_for(user)
    assert isinstance(service, mailer.NullMailer) and reply_to == "dr@gmail.com"
    assert user_email.mailer_for(None)[1] is None
    user_email.save_settings(user["id"], **FORM)
    service, reply_to = user_email.mailer_for(user)
    assert isinstance(service, smtp_mailer.SmtpMailer) and reply_to == "dr@gmail.com"
    assert service.settings.sender == "Dr Martin <dr@gmail.com>"
    assert service.settings.starttls and not service.settings.secure and service.settings.user == "dr@gmail.com"


def test_send_test_records_success_and_failure(monkeypatch):
    user = _user()
    with pytest.raises(accounts.AccountError, match="Aucun email"):
        user_email.send_test(user)
    user_email.save_settings(user["id"], **FORM)
    sent = []
    monkeypatch.setattr(smtp_mailer.SmtpMailer, "send", lambda self, message: sent.append(message))
    result = user_email.send_test(user)
    assert sent[0].to == "dr@gmail.com" and result["status"] == "connected"

    def refuse(self, message):
        raise mailer.MailerError("Identifiant ou mot de passe refusé")

    monkeypatch.setattr(smtp_mailer.SmtpMailer, "send", refuse)
    with pytest.raises(accounts.AccountError) as error:
        user_email.send_test(user)
    assert error.value.code == "send_failed"


def test_changing_settings_clears_the_connected_status(monkeypatch):
    user = _user()
    user_email.save_settings(user["id"], **FORM)
    monkeypatch.setattr(smtp_mailer.SmtpMailer, "send", lambda self, message: None)
    assert user_email.send_test(user)["status"] == "connected"
    assert user_email.save_settings(user["id"], **{**FORM, "password": ""})["status"] == "untested"


def test_routes_are_per_account_and_need_a_session():
    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(auth_api.me_email_router)
    app.add_middleware(auth_api.AuthMiddleware)
    client = TestClient(app)
    one, two = _user("one@gmail.com"), _user("two@gmail.com")
    auth_api.reset_cache()
    assert client.get("/me/email").status_code == 401
    client.post("/auth/login", json={"email": "one@gmail.com", "password": GOOD})
    body = {k: v for k, v in FORM.items()}
    assert client.put("/me/email", json=body, headers=ORIGIN).json()["configured"] is True
    assert "abcd" not in client.get("/me/email").text
    assert client.get("/me/email/suggest", params={"address": "a@free.fr"}).json()["suggestion"]["port"] == 465
    client.post("/auth/logout", headers=ORIGIN)
    client.post("/auth/login", json={"email": "two@gmail.com", "password": GOOD})
    assert client.get("/me/email").json()["configured"] is False
    assert client.delete("/me/email", headers=ORIGIN).json()["configured"] is False
