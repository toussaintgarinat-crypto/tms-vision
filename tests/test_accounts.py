from datetime import timedelta

import pytest

from tms_vision import accounts, storage

GOOD = "correct horse battery"


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")


def _user(email="Martin@Cabinet.fr", roles=("osteopathe",), password=GOOD):
    return accounts.create_user(email, "Théo Martin", password, list(roles))


def test_create_user_normalizes_email_and_orders_roles():
    user = _user(roles=("osteopathe", "praticien"))
    assert user["email"] == "martin@cabinet.fr"
    assert user["roles"] == ["praticien", "osteopathe"]
    assert user["active"] is True
    assert "password" not in str(user)


def test_password_is_hashed_with_argon2id_never_stored_clear():
    user = _user()
    conn = accounts._connect()
    stored = conn.execute("SELECT password_hash FROM users WHERE id = ?", [user["id"]]).fetchone()[0]
    conn.close()
    assert stored.startswith("$argon2id$")
    assert GOOD not in stored


@pytest.mark.parametrize(
    "password, code",
    [("court", "password_too_short"), ("motdepasse123", "password_too_common"),
     ("azertyazerty", "password_too_common"), ("aaaaaaaaaaaaaaa", "password_too_common"),
     ("martin@cabinet.fr", "password_is_email")],
)
def test_weak_passwords_are_refused(password, code):
    with pytest.raises(accounts.AccountError) as error:
        _user(password=password)
    assert error.value.code == code


def test_duplicate_email_invalid_email_and_unknown_role():
    _user()
    with pytest.raises(accounts.AccountError, match="existe déjà"):
        _user(email="MARTIN@cabinet.fr")
    with pytest.raises(accounts.AccountError, match="invalide"):
        accounts.create_user("pas-un-email", "X", GOOD, ["praticien"])
    with pytest.raises(accounts.AccountError, match="Rôles"):
        accounts.create_user("a@b.fr", "X", GOOD, ["dieu"])


def test_login_success_and_same_message_for_every_failure():
    user = _user()
    assert accounts.authenticate("MARTIN@cabinet.fr", GOOD, "1.2.3.4")["id"] == user["id"]
    messages = set()
    for email, password in (("martin@cabinet.fr", "mauvais mot de passe"), ("inconnu@x.fr", GOOD)):
        with pytest.raises(accounts.AccountError) as error:
            accounts.authenticate(email, password, "1.2.3.4")
        messages.add((error.value.code, str(error.value)))
    assert len(messages) == 1


def test_disabled_account_cannot_log_in_and_loses_sessions():
    admin = _user(email="admin@x.fr", roles=("administrateur",))
    user = _user()
    token = accounts.create_session(user["id"])
    assert accounts.user_for_token(token)["id"] == user["id"]
    accounts.update_user(user["id"], active=False, actor=admin["id"])
    assert accounts.user_for_token(token) is None
    with pytest.raises(accounts.AccountError):
        accounts.authenticate(user["email"], GOOD)


def test_repeated_failures_slow_the_account_down_then_success_resets():
    _user()
    for _ in range(accounts.ACCOUNT_FREE_ATTEMPTS):
        with pytest.raises(accounts.AccountError) as error:
            accounts.authenticate("martin@cabinet.fr", "faux", "9.9.9.9")
        assert error.value.code == "invalid_credentials"
    with pytest.raises(accounts.AccountError) as error:
        accounts.authenticate("martin@cabinet.fr", GOOD, "9.9.9.9")  # même le bon mot de passe
    assert error.value.code == "too_many_attempts"
    assert error.value.retry_after and error.value.retry_after >= 1


def test_throttle_per_address_blocks_other_accounts():
    for index in range(accounts.ADDRESS_FREE_ATTEMPTS):
        with pytest.raises(accounts.AccountError):
            accounts.authenticate(f"inconnu{index}@x.fr", "faux", "8.8.8.8")
    with pytest.raises(accounts.AccountError) as error:
        accounts.authenticate("autre@x.fr", "faux", "8.8.8.8")
    assert error.value.code == "too_many_attempts"


def test_session_lifecycle_and_only_hash_stored():
    user = _user()
    token = accounts.create_session(user["id"])
    conn = accounts._connect()
    hashes = [row[0] for row in conn.execute("SELECT token_hash FROM sessions").fetchall()]
    conn.close()
    assert token not in hashes and len(hashes[0]) == 64
    assert accounts.user_for_token(token)["email"] == user["email"]
    assert accounts.user_for_token("n'importe quoi") is None
    assert accounts.user_for_token(None) is None
    accounts.revoke_session(token)
    assert accounts.user_for_token(token) is None


def test_expired_session_is_refused():
    user = _user()
    token = accounts.create_session(user["id"])
    conn = accounts._connect()
    conn.execute("UPDATE sessions SET expires_at = ?", [accounts._now() - timedelta(minutes=1)])
    conn.close()
    assert accounts.user_for_token(token) is None


def test_absolute_session_cap():
    user = _user()
    token = accounts.create_session(user["id"])
    conn = accounts._connect()
    conn.execute("UPDATE sessions SET created_at = ?", [accounts._now() - timedelta(days=accounts.SESSION_MAX_DAYS + 1)])
    conn.close()
    assert accounts.user_for_token(token) is None


def test_change_password_checks_current_and_closes_other_sessions():
    user = _user()
    keep = accounts.create_session(user["id"])
    other = accounts.create_session(user["id"])
    with pytest.raises(accounts.AccountError):
        accounts.change_password(user["id"], "faux", "un autre mot de passe", keep_token=keep)
    accounts.change_password(user["id"], GOOD, "un autre mot de passe", keep_token=keep)
    assert accounts.user_for_token(keep) is not None
    assert accounts.user_for_token(other) is None
    accounts.authenticate(user["email"], "un autre mot de passe")


def test_last_active_administrator_cannot_be_removed():
    admin = _user(email="admin@x.fr", roles=("administrateur",))
    with pytest.raises(accounts.AccountError) as error:
        accounts.update_user(admin["id"], active=False)
    assert error.value.code == "last_admin"
    with pytest.raises(accounts.AccountError):
        accounts.update_user(admin["id"], roles=["praticien"])
    second = _user(email="b@x.fr", roles=("administrateur", "praticien"))
    accounts.update_user(admin["id"], roles=["praticien"])
    assert accounts.get_user(second["id"])["roles"] == ["praticien", "administrateur"]


def test_audit_log_records_events_without_secrets():
    user = _user()
    accounts.authenticate(user["email"], GOOD, "1.1.1.1")
    with pytest.raises(accounts.AccountError):
        accounts.authenticate(user["email"], "mot de passe secret", "1.1.1.1")
    entries = accounts.list_audit()
    actions = [entry["action"] for entry in entries]
    assert {"user.create", "login.success", "login.failed"} <= set(actions)
    assert "mot de passe secret" not in str(entries) and GOOD not in str(entries)


def test_has_users():
    assert accounts.has_users() is False
    _user()
    assert accounts.has_users() is True
