import pytest
from fastapi.testclient import TestClient

from tms_vision import assistant, assistant_settings, storage
from tms_vision.api import app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Les réglages vont dans un dossier temporaire ; l'environnement de départ est vide."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    for name in ("TMS_ASSISTANT", "TMS_ASSISTANT_LLM_URL", "TMS_ASSISTANT_LLM_KEY",
                 "TMS_ASSISTANT_MODEL", "TMS_TRANSCRIPTION_URL", "TMS_TRANSCRIPTION_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_normalize_keeps_valid_fields_and_derives_hours_from_slots():
    fields, warnings = assistant.normalize_task_fields({
        "name": "  Peindre un plafond ",
        "zones": ["upper_arm", "neck", "inconnue"],
        "time_slots": [{"start": "08:00", "end": "12:00"}],
        "zone_repetitions": {"upper_arm": {"value": 20, "unit": "minute"}},
        "load_kg": 3,
    })
    assert fields["name"] == "Peindre un plafond"
    assert fields["zones"] == ["upper_arm", "neck"]
    assert fields["activity_hours"] == 4.0
    assert fields["zone_cycles_per_minute"] == {"upper_arm": 20.0}
    assert fields["load_kg"] == 3.0
    assert any("zone" in w for w in warnings)


def test_normalize_converts_units_and_drops_what_it_cannot_trust():
    fields, warnings = assistant.normalize_task_fields({
        "zones": ["hand"],
        "activity_hours": 4,
        "zone_repetitions": {
            "hand": {"value": 120, "unit": "hour"},
            "foot": {"value": 5, "unit": "minute"},
        },
        "time_slots": [{"start": "10:00", "end": "09:00"}],
        "days_per_week": 9,
    })
    assert fields["zone_cycles_per_minute"] == {"hand": 2.0}
    assert "time_slots" not in fields and fields["activity_hours"] == 4.0
    assert "days_per_week" not in fields
    assert len(warnings) == 3


def test_normalize_per_day_needs_known_duration():
    fields, _ = assistant.normalize_task_fields(
        {"zones": ["hand"], "zone_repetitions": {"hand": {"value": 480, "unit": "day"}}}
    )
    assert "zone_cycles_per_minute" not in fields
    fields, _ = assistant.normalize_task_fields(
        {"zone_repetitions": {"hand": {"value": 480, "unit": "day"}}},
        current={"zones": ["hand"], "activity_hours": 4},
    )
    assert fields["zone_cycles_per_minute"] == {"hand": 2.0}


def test_normalize_rejects_garbage():
    assert assistant.normalize_task_fields("pas un objet")[0] == {}
    fields, _ = assistant.normalize_task_fields({"name": 12, "zones": "neck", "load_kg": True})
    assert fields == {}


def test_missing_fields():
    assert assistant.missing_task_fields({}) == ["name", "zones", "duration"]
    assert assistant.missing_task_fields({"name": "a", "zones": ["neck"], "activity_hours": 1}) == []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TMS_ASSISTANT_LLM_URL", "http://llm.test/v1")
    test_client = TestClient(app)
    test_client.put("/assistant/settings", json={"enabled": True})
    return test_client


def _fake_llm(monkeypatch, reply):
    async def fake(system, history, transcript):
        fake.calls.append((system, history, transcript))
        return reply
    fake.calls = []
    monkeypatch.setattr(assistant, "chat_json", fake)
    return fake


def test_disabled_by_default():
    client = TestClient(app)
    assert client.get("/assistant/config").json()["enabled"] is False
    response = client.post("/assistant/extract", json={"form": "task", "transcript": "bonjour"})
    assert response.status_code == 403


def test_extract_requires_a_configured_model(monkeypatch):
    test_client = TestClient(app)
    test_client.put("/assistant/settings", json={"enabled": True})
    response = test_client.post("/assistant/extract", json={"form": "task", "transcript": "x"})
    assert response.status_code == 503


