"""Assistant vocal : transforme ce que dit la personne en champs de formulaire.

Option DÉSACTIVÉE par défaut (TMS_ASSISTANT=on pour l'autoriser). Il ne sauvegarde jamais :
il renvoie des champs que l'interface pré-remplit, l'utilisateur relit puis enregistre. Ce qui
n'a pas été dit reste absent (jamais deviné). Chaque champ renvoyé par le modèle est revalidé ici
avec les mêmes règles que la fiche d'activité (api.py, bilan.py).

Le modèle est joint par une passerelle COMPATIBLE OPENAI (cloud ou local) :
TMS_ASSISTANT_LLM_URL, TMS_ASSISTANT_LLM_KEY (inutile en local), TMS_ASSISTANT_MODEL.
Pour un modèle LOCAL (rien ne sort de la machine), TMS_ASSISTANT_LLM_URL accepte aussi un raccourci :
« ollama », « lmstudio » ou « llamacpp » ; tout autre serveur compatible OpenAI (vLLM, LocalAI…)
se donne par son adresse complète. Sous Docker, le serveur local tourne sur l'hôte : utiliser
http://host.docker.internal:11434/v1 (Ollama). Modèle vide : le premier modèle du serveur est pris.
La transcription souveraine relaie vers la brique « transcription » de Workplace
(TMS_TRANSCRIPTION_URL, TMS_TRANSCRIPTION_KEY) ; sans elle, repli honnête (texte vide).
"""
import json
import os

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from tms_vision import bilan

router = APIRouter(prefix="/assistant", tags=["assistant"])

ZONES = ("neck", "trunk", "upper_arm", "lower_arm", "hand", "foot")
ZONE_LABELS_FR = {
    "neck": "cou", "trunk": "tronc", "upper_arm": "épaule / bras",
    "lower_arm": "avant-bras / coude", "hand": "main / poignet", "foot": "pied / cheville",
}
UNITS = {"minute": 1.0, "hour": 1 / 60, "day": None}  # day : dépend de la durée de la tâche

# À garder alignées avec web/app/bilans/taskForm.ts (WORKSTATION_OPTIONS, BREAK_OPTIONS).
WORKSTATION_OPTIONS = [
    "Assis devant écran", "Debout statique (caisse, atelier)", "Manutention et port de charges",
    "Bras au-dessus des épaules (peinture, plafond)", "Conduite", "Geste répétitif en production",
    "Penché (soins, nettoyage)", "Marche et déplacements",
]
BREAK_OPTIONS = [
    "Aucune pause", "Déjeuner seulement", "Pauses courtes toutes les 2 h",
    "Micro-pauses fréquentes", "Rotation de poste",
]

REQUIRED_TASK_FIELDS = ("name", "zones", "duration")
QUESTIONS_FR = {
    "name": "Quelle tâche est effectuée ?",
    "zones": "Quelles parties du corps sont sollicitées ?",
    "duration": "Combien de temps par jour, ou à quelles heures, cette tâche est-elle faite ?",
}


def enabled() -> bool:
    return os.environ.get("TMS_ASSISTANT", "off").strip().lower() in {"on", "1", "true", "oui"}


LOCAL_PRESETS = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
}


def llm_base_url() -> str:
    value = os.environ.get("TMS_ASSISTANT_LLM_URL", "").strip()
    return LOCAL_PRESETS.get(value.lower(), value).rstrip("/")


def llm_is_local() -> bool:
    value = os.environ.get("TMS_ASSISTANT_LLM_URL", "").strip().lower()
    return value in LOCAL_PRESETS or any(
        host in value for host in ("localhost", "127.0.0.1", "host.docker.internal")
    )


def llm_configured() -> bool:
    return bool(llm_base_url())


