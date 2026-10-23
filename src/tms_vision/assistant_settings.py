"""Réglages de l'assistant vocal : fournisseur d'IA, adresse, clé, modèle, transcription.

Ils se règlent depuis l'interface (roue ⚙ du bandeau de l'assistant) et sont rangés dans
data/assistant.json (droits 0600, sauvegardé avec data/). La clé n'est JAMAIS renvoyée au navigateur.
Les variables d'environnement TMS_ASSISTANT* restent valables comme réglages par défaut ; ce qui est
enregistré depuis l'interface les remplace. TMS_ASSISTANT=off les verrouille : l'assistant reste éteint.
"""
import json
import os
from pathlib import Path

from tms_vision import storage

PROVIDERS = [
    {"id": "ollama", "label": "Ollama (local)", "base_url": "http://localhost:11434/v1",
     "local": True, "key_required": False,
     "hint": "Installez Ollama sur cette machine, puis : ollama pull mistral. Rien ne quitte la machine."},
    {"id": "lmstudio", "label": "LM Studio (local)", "base_url": "http://localhost:1234/v1",
     "local": True, "key_required": False,
     "hint": "Dans LM Studio, démarrez le serveur local (onglet Developer)."},
    {"id": "llamacpp", "label": "llama.cpp (local)", "base_url": "http://localhost:8080/v1",
     "local": True, "key_required": False,
     "hint": "Lancez llama-server avec votre modèle."},
    {"id": "openrouter", "label": "OpenRouter (en ligne)", "base_url": "https://openrouter.ai/api/v1",
     "local": False, "key_required": True,
     "hint": "Clé sur openrouter.ai/keys. Le texte dicté est envoyé à ce service."},
    {"id": "openai", "label": "OpenAI (en ligne)", "base_url": "https://api.openai.com/v1",
     "local": False, "key_required": True,
     "hint": "Clé sur platform.openai.com. Le texte dicté est envoyé à ce service."},
    {"id": "deepseek", "label": "DeepSeek (en ligne)", "base_url": "https://api.deepseek.com/v1",
     "local": False, "key_required": True,
     "hint": "Clé sur platform.deepseek.com. Le texte dicté est envoyé à ce service."},
    {"id": "custom", "label": "Autre serveur compatible OpenAI", "base_url": "",
     "local": False, "key_required": False,
     "hint": "vLLM, LocalAI, Mistral, Groq… : adresse complète terminant par /v1, clé si besoin."},
]
PROVIDER_IDS = {provider["id"] for provider in PROVIDERS}
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "host.docker.internal")
FILE_FIELDS = ("enabled", "provider", "base_url", "model", "api_key",
               "transcription_url", "transcription_key")


def settings_path() -> Path:
    return storage.DB_PATH.parent / "assistant.json"


def load_file() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {key: data[key] for key in FILE_FIELDS if key in data} if isinstance(data, dict) else {}


def save_file(data: dict) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def _in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def resolve_url(value: str) -> str:
    """Adresse utilisable : raccourci (« ollama ») développé ; sous Docker, « localhost » désigne
    le conteneur lui-même, le serveur local est sur la machine hôte."""
    value = (value or "").strip()
    for provider in PROVIDERS:
        if value.lower() == provider["id"] and provider["base_url"]:
            value = provider["base_url"]
    value = value.rstrip("/")
    if _in_docker():
        value = value.replace("//localhost", "//host.docker.internal").replace(
            "//127.0.0.1", "//host.docker.internal")
    return value


def is_local_url(url: str) -> bool:
    return any(host in url for host in _LOCAL_HOSTS)


def _env_enabled() -> bool | None:
    """True / False si l'environnement tranche, None s'il laisse l'interface décider."""
    value = os.environ.get("TMS_ASSISTANT", "").strip().lower()
    if value in {"on", "1", "true", "oui"}:
        return True
    if value in {"off", "0", "false", "non"}:
        return False
    return None


def effective(overrides: dict | None = None) -> dict:
    """Réglages réellement utilisés : environnement < fichier < `overrides` (essai non enregistré)."""
    env = os.environ.get
    merged = {
        "provider": "", "base_url": env("TMS_ASSISTANT_LLM_URL", "").strip(),
        "model": env("TMS_ASSISTANT_MODEL", "").strip(),
        "api_key": env("TMS_ASSISTANT_LLM_KEY", "").strip(),
        "transcription_url": env("TMS_TRANSCRIPTION_URL", "").strip(),
        "transcription_key": env("TMS_TRANSCRIPTION_KEY", "").strip(),
    }
    file_data = load_file()
    for source in (file_data, overrides or {}):
        for key, value in source.items():
            if key != "enabled" and isinstance(value, str) and (value.strip() or key == "api_key"):
                merged[key] = value.strip()
    forced = _env_enabled()
    merged["enabled"] = forced if forced is not None else bool(file_data.get("enabled", False))
    merged["enabled_locked"] = forced is not None
    merged["base_url_resolved"] = resolve_url(merged["base_url"])
    merged["local"] = bool(merged["base_url_resolved"]) and is_local_url(merged["base_url_resolved"])
    return merged


def public_view() -> dict:
    """Ce que le navigateur peut voir : jamais les clés."""
    current = effective()
    return {
        "enabled": current["enabled"], "enabled_locked": current["enabled_locked"],
        "provider": current["provider"], "base_url": current["base_url"], "model": current["model"],
        "key_set": bool(current["api_key"]),
        "transcription_url": current["transcription_url"],
        "transcription_key_set": bool(current["transcription_key"]),
        "local": current["local"], "providers": PROVIDERS,
    }


def update(changes: dict) -> None:
    """Enregistre `changes`. Pour une clé : absente = inchangée, chaîne vide = effacée."""
    data = load_file()
    for key in FILE_FIELDS:
        if key not in changes or changes[key] is None:
            continue
        value = changes[key]
        if key == "enabled":
            data[key] = bool(value)
        else:
            data[key] = str(value).strip()
    save_file(data)