def test_extract_dictation_returns_fields_and_missing(client, monkeypatch):
    fake = _fake_llm(monkeypatch, {"fields": {"name": "Saisie", "zones": ["hand"]},
                                   "next_question": "Combien de temps ?"})
    response = client.post("/assistant/extract", json={
        "form": "task", "transcript": "Il fait de la saisie avec les mains",
    })
    body = response.json()
    assert body["fields"] == {"name": "Saisie", "zones": ["hand"]}
    assert body["missing"] == ["duration"]
    assert body["next_question"] == ""  # question seulement en mode guidé
    assert fake.calls[0][2] == "Il fait de la saisie avec les mains"


def test_extract_guided_asks_a_question_and_falls_back_to_a_default(client, monkeypatch):
    _fake_llm(monkeypatch, {"fields": {"name": "Saisie"}, "next_question": "Quelles zones ?"})
    body = client.post("/assistant/extract", json={
        "form": "task", "transcript": "saisie", "mode": "guided",
    }).json()
    assert body["next_question"] == "Quelles zones ?"
    _fake_llm(monkeypatch, {"fields": {}})
    body = client.post("/assistant/extract", json={
        "form": "task", "transcript": "euh", "mode": "guided",
        "current_values": {"name": "Saisie"},
    }).json()
    assert body["next_question"] == assistant.QUESTIONS_FR["zones"]


def test_transcribe_placeholder_without_service(client, monkeypatch):
    monkeypatch.delenv("TMS_TRANSCRIPTION_URL", raising=False)
    response = client.post("/assistant/transcribe", files={"file": ("a.webm", b"x", "audio/webm")})
    assert response.json() == {"text": "", "backend": None, "placeholder": True}


def _mock_llm_server(monkeypatch, handler):
    import httpx
    real = httpx.AsyncClient
    monkeypatch.setattr(
        assistant.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


def test_local_presets_and_detection(monkeypatch):
    monkeypatch.setenv("TMS_ASSISTANT_LLM_URL", "Ollama")
    assert assistant.llm_base_url() == "http://localhost:11434/v1" and assistant.llm_is_local()
    monkeypatch.setenv("TMS_ASSISTANT_LLM_URL", "http://host.docker.internal:11434/v1/")
    assert assistant.llm_base_url() == "http://host.docker.internal:11434/v1"
    assert assistant.llm_is_local()
    monkeypatch.setenv("TMS_ASSISTANT_LLM_URL", "https://api.exemple.com/v1")
    assert not assistant.llm_is_local()


def test_local_preset_targets_the_host_inside_docker(monkeypatch):
    monkeypatch.setenv("TMS_ASSISTANT_LLM_URL", "ollama")
    monkeypatch.setattr(assistant_settings, "_in_docker", lambda: True)
    assert assistant.llm_base_url() == "http://host.docker.internal:11434/v1"


@pytest.mark.anyio
async def test_chat_json_local_model_without_key_picks_first_model_and_retries(monkeypatch):
    import httpx
    monkeypatch.setenv("TMS_ASSISTANT_LLM_URL", "ollama")
    monkeypatch.delenv("TMS_ASSISTANT_MODEL", raising=False)
    monkeypatch.delenv("TMS_ASSISTANT_LLM_KEY", raising=False)
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "mistral:7b"}, {"id": "autre"}]})
        body = request.read()
        if b"response_format" in body:
            return httpx.Response(400, json={"error": "non supporté"})
        return httpx.Response(200, json={"choices": [{"message": {
            "content": 'Voici : {"fields": {"name": "Saisie"}} merci'}}]})

    _mock_llm_server(monkeypatch, handler)
    result = await assistant.chat_json("sys", [], "texte")
    assert result == {"fields": {"name": "Saisie"}}
    assert all("authorization" not in r.headers for r in seen)
    assert b"mistral:7b" in seen[-1].read()