def _llm_headers() -> dict:
    key = os.environ.get("TMS_ASSISTANT_LLM_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


async def list_models() -> list[str]:
    """Modèles proposés par le serveur (GET /models, standard OpenAI/Ollama/LM Studio)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{llm_base_url()}/models", headers=_llm_headers())
            response.raise_for_status()
        return [item["id"] for item in response.json()["data"] if "id" in item]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502, detail="Impossible de lire la liste des modèles du serveur."
        ) from error


def transcription_configured() -> bool:
    return bool(os.environ.get("TMS_TRANSCRIPTION_URL", "").strip())


# ── Normalisation des champs proposés par le modèle (logique pure, testée) ─────────────────────

def _number(value, *, minimum=None, maximum=None, exclusive_min=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if minimum is not None and (value <= minimum if exclusive_min else value < minimum):
        return None
    if maximum is not None and value > maximum:
        return None
    return float(value)


def _text(value, limit):
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:limit]


def normalize_task_fields(raw: dict, current: dict | None = None) -> tuple[dict, list[str]]:
    """Garde les seuls champs valides de `raw` ; renvoie (champs, avertissements).

    Clés produites : name, zones, time_slots, activity_hours, zone_cycles_per_minute,
    cycle_seconds, static_seconds, load_kg, days_per_week, workstation, breaks, notes."""
    current = current or {}
    fields: dict = {}
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return fields, ["Réponse du modèle inexploitable."]

    name = _text(raw.get("name"), 120)
    if name:
        fields["name"] = name

    zones_raw = raw.get("zones")
    if isinstance(zones_raw, list):
        zones = [z for z in dict.fromkeys(zones_raw) if z in ZONES]
        if any(z not in ZONES for z in zones_raw):
            warnings.append("Une zone du corps non reconnue a été ignorée.")
        if zones:
            fields["zones"] = zones

    slots_raw = raw.get("time_slots")
    if isinstance(slots_raw, list) and slots_raw:
        slots = [
            {"start": s.get("start"), "end": s.get("end")}
            for s in slots_raw if isinstance(s, dict)
        ]
        try:
            hours = bilan.slots_hours(slots)
        except (ValueError, TypeError, AttributeError):
            hours = None
            warnings.append("Plages horaires ignorées : début, fin ou chevauchement invalide.")
        if hours is not None and 0 < hours <= 24:
            fields["time_slots"] = slots
            fields["activity_hours"] = hours
    if "activity_hours" not in fields:
        hours = _number(raw.get("activity_hours"), minimum=0, maximum=24, exclusive_min=True)
        if hours is not None:
            fields["activity_hours"] = hours
        elif raw.get("activity_hours") is not None:
            warnings.append("Durée ignorée : elle doit être comprise entre 0 et 24 heures.")

    effective_hours = fields.get("activity_hours") or _number(current.get("activity_hours"))
    effective_zones = fields.get("zones") or current.get("zones") or []
    cycles: dict[str, float] = {}
    repetitions = raw.get("zone_repetitions")
    if isinstance(repetitions, dict):
        for zone, item in repetitions.items():
            value = _number(item.get("value"), minimum=0) if isinstance(item, dict) else None
            unit = item.get("unit") if isinstance(item, dict) else None
            if zone not in ZONES or value is None or unit not in UNITS:
                warnings.append("Une fréquence de répétition n'a pas pu être comprise.")
                continue
            if effective_zones and zone not in effective_zones:
                warnings.append(f"Fréquence ignorée : la zone « {ZONE_LABELS_FR[zone]} » n'est pas retenue.")
                continue
            if unit == "day":
                if not effective_hours:
                    warnings.append("Répétitions « par jour » ignorées : durée de la tâche inconnue.")
                    continue
                cycles[zone] = value / (effective_hours * 60)
            else:
                cycles[zone] = value * UNITS[unit]
    if cycles:
        fields["zone_cycles_per_minute"] = cycles

    for key, minimum, exclusive, maximum in (
        ("cycle_seconds", 0, True, None), ("static_seconds", 0, False, None),
        ("load_kg", 0, False, None), ("days_per_week", 0, True, 7),
    ):
        number = _number(raw.get(key), minimum=minimum, maximum=maximum, exclusive_min=exclusive)
        if number is not None:
            fields[key] = number
        elif raw.get(key) is not None:
            warnings.append(f"Valeur ignorée pour « {key} » : hors limites.")

    for key, limit in (("workstation", 200), ("breaks", 200), ("notes", 2000)):
        text = _text(raw.get(key), limit)
        if text:
            fields[key] = text
    return fields, warnings


def missing_task_fields(merged: dict) -> list[str]:
    missing = []
    if not merged.get("name"):
        missing.append("name")
    if not merged.get("zones"):
        missing.append("zones")
    if not merged.get("activity_hours") and not merged.get("time_slots"):
        missing.append("duration")
    return missing


# ── Appel du modèle ────────────────────────────────────────────────────────────────────────────

def build_task_prompt(current: dict) -> str:
    zones = "; ".join(f"{key} = {label}" for key, label in ZONE_LABELS_FR.items())
    return (
        "Tu aides un professionnel de santé à remplir la fiche d'activité d'un poste de travail "
        "(prévention des TMS). Tu reçois ce que la personne vient de dire, en français. "
        "Réponds UNIQUEMENT par un objet JSON, sans texte autour.\n"
        "N'invente RIEN : un champ non mentionné est omis. Ne reprends pas une valeur déjà saisie "
        "sauf si la personne la corrige.\n"
        'Format : {"fields": {...}, "next_question": "..."}\n'
        "Champs possibles dans fields :\n"
        '- name : nom court de la tâche (ex. « Peindre un plafond »)\n'
        f"- zones : liste parmi [{', '.join(ZONES)}] ({zones})\n"
        '- time_slots : [{"start": "08:00", "end": "12:00"}] (HH:MM, 24 h, sans chevauchement)\n'
        "- activity_hours : durée totale de la tâche dans la journée, en heures (0 à 24), "
        "si aucune plage horaire n'est donnée\n"
        '- zone_repetitions : {"upper_arm": {"value": 20, "unit": "minute"}} avec unit parmi '
        "minute, hour, day (nombre de gestes répétés dans cette unité)\n"
        "- cycle_seconds : durée d'un cycle de geste, en secondes\n"
        "- static_seconds : plus longue posture tenue sans bouger, en secondes\n"
        "- load_kg : charge manipulée, en kg\n"
        "- days_per_week : jours par semaine (0 à 7)\n"
        f"- workstation : un choix parmi {json.dumps(WORKSTATION_OPTIONS, ensure_ascii=False)} "
        "ou, si aucun ne convient, une courte description\n"
        f"- breaks : un choix parmi {json.dumps(BREAK_OPTIONS, ensure_ascii=False)} "
        "ou, si aucun ne convient, une courte description\n"
        "- notes : autre information utile\n"
        "next_question : UNE seule question courte, naturelle, pour obtenir l'information "
        "manquante la plus utile (nom, zones, durée ou horaires d'abord), ou une chaîne vide "
        "si la fiche te paraît complète.\n"
        f"Valeurs déjà saisies : {json.dumps(current, ensure_ascii=False)}"
    )


async def chat_json(system: str, history: list[dict], transcript: str) -> dict:
    """Appelle la passerelle compatible OpenAI et renvoie l'objet JSON de la réponse."""
    model = os.environ.get("TMS_ASSISTANT_MODEL", "").strip()
    if not model:
        models = await list_models()
        if not models:
            raise HTTPException(status_code=503, detail="Le serveur n'a aucun modèle installé.")
        model = models[0]
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": transcript},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            url = f"{llm_base_url()}/chat/completions"
            response = await client.post(
                url, json={**payload, "response_format": {"type": "json_object"}},
                headers=_llm_headers(),
            )
            if response.status_code == 400:  # certains serveurs locaux refusent response_format
                response = await client.post(url, json=payload, headers=_llm_headers())
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
        raise HTTPException(
            status_code=502, detail="Le modèle de l'assistant n'a pas répondu."
        ) from error
    # Un modèle local entoure parfois le JSON de texte : on isole le premier objet.
    content = content.strip()
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        content = content[start:end + 1]
    try:
        parsed = json.loads(content)
    except ValueError as error:
        raise HTTPException(
            status_code=502, detail="L'assistant n'a pas compris la réponse du modèle."
        ) from error
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502, detail="L'assistant n'a pas compris la réponse du modèle."
        )
    return parsed


