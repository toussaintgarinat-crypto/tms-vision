import pytest

from tms_vision import updates


@pytest.mark.parametrize("text, expected", [
    ("v1.2.0", (1, 2, 0)), ("1.10.3", (1, 10, 3)), (" v2.0 ", (2, 0)),
    ("latest", None), ("", None), (None, None), ("v1.2.0-beta", None),
])
def test_parse_version(text, expected):
    assert updates.parse_version(text) == expected


def test_is_newer_compares_numbers_not_text():
    assert updates.is_newer("v1.10.0", "1.9.0")
    assert not updates.is_newer("1.0.0", "1.0.0")
    assert not updates.is_newer("0.9.0", "1.0.0")
    assert not updates.is_newer("n'importe quoi", "1.0.0")
    assert not updates.is_newer("1.1.0", "inconnue")


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(updates, "_cache", {"at": None, "result": None})


def _release(version="1.2.0"):
    return {"version": version, "url": f"https://github.com/x/y/releases/tag/v{version}"}


def test_check_reports_a_newer_release_and_keeps_it_for_six_hours(monkeypatch):
    calls = []
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: calls.append(1) or _release())

    first = updates.check("1.0.0", now=100.0)
    second = updates.check("1.0.0", now=100.0 + 3600)
    later = updates.check("1.0.0", now=100.0 + updates.CACHE_SECONDS + 1)

    assert first == {"available": True, **_release()} == second == later
    assert len(calls) == 2


def test_check_is_quiet_when_up_to_date_or_offline_and_retries_after_a_failure(monkeypatch):
    answers = iter([None, _release("1.0.0"), _release("1.0.0")])
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: next(answers))
    none = {"available": False, "version": None, "url": None}

    assert updates.check("1.0.0", now=1.0) == none  # hors ligne
    assert updates.check("1.0.0", now=2.0) == none  # à jour (la panne n'a pas été gardée)
    assert updates.check("1.0.0", now=3.0) == none  # à jour, depuis le cache


def test_fetch_latest_release_reads_the_github_answer(monkeypatch):
    import io
    import json

    def fake_urlopen(request, timeout):
        return io.BytesIO(json.dumps({
            "tag_name": "v1.4.0", "html_url": "https://github.com/x/y/releases/tag/v1.4.0",
        }).encode())

    monkeypatch.setattr(updates.urllib.request, "urlopen", fake_urlopen)
    assert updates.fetch_latest_release() == {
        "version": "1.4.0", "url": "https://github.com/x/y/releases/tag/v1.4.0",
    }

    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda r, timeout: io.BytesIO(b'{"tag_name": "x"}'))
    assert updates.fetch_latest_release() is None

    def offline(request, timeout):
        raise OSError("pas de réseau")

    monkeypatch.setattr(updates.urllib.request, "urlopen", offline)
    assert updates.fetch_latest_release() is None
