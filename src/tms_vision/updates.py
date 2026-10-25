"""Vérifie si une version plus récente de l'application est publiée sur GitHub (Releases). Utilisé
par l'application de bureau (desktop.py, qui active TMS_CHECK_UPDATES) : elle prévient le praticien
sans jamais se mettre à jour elle-même. Hors ligne ou en cas d'erreur, on ne signale rien."""
import json
import re
import time
import urllib.request

RELEASES_URL = "https://api.github.com/repos/toussaintgarinat-crypto/tms-vision/releases/latest"
CACHE_SECONDS = 6 * 3600
TIMEOUT_SECONDS = 5

_cache: dict = {"at": None, "result": None}


def parse_version(text: str | None) -> tuple[int, ...] | None:
    """« v1.2.0 » ou « 1.2.0 » -> (1, 2, 0) ; None si ce n'est pas un numéro de version."""
    match = re.fullmatch(r"v?(\d+(?:\.\d+){1,3})", (text or "").strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def is_newer(latest: str | None, current: str | None) -> bool:
    latest_version, current_version = parse_version(latest), parse_version(current)
    return latest_version is not None and current_version is not None and latest_version > current_version


def fetch_latest_release(url: str = RELEASES_URL) -> dict | None:
    """Dernière version publiée : {"version", "url"} (page de téléchargement), ou None."""
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "tms-vision"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except (OSError, ValueError):
        return None
    tag, page = data.get("tag_name"), data.get("html_url")
    if parse_version(tag) is None or not isinstance(page, str) or not page.startswith("https://"):
        return None
    return {"version": tag.lstrip("v"), "url": page}


def check(current: str, *, now: float | None = None) -> dict:
    """{"available": bool, "version": str | None, "url": str | None}. Le résultat est gardé 6 h
    pour ne pas interroger GitHub à chaque page ; un échec n'est pas gardé (nouvel essai au
    prochain appel)."""
    moment = time.monotonic() if now is None else now
    if _cache["at"] is not None and moment - _cache["at"] < CACHE_SECONDS:
        latest = _cache["result"]
    else:
        latest = fetch_latest_release()
        if latest is not None:
            _cache.update(at=moment, result=latest)
    if latest is not None and is_newer(latest["version"], current):
        return {"available": True, **latest}
    return {"available": False, "version": None, "url": None}
