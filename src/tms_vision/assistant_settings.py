"""Réglages de l'assistant vocal : fournisseur d'IA, adresse, clé, modèle, transcription.

Fournisseur, adresse, modèle et transcription se règlent depuis l'interface (roue ⚙ du bandeau de
l'assistant) et sont rangés dans data/assistant.json (sauvegardé avec data/, ignoré par Git).
Les CLÉS (TMS_ASSISTANT_LLM_KEY, TMS_TRANSCRIPTION_KEY) ne sont lues QUE dans l'environnement, donc
dans le fichier .env : le site ne les enregistre jamais et ne les renvoie jamais au navigateur.
L'activation se fait UNIQUEMENT depuis l'interface (interrupteur du panneau ⚙) : éteint tant que le
praticien ne l'a pas allumé. La variable TMS_ASSISTANT n'existe plus (ignorée). Les autres variables
TMS_ASSISTANT_* restent valables comme réglages par défaut ; ce qui est enregistré sur le site les remplace.
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
FILE_FIELDS = ("enabled", "provider", "base_url", "model", "transcription_url")
KEY_ENV = "TMS_ASSISTANT_LLM_KEY"
TRANSCRIPTION_KEY_ENV = "TMS_TRANSCRIPTION_KEY"


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


def effective(overrides: dict | None = None) -> dict:
    """Réglages réellement utilisés : environnement < fichier < `overrides` (essai non enregistré).
    Les clés viennent toujours de l'environnement."""
    env = os.environ.get
    merged = {
        "provider": "", "base_url": env("TMS_ASSISTANT_LLM_URL", "").strip(),
        "model": env("TMS_ASSISTANT_MODEL", "").strip(),
        "api_key": env(KEY_ENV, "").strip(),
        "transcription_url": env("TMS_TRANSCRIPTION_URL", "").strip(),
        "transcription_key": env(TRANSCRIPTION_KEY_ENV, "").strip(),
    }
    file_data = load_file()
    for source in (file_data, overrides or {}):
        for key, value in source.items():
            if key in FILE_FIELDS and key != "enabled" and isinstance(value, str) and value.strip():
                merged[key] = value.strip()
    merged["enabled"] = bool(file_data.get("enabled", False))
    merged["base_url_resolved"] = resolve_url(merged["base_url"])
    merged["local"] = bool(merged["base_url_resolved"]) and is_local_url(merged["base_url_resolved"])
    return merged


def public_view() -> dict:
    """Ce que le navigateur peut voir : jamais les clés."""
    current = effective()
    return {
        "enabled": current["enabled"],
        "provider": current["provider"], "base_url": current["base_url"], "model": current["model"],
        "key_set": bool(current["api_key"]), "key_env": KEY_ENV,
        "transcription_url": current["transcription_url"],
        "transcription_key_set": bool(current["transcription_key"]),
        "transcription_key_env": TRANSCRIPTION_KEY_ENV,
        "local": current["local"], "providers": PROVIDERS,
    }


def update(changes: dict) -> None:
    """Enregistre `changes` (jamais de clé : elles restent dans le fichier .env)."""
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
