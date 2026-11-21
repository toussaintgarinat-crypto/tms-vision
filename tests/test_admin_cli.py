import pytest

from tms_vision import accounts, admin_cli, storage

GOOD = "correct horse battery"


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    monkeypatch.setenv("TMS_ADMIN_PASSWORD", GOOD)


def test_create_admin_gives_both_roles_and_journals_it(capsys):
    assert admin_cli.main(["create-admin", "--email", "Dr@Cabinet.fr", "--name", "Dr Martin"]) == 0
    (user,) = accounts.list_users()
    assert user["email"] == "dr@cabinet.fr" and user["roles"] == ["praticien", "administrateur"]
    assert "admin.create_cli" in [entry["action"] for entry in accounts.list_audit()]
    assert GOOD not in capsys.readouterr().out
    accounts.authenticate("dr@cabinet.fr", GOOD)


def test_create_admin_refuses_a_second_one(capsys):
    admin_cli.main(["create-admin", "--email", "a@x.fr", "--name", "A"])
    assert admin_cli.main(["create-admin", "--email", "b@x.fr", "--name", "B"]) == 1
    assert "existe déjà" in capsys.readouterr().err
    assert len(accounts.list_users()) == 1


def test_weak_password_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("TMS_ADMIN_PASSWORD", "court")
    assert admin_cli.main(["create-admin", "--email", "a@x.fr", "--name", "A"]) == 1
    assert "au moins" in capsys.readouterr().err
    assert accounts.list_users() == []


def test_reset_password_closes_sessions(monkeypatch):
    admin_cli.main(["create-admin", "--email", "a@x.fr", "--name", "A"])
    user = accounts.list_users()[0]
    token = accounts.create_session(user["id"])
    monkeypatch.setenv("TMS_ADMIN_PASSWORD", "un nouveau mot de passe")
    assert admin_cli.main(["reset-password", "--email", "a@x.fr"]) == 0
    assert accounts.user_for_token(token) is None
    accounts.authenticate("a@x.fr", "un nouveau mot de passe")
    assert admin_cli.main(["reset-password", "--email", "inconnu@x.fr"]) == 1