@pytest.mark.anyio
async def test_chat_json_reports_unreachable_server(monkeypatch):
    import httpx
    from fastapi import HTTPException
    monkeypatch.setenv("TMS_ASSISTANT_LLM_URL", "ollama")
    monkeypatch.setenv("TMS_ASSISTANT_MODEL", "m")

    def handler(request):
        raise httpx.ConnectError("refusé")

    _mock_llm_server(monkeypatch, handler)
    with pytest.raises(HTTPException) as error:
        await assistant.chat_json("sys", [], "texte")
    assert error.value.status_code == 502


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_settings_saved_from_the_interface_enable_and_configure_the_assistant(monkeypatch):
    client = TestClient(app)
    view = client.get("/assistant/settings").json()
    assert view["enabled"] is False and view["provider"] == "" and view["key_set"] is False
    assert {p["id"] for p in view["providers"]} >= {"ollama", "openrouter", "custom"}

    monkeypatch.setenv("TMS_ASSISTANT_LLM_KEY", "sk-secret")
    view = client.put("/assistant/settings", json={
        "enabled": True, "provider": "openrouter", "base_url": "https://openrouter.ai/api/v1",
        "model": "mistralai/mistral-small",
        # une clé envoyée par un vieux navigateur ne doit jamais être enregistrée
        "api_key": "sk-ne-doit-pas-etre-gardee",
    }).json()
    assert view["enabled"] is True and view["key_set"] is True and view["key_env"] == "TMS_ASSISTANT_LLM_KEY"
    assert "sk-secret" not in str(view)
    config = client.get("/assistant/config").json()
    assert config["enabled"] and config["llm_configured"] and not config["llm_local"]
    saved = assistant_settings.settings_path().read_text()
    assert "sk-" not in saved and "api_key" not in saved and "openrouter" in saved
    assert assistant_settings.effective()["api_key"] == "sk-secret"  # vient de l'environnement


def test_a_key_left_in_an_old_settings_file_is_ignored(monkeypatch):
    assistant_settings.save_file({"enabled": True, "base_url": "ollama", "api_key": "sk-vieille"})
    assert assistant_settings.effective()["api_key"] == ""


def test_settings_validation(tmp_path):
    client = TestClient(app)
    assert client.put("/assistant/settings", json={"provider": "inconnu"}).status_code == 422
    assert client.put("/assistant/settings", json={"base_url": "ftp://x"}).status_code == 422
    assert client.put("/assistant/settings", json={"base_url": "ollama"}).status_code == 200


def test_assistant_is_off_by_default_and_only_the_interface_switches_it(monkeypatch):
    client = TestClient(app)
    assert client.get("/assistant/config").json()["enabled"] is False
    # l'ancienne variable est ignorée, dans un sens comme dans l'autre
    monkeypatch.setenv("TMS_ASSISTANT", "on")
    assert client.get("/assistant/config").json()["enabled"] is False
    client.put("/assistant/settings", json={"enabled": True, "base_url": "ollama"})
    monkeypatch.setenv("TMS_ASSISTANT", "off")
    assert client.get("/assistant/config").json()["enabled"] is True
    assert client.put("/assistant/settings", json={"enabled": False}).json()["enabled"] is False
    assert client.post("/assistant/extract", json={"form": "task", "transcript": "x"}).status_code == 403
    monkeypatch.delenv("TMS_ASSISTANT")
    monkeypatch.setenv("TMS_ASSISTANT_MODEL", "mistral:7b")
    assert client.get("/assistant/settings").json()["model"] == "mistral:7b"


def test_connection_test_reports_models_or_a_clear_failure(monkeypatch):
    import httpx
    client = TestClient(app)

    def handler(request):
        if "ok.test" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "m1"}, {"id": "m2"}]})
        raise httpx.ConnectError("refusé")

    _mock_llm_server(monkeypatch, handler)
    good = client.post("/assistant/settings/test", json={"base_url": "https://ok.test/v1"}).json()
    assert good["ok"] and good["models"] == ["m1", "m2"]
    bad = client.post("/assistant/settings/test", json={"base_url": "http://ko.test/v1"}).json()
    assert not bad["ok"] and "n'a pas répondu" in bad["message"]
    assert not client.post("/assistant/settings/test", json={}).json()["ok"]