# ── Routes ─────────────────────────────────────────────────────────────────────────────────────

class HistoryTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class ExtractBody(BaseModel):
    form: str = Field(pattern="^task$")
    transcript: str = Field(min_length=1, max_length=4000)
    current_values: dict = Field(default_factory=dict)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=20)
    mode: str = Field(default="dictation", pattern="^(dictation|guided)$")


@router.get("/config")
async def get_config() -> dict:
    return {
        "enabled": enabled(),
        "llm_configured": llm_configured(),
        "llm_local": llm_configured() and llm_is_local(),
        "transcription_configured": transcription_configured(),
    }


@router.get("/models")
async def get_models() -> dict:
    if not enabled():
        raise HTTPException(status_code=403, detail="L'assistant vocal n'est pas activé.")
    if not llm_configured():
        raise HTTPException(status_code=503, detail="Aucun modèle n'est configuré pour l'assistant.")
    return {"models": await list_models()}


@router.post("/extract")
async def extract(body: ExtractBody) -> dict:
    if not enabled():
        raise HTTPException(status_code=403, detail="L'assistant vocal n'est pas activé.")
    if not llm_configured():
        raise HTTPException(status_code=503, detail="Aucun modèle n'est configuré pour l'assistant.")
    raw = await chat_json(
        build_task_prompt(body.current_values),
        [turn.model_dump() for turn in body.history],
        body.transcript,
    )
    fields, warnings = normalize_task_fields(raw.get("fields", {}), body.current_values)
    merged = {**body.current_values, **fields}
    missing = missing_task_fields(merged)
    question = ""
    if body.mode == "guided":
        question = _text(raw.get("next_question"), 300) or ""
        if not question and missing:
            question = QUESTIONS_FR[missing[0]]
    return {"fields": fields, "missing": missing, "next_question": question, "warnings": warnings}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    if not enabled():
        raise HTTPException(status_code=403, detail="L'assistant vocal n'est pas activé.")
    if not transcription_configured():
        return {"text": "", "backend": None, "placeholder": True}
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=422, detail="Enregistrement audio vide.")
    base = os.environ["TMS_TRANSCRIPTION_URL"].strip().rstrip("/")
    headers = {}
    key = os.environ.get("TMS_TRANSCRIPTION_KEY", "").strip()
    if key:
        headers["X-API-Key"] = key
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{base}/transcrire",
                files={"fichier": (file.filename or "audio.webm", audio, file.content_type)},
                data={"langue": "fr"},
                headers=headers,
            )
            response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(
            status_code=502, detail="Le service de transcription n'a pas répondu."
        ) from error
    return {
        "text": str(result.get("texte", "")).strip(),
        "backend": result.get("backend"),
        "placeholder": bool(result.get("place_holder", False)),
    }
