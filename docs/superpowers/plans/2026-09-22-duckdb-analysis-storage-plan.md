# Stockage des analyses RULA dans DuckDB — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrer la persistance des résultats d'analyse RULA (métadonnées, scores par frame,
vidéo annotée, landmarks 3D) du système de fichiers `outputs/` vers DuckDB, avec un endpoint de
lecture pour l'historique, sans casser la CLI locale (Phase 1) qui continue d'écrire des fichiers.

**Architecture:** `pipeline.analyze_video()` devient pur (retourne bytes/dicts en mémoire, plus
aucune écriture disque durable). Un nouveau module `tms_vision/storage.py` encapsule tout l'accès
DuckDB (2 tables : `analyses` pour les métadonnées/blobs, `analysis_frames` pour les scores par
frame interrogeables). `api.py` appelle `analyze_video()` puis `storage.save_analysis()` et expose
de nouvelles routes `/analyses/...` en remplacement de `/outputs/{filename}`. `cli.py` récupère le
même résultat en mémoire et écrit lui-même les fichiers dans `--output-dir`, comme avant.

**Tech Stack:** Python 3.11, FastAPI, DuckDB (nouvelle dépendance), pytest, OpenCV (`cv2`), NumPy.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md`.
- Fichier DuckDB local : `data/tms_vision.duckdb` (créé au premier accès, ajouté à `.gitignore`).
- `pipeline.analyze_video()` ne prend plus de paramètre `output_dir` et n'écrit plus aucun fichier
  durable (seul un fichier temporaire supprimé avant le retour de la fonction, requis par
  `cv2.VideoWriter`).
- Les colonnes de `analysis_frames` reprennent exactement les noms de `CSV_FIELDS`
  (`src/tms_vision/export.py`) pour les champs communs, plus 4 colonnes
  `{neck,trunk,upper_arm,lower_arm}_segment_action_level`.
- `GET /outputs/{filename}` est supprimé ; remplacé par `/analyses/{id}/video`,
  `/analyses/{id}/pose3d`, `/analyses/{id}/frames.csv`, `/analyses`, `/analyses/{id}`.
- La CLI (`cli.py`) garde son comportement observable actuel : mêmes messages affichés, mêmes
  fichiers écrits dans `--output-dir`.

---

### Task 1: `storage.py` — connexion DuckDB et schéma

**Files:**
- Create: `src/tms_vision/storage.py`
- Test: `tests/test_storage.py`
- Modify: `requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `storage.DB_PATH: Path` (module-level, monkeypatchable comme `api.OUTPUT_DIR`),
  `storage._connect() -> duckdb.DuckDBPyConnection` (privé, ouvre une connexion sur `DB_PATH`,
  crée les tables si absentes, appelé par toutes les fonctions publiques du module).

- [ ] **Step 1: Ajouter la dépendance DuckDB**

Ajouter une ligne à `requirements.txt` (après `httpx>=0.27`) :

```
duckdb>=1.0
```

Installer dans l'environnement du projet :

```bash
pip install "duckdb>=1.0"
```

- [ ] **Step 2: Ajouter `data/` au `.gitignore`**

Ajouter une ligne à `.gitignore` (le fichier existe déjà, avec `outputs/` notamment) :

```
data/
```

- [ ] **Step 3: Écrire le test qui échoue**

Créer `tests/test_storage.py` :

```python
from tms_vision import storage


def test_connect_creates_both_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    conn = storage._connect()
    try:
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"analyses", "analysis_frames"} <= table_names


def test_connect_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    conn1 = storage._connect()
    conn1.close()
    conn2 = storage._connect()
    conn2.close()
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'tms_vision.storage'` (ou
`AttributeError` si le module existe déjà partiellement).

- [ ] **Step 5: Créer `storage.py` avec la connexion et le schéma**

```python
"""Persistance des résultats d'analyse RULA en DuckDB (voir
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md). Chaque
fonction publique ouvre puis referme sa propre connexion -- suffisant à
l'échelle actuelle du projet (un seul process uvicorn, pas de charge
concurrente à optimiser)."""
from pathlib import Path

import duckdb

DB_PATH = Path("data/tms_vision.duckdb")

CREATE_ANALYSES_TABLE = """
CREATE TABLE IF NOT EXISTS analyses (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    side VARCHAR NOT NULL,
    load_kg DOUBLE NOT NULL,
    wrist_twist VARCHAR NOT NULL,
    worker_label VARCHAR,
    poste_label VARCHAR,
    frame_count INTEGER NOT NULL,
    detected_frame_count INTEGER NOT NULL,
    max_score INTEGER NOT NULL,
    average_score DOUBLE NOT NULL,
    time_by_action_level VARCHAR NOT NULL,
    video_bytes BLOB NOT NULL,
    pose3d_json VARCHAR NOT NULL
)
"""

CREATE_ANALYSIS_FRAMES_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_frames (
    analysis_id VARCHAR NOT NULL REFERENCES analyses(id),
    frame_index INTEGER NOT NULL,
    timestamp_seconds DOUBLE NOT NULL,
    detected BOOLEAN NOT NULL,
    neck_flexion_deg DOUBLE,
    trunk_flexion_deg DOUBLE,
    upper_arm_flexion_deg DOUBLE,
    lower_arm_angle_deg DOUBLE,
    wrist_flexion_deg DOUBLE,
    upper_arm INTEGER,
    lower_arm INTEGER,
    wrist INTEGER,
    wrist_twist INTEGER,
    posture_score_a INTEGER,
    neck INTEGER,
    trunk INTEGER,
    legs INTEGER,
    posture_score_b INTEGER,
    muscle_use_score INTEGER,
    force_load_score INTEGER,
    final_score INTEGER,
    action_level VARCHAR,
    neck_segment_action_level VARCHAR,
    trunk_segment_action_level VARCHAR,
    upper_arm_segment_action_level VARCHAR,
    lower_arm_segment_action_level VARCHAR,
    PRIMARY KEY (analysis_id, frame_index)
)
"""


def _connect() -> "duckdb.DuckDBPyConnection":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(CREATE_ANALYSES_TABLE)
    conn.execute(CREATE_ANALYSIS_FRAMES_TABLE)
    return conn
```

- [ ] **Step 6: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore src/tms_vision/storage.py tests/test_storage.py
git commit -m "feat: connexion et schéma DuckDB pour le stockage des analyses"
```

---

### Task 2: `storage.py` — `save_analysis` / `get_analysis`

**Files:**
- Modify: `src/tms_vision/storage.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Consumes: `storage._connect()` (Task 1).
- Produces: `storage.save_analysis(*, analysis_id, created_at, side, load_kg, wrist_twist,
  worker_label, poste_label, summary, video_bytes, pose3d_json, frame_rows) -> None`,
  `storage.get_analysis(analysis_id: str) -> dict | None`. `frame_rows` est une liste de dicts,
  une entrée par frame, avec au moins toutes les clés de `CSV_FIELDS`
  (`src/tms_vision/export.py`) plus `neck_segment_action_level`, `trunk_segment_action_level`,
  `upper_arm_segment_action_level`, `lower_arm_segment_action_level`. `summary` a la forme du
  JSON produit aujourd'hui par `ResultsExporter._summary()` (`frame_count`,
  `detected_frame_count`, `max_score`, `average_score`, `time_by_action_level`).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `tests/test_storage.py` :

```python
from datetime import datetime, timezone

from tms_vision.export import CSV_FIELDS


def _frame_row(**overrides):
    row = {field: None for field in CSV_FIELDS}
    row.update(
        frame_index=0, timestamp_seconds=0.0, detected=True,
        neck_flexion_deg=5.0, trunk_flexion_deg=1.0, upper_arm_flexion_deg=10.0,
        lower_arm_angle_deg=90.0, wrist_flexion_deg=0.5,
        upper_arm=1, lower_arm=1, wrist=1, wrist_twist=1, posture_score_a=1,
        neck=1, trunk=1, legs=1, posture_score_b=1,
        muscle_use_score=0, force_load_score=0, final_score=1, action_level="acceptable",
    )
    row.update(overrides)
    row["neck_segment_action_level"] = "acceptable"
    row["trunk_segment_action_level"] = "investigation_recommandee"
    row["upper_arm_segment_action_level"] = "acceptable"
    row["lower_arm_segment_action_level"] = "acceptable"
    return row


def test_save_analysis_then_get_analysis_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    summary = {
        "frame_count": 2, "detected_frame_count": 2, "max_score": 1,
        "average_score": 1.0, "time_by_action_level": {"acceptable": 2.0},
    }
    storage.save_analysis(
        analysis_id="20260922-000000-abc123",
        created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        side="right", load_kg=2.5, wrist_twist="normal",
        worker_label="Marie D.", poste_label="Poste emballage",
        summary=summary, video_bytes=b"fake-mp4-bytes",
        pose3d_json='[{"frame_index": 0}]',
        frame_rows=[_frame_row(frame_index=0), _frame_row(frame_index=1, timestamp_seconds=1.0)],
    )

    analysis = storage.get_analysis("20260922-000000-abc123")

    assert analysis is not None
    assert analysis["id"] == "20260922-000000-abc123"
    assert analysis["side"] == "right"
    assert analysis["load_kg"] == 2.5
    assert analysis["wrist_twist"] == "normal"
    assert analysis["worker_label"] == "Marie D."
    assert analysis["poste_label"] == "Poste emballage"
    assert analysis["frame_count"] == 2
    assert analysis["detected_frame_count"] == 2
    assert analysis["max_score"] == 1
    assert analysis["average_score"] == 1.0
    assert analysis["time_by_action_level"] == {"acceptable": 2.0}


def test_get_analysis_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    assert storage.get_analysis("does-not-exist") is None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL avec `AttributeError: module 'tms_vision.storage' has no attribute 'save_analysis'`

- [ ] **Step 3: Implémenter `save_analysis` et `get_analysis`**

Ajouter à `src/tms_vision/storage.py` (après `_connect`) :

```python
import json
from datetime import datetime

from tms_vision.export import CSV_FIELDS

SEGMENT_COLUMNS = [
    "neck_segment_action_level",
    "trunk_segment_action_level",
    "upper_arm_segment_action_level",
    "lower_arm_segment_action_level",
]
FRAME_VALUE_COLUMNS = CSV_FIELDS + SEGMENT_COLUMNS

_ANALYSIS_COLUMNS = [
    "id", "created_at", "side", "load_kg", "wrist_twist", "worker_label", "poste_label",
    "frame_count", "detected_frame_count", "max_score", "average_score", "time_by_action_level",
]


def save_analysis(
    *,
    analysis_id: str,
    created_at: datetime,
    side: str,
    load_kg: float,
    wrist_twist: str,
    worker_label: str | None,
    poste_label: str | None,
    summary: dict,
    video_bytes: bytes,
    pose3d_json: str,
    frame_rows: list[dict],
) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO analyses (
                id, created_at, side, load_kg, wrist_twist, worker_label, poste_label,
                frame_count, detected_frame_count, max_score, average_score,
                time_by_action_level, video_bytes, pose3d_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                analysis_id, created_at, side, load_kg, wrist_twist, worker_label, poste_label,
                summary["frame_count"], summary["detected_frame_count"], summary["max_score"],
                summary["average_score"],
                json.dumps(summary["time_by_action_level"], ensure_ascii=False),
                video_bytes, pose3d_json,
            ],
        )
        insert_frame_sql = (
            "INSERT INTO analysis_frames (analysis_id, "
            + ", ".join(FRAME_VALUE_COLUMNS)
            + ") VALUES ("
            + ", ".join(["?"] * (len(FRAME_VALUE_COLUMNS) + 1))
            + ")"
        )
        for row in frame_rows:
            conn.execute(
                insert_frame_sql,
                [analysis_id] + [row.get(column) for column in FRAME_VALUE_COLUMNS],
            )
    finally:
        conn.close()


def get_analysis(analysis_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {', '.join(_ANALYSIS_COLUMNS)} FROM analyses WHERE id = ?",
            [analysis_id],
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    record = dict(zip(_ANALYSIS_COLUMNS, row))
    record["time_by_action_level"] = json.loads(record["time_by_action_level"])
    record["created_at"] = record["created_at"].isoformat()
    return record
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/storage.py tests/test_storage.py
git commit -m "feat: save_analysis/get_analysis dans storage.py"
```

---

### Task 3: `storage.py` — `list_analyses` avec filtres

**Files:**
- Modify: `src/tms_vision/storage.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Consumes: `storage.save_analysis`, `storage._connect` (Tasks 1-2).
- Produces: `storage.list_analyses(worker_label=None, poste_label=None, since=None, until=None)
  -> list[dict]`, triée par `created_at` décroissant, même forme de dict que `get_analysis`.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `tests/test_storage.py` :

```python
def _save(analysis_id, created_at, worker_label=None, poste_label=None):
    summary = {
        "frame_count": 1, "detected_frame_count": 1, "max_score": 1,
        "average_score": 1.0, "time_by_action_level": {"acceptable": 1.0},
    }
    storage.save_analysis(
        analysis_id=analysis_id, created_at=created_at, side="right", load_kg=0.0,
        wrist_twist="normal", worker_label=worker_label, poste_label=poste_label,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=[],
    )


def test_list_analyses_orders_by_created_at_desc(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    _save("a", datetime(2026, 9, 20, tzinfo=timezone.utc))
    _save("b", datetime(2026, 9, 22, tzinfo=timezone.utc))
    _save("c", datetime(2026, 9, 21, tzinfo=timezone.utc))

    results = storage.list_analyses()

    assert [r["id"] for r in results] == ["b", "c", "a"]


def test_list_analyses_filters_by_worker_and_poste_label(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    _save("a", datetime(2026, 9, 20, tzinfo=timezone.utc), worker_label="Marie D.", poste_label="Emballage")
    _save("b", datetime(2026, 9, 21, tzinfo=timezone.utc), worker_label="Paul L.", poste_label="Emballage")

    assert [r["id"] for r in storage.list_analyses(worker_label="Marie D.")] == ["a"]
    assert [r["id"] for r in storage.list_analyses(poste_label="Emballage")] == ["b", "a"]


def test_list_analyses_filters_by_date_range(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    _save("a", datetime(2026, 9, 20, tzinfo=timezone.utc))
    _save("b", datetime(2026, 9, 22, tzinfo=timezone.utc))

    results = storage.list_analyses(
        since=datetime(2026, 9, 21, tzinfo=timezone.utc),
        until=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )

    assert [r["id"] for r in results] == ["b"]
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL avec `AttributeError: module 'tms_vision.storage' has no attribute 'list_analyses'`

- [ ] **Step 3: Implémenter `list_analyses`**

Ajouter à `src/tms_vision/storage.py` (après `get_analysis`) :

```python
def list_analyses(
    worker_label: str | None = None,
    poste_label: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    clauses = []
    params: list = []
    if worker_label is not None:
        clauses.append("worker_label = ?")
        params.append(worker_label)
    if poste_label is not None:
        clauses.append("poste_label = ?")
        params.append(poste_label)
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("created_at <= ?")
        params.append(until)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT {', '.join(_ANALYSIS_COLUMNS)} FROM analyses {where} "
            "ORDER BY created_at DESC",
            params,
        ).fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        record = dict(zip(_ANALYSIS_COLUMNS, row))
        record["time_by_action_level"] = json.loads(record["time_by_action_level"])
        record["created_at"] = record["created_at"].isoformat()
        results.append(record)
    return results
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/storage.py tests/test_storage.py
git commit -m "feat: list_analyses avec filtres worker/poste/date dans storage.py"
```

---

### Task 4: `storage.py` — lecture des blobs et du CSV à la volée

**Files:**
- Modify: `src/tms_vision/storage.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Consumes: `storage.save_analysis`, `storage._connect` (Tasks 1-2).
- Produces: `storage.get_video_bytes(analysis_id: str) -> bytes | None`,
  `storage.get_pose3d_json(analysis_id: str) -> str | None`,
  `storage.frames_csv_text(analysis_id: str) -> str | None` (texte CSV avec en-tête `CSV_FIELDS`,
  `None` si `analysis_id` inconnu).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `tests/test_storage.py` :

```python
def test_get_video_bytes_and_pose3d_json_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    summary = {
        "frame_count": 1, "detected_frame_count": 1, "max_score": 1,
        "average_score": 1.0, "time_by_action_level": {"acceptable": 1.0},
    }
    storage.save_analysis(
        analysis_id="vid-1", created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"\x00\x01mp4-bytes", pose3d_json='[{"frame_index": 0}]',
        frame_rows=[],
    )

    assert storage.get_video_bytes("vid-1") == b"\x00\x01mp4-bytes"
    assert storage.get_pose3d_json("vid-1") == '[{"frame_index": 0}]'
    assert storage.get_video_bytes("unknown") is None
    assert storage.get_pose3d_json("unknown") is None


def test_frames_csv_text_generates_header_and_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    summary = {
        "frame_count": 1, "detected_frame_count": 1, "max_score": 1,
        "average_score": 1.0, "time_by_action_level": {"acceptable": 1.0},
    }
    storage.save_analysis(
        analysis_id="csv-1", created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]",
        frame_rows=[_frame_row(frame_index=0)],
    )

    csv_text = storage.frames_csv_text("csv-1")

    assert csv_text is not None
    lines = csv_text.strip().splitlines()
    assert lines[0] == ",".join(CSV_FIELDS)
    assert "acceptable" in lines[1]
    assert storage.frames_csv_text("unknown") is None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL avec `AttributeError: module 'tms_vision.storage' has no attribute 'get_video_bytes'`

- [ ] **Step 3: Implémenter les fonctions de lecture**

Ajouter à `src/tms_vision/storage.py` (après `list_analyses`), avec `import csv` et `import io`
ajoutés en haut du fichier :

```python
def get_video_bytes(analysis_id: str) -> bytes | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT video_bytes FROM analyses WHERE id = ?", [analysis_id]
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row is not None else None


def get_pose3d_json(analysis_id: str) -> str | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT pose3d_json FROM analyses WHERE id = ?", [analysis_id]
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row is not None else None


def frames_csv_text(analysis_id: str) -> str | None:
    conn = _connect()
    try:
        exists = conn.execute(
            "SELECT 1 FROM analyses WHERE id = ?", [analysis_id]
        ).fetchone()
        if exists is None:
            return None
        rows = conn.execute(
            f"SELECT {', '.join(CSV_FIELDS)} FROM analysis_frames "
            "WHERE analysis_id = ? ORDER BY frame_index",
            [analysis_id],
        ).fetchall()
    finally:
        conn.close()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(zip(CSV_FIELDS, row)))
    return buffer.getvalue()
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/storage.py tests/test_storage.py
git commit -m "feat: lecture vidéo/pose3D/CSV à la volée dans storage.py"
```

---

### Task 5: `export.py` — accumulateur pur + écriture CSV/JSON réutilisable

**Files:**
- Modify: `src/tms_vision/export.py`
- Modify: `tests/test_export.py`

**Interfaces:**
- Produces: `ResultsExporter()` (plus d'arguments de chemin), `ResultsExporter.add_frame(record)`
  (inchangé), `ResultsExporter.rows() -> list[dict]` (une entrée par frame, clés = `CSV_FIELDS`,
  valeurs `None` -- pas `""` -- pour les champs non applicables), `ResultsExporter.summary() ->
  dict` (remplace l'ancien `_summary()` privé). Nouvelles fonctions module :
  `write_frames_csv(rows: list[dict], path: str) -> None`,
  `write_summary_json(summary: dict, path: str) -> None`. `ResultsExporter.finalize()` et le
  constructeur à 2 arguments (`csv_path`, `summary_json_path`) sont supprimés.

- [ ] **Step 1: Réécrire le test qui échoue**

Remplacer entièrement `tests/test_export.py` :

```python
import csv
import json

from tms_vision.angles import JointAngles
from tms_vision.rula.scoring import RulaScore
from tms_vision.export import (
    FrameRecord,
    ResultsExporter,
    write_frames_csv,
    write_summary_json,
)


def _angles():
    return JointAngles(
        neck_flexion_deg=5.0, neck_twisted=False, neck_side_bending=False,
        trunk_flexion_deg=1.0, trunk_twisted=False, trunk_side_bending=False,
        upper_arm_flexion_deg=10.0, upper_arm_abducted=False, upper_arm_shoulder_raised=False,
        lower_arm_angle_deg=90.0, lower_arm_across_midline=False,
        wrist_flexion_deg=0.5, wrist_bent_from_midline=False, arm_supported=False,
    )


def _score(final_score, level):
    return RulaScore(
        upper_arm=1, lower_arm=1, wrist=1, wrist_twist=1, posture_score_a=1,
        neck=1, trunk=1, legs=1, posture_score_b=1, muscle_use_score=0,
        force_load_score=0, wrist_arm_score=1, neck_trunk_leg_score=1,
        final_score=final_score, action_level=level,
    )


def test_rows_returns_one_dict_per_frame_with_none_for_missing_values():
    exporter = ResultsExporter()
    exporter.add_frame(FrameRecord(0, 0.0, True, _angles(), _score(1, "acceptable")))
    exporter.add_frame(FrameRecord(1, 1.0, True, _angles(), _score(7, "changement_immediat")))
    exporter.add_frame(FrameRecord(2, 2.0, False, None, None))

    rows = exporter.rows()

    assert len(rows) == 3
    assert rows[0]["detected"] is True
    assert rows[0]["final_score"] == 1
    assert rows[0]["posture_score_a"] == 1
    assert rows[0]["posture_score_b"] == 1
    assert rows[0]["wrist_twist"] == 1
    assert rows[2]["detected"] is False
    assert rows[2]["final_score"] is None
    assert rows[2]["posture_score_a"] is None


def test_summary_aggregates_scores_and_time_by_action_level():
    exporter = ResultsExporter()
    exporter.add_frame(FrameRecord(0, 0.0, True, _angles(), _score(1, "acceptable")))
    exporter.add_frame(FrameRecord(1, 1.0, True, _angles(), _score(7, "changement_immediat")))
    exporter.add_frame(FrameRecord(2, 2.0, False, None, None))

    summary = exporter.summary()

    assert summary["frame_count"] == 3
    assert summary["detected_frame_count"] == 2
    assert summary["max_score"] == 7
    assert summary["average_score"] == 4.0
    assert summary["time_by_action_level"]["acceptable"] == 1.0
    assert summary["time_by_action_level"]["changement_immediat"] == 1.0


def test_summary_with_no_detected_frames_gives_zeroed_summary():
    exporter = ResultsExporter()
    exporter.add_frame(FrameRecord(0, 0.0, False, None, None))

    summary = exporter.summary()

    assert summary["max_score"] == 0
    assert summary["average_score"] == 0
    assert summary["time_by_action_level"] == {}


def test_write_frames_csv_writes_one_row_per_frame_and_ignores_extra_keys(tmp_path):
    csv_path = tmp_path / "frames.csv"
    exporter = ResultsExporter()
    exporter.add_frame(FrameRecord(0, 0.0, True, _angles(), _score(1, "acceptable")))
    exporter.add_frame(FrameRecord(1, 1.0, False, None, None))
    rows = exporter.rows()
    for row in rows:
        row["neck_segment_action_level"] = "acceptable"  # clé étrangère à CSV_FIELDS

    write_frames_csv(rows, str(csv_path))

    with open(csv_path, newline="") as f:
        read_rows = list(csv.DictReader(f))
    assert len(read_rows) == 2
    assert read_rows[0]["detected"] == "True"
    assert read_rows[0]["final_score"] == "1"
    assert read_rows[1]["detected"] == "False"
    assert read_rows[1]["final_score"] == ""


def test_write_summary_json_writes_the_summary_dict(tmp_path):
    summary_path = tmp_path / "summary.json"
    write_summary_json({"frame_count": 1, "max_score": 3}, str(summary_path))

    with open(summary_path) as f:
        assert json.load(f) == {"frame_count": 1, "max_score": 3}
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_export.py -v`
Expected: FAIL (`TypeError: ResultsExporter() takes no arguments` ou `AttributeError` selon la
fonction manquante en premier)

- [ ] **Step 3: Réécrire `export.py`**

Remplacer entièrement `src/tms_vision/export.py` :

```python
"""Accumulation des résultats par frame, et deux fonctions d'écriture disque
réutilisables (CSV/JSON) -- utilisées par la CLI (tms_vision.cli) pour
reproduire le comportement historique d'écriture sur le système de fichiers.
L'API web (tms_vision.api / tms_vision.storage) consomme rows()/summary()
directement en mémoire, sans jamais écrire ces fichiers."""
import csv
import json
from dataclasses import dataclass

from tms_vision.angles import JointAngles
from tms_vision.rula.scoring import RulaScore

CSV_FIELDS = [
    "frame_index", "timestamp_seconds", "detected",
    "neck_flexion_deg", "trunk_flexion_deg", "upper_arm_flexion_deg",
    "lower_arm_angle_deg", "wrist_flexion_deg",
    "upper_arm", "lower_arm", "wrist", "wrist_twist", "posture_score_a",
    "neck", "trunk", "legs", "posture_score_b",
    "muscle_use_score", "force_load_score", "final_score", "action_level",
]


@dataclass
class FrameRecord:
    frame_index: int
    timestamp_seconds: float
    detected: bool
    angles: JointAngles | None
    score: RulaScore | None


class ResultsExporter:
    def __init__(self) -> None:
        self._records: list[FrameRecord] = []

    def add_frame(self, record: FrameRecord) -> None:
        self._records.append(record)

    def _row_for(self, record: FrameRecord) -> dict:
        row = {field: None for field in CSV_FIELDS}
        row["frame_index"] = record.frame_index
        row["timestamp_seconds"] = record.timestamp_seconds
        row["detected"] = record.detected
        if record.angles is not None:
            row["neck_flexion_deg"] = record.angles.neck_flexion_deg
            row["trunk_flexion_deg"] = record.angles.trunk_flexion_deg
            row["upper_arm_flexion_deg"] = record.angles.upper_arm_flexion_deg
            row["lower_arm_angle_deg"] = record.angles.lower_arm_angle_deg
            row["wrist_flexion_deg"] = record.angles.wrist_flexion_deg
        if record.score is not None:
            row["upper_arm"] = record.score.upper_arm
            row["lower_arm"] = record.score.lower_arm
            row["wrist"] = record.score.wrist
            row["wrist_twist"] = record.score.wrist_twist
            row["posture_score_a"] = record.score.posture_score_a
            row["neck"] = record.score.neck
            row["trunk"] = record.score.trunk
            row["legs"] = record.score.legs
            row["posture_score_b"] = record.score.posture_score_b
            row["muscle_use_score"] = record.score.muscle_use_score
            row["force_load_score"] = record.score.force_load_score
            row["final_score"] = record.score.final_score
            row["action_level"] = record.score.action_level
        return row

    def rows(self) -> list[dict]:
        return [self._row_for(record) for record in self._records]

    def summary(self) -> dict:
        detected = [r for r in self._records if r.detected and r.score is not None]
        if not detected:
            return {
                "frame_count": len(self._records),
                "detected_frame_count": 0,
                "max_score": 0,
                "average_score": 0,
                "time_by_action_level": {},
            }

        scores = [r.score.final_score for r in detected]
        time_by_level: dict[str, float] = {}
        for record in detected:
            next_timestamp = None
            for r in self._records:
                if r.frame_index > record.frame_index:
                    next_timestamp = r.timestamp_seconds
                    break

            if next_timestamp is None:
                duration = 1.0 if len(detected) == 1 else 0.0
            else:
                duration = max(next_timestamp - record.timestamp_seconds, 0.0) or (
                    1.0 if len(detected) == 1 else 0.0
                )

            time_by_level[record.score.action_level] = (
                time_by_level.get(record.score.action_level, 0.0) + duration
            )

        return {
            "frame_count": len(self._records),
            "detected_frame_count": len(detected),
            "max_score": max(scores),
            "average_score": sum(scores) / len(scores),
            "time_by_action_level": time_by_level,
        }


def write_frames_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_summary_json(summary: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_export.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/export.py tests/test_export.py
git commit -m "refactor: export.py devient un accumulateur pur, écriture CSV/JSON réutilisable"
```

---

### Task 6: `pose3d_export.py` — extraire `build_pose3d_payload`

**Files:**
- Modify: `src/tms_vision/pose3d_export.py`
- Modify: `tests/test_pose3d_export.py`

**Interfaces:**
- Produces: `pose3d_export.build_pose3d_payload(records: list[Pose3DFrameRecord]) -> list[dict]`
  (fonction pure, extraite de `write_pose3d_json`, retourne exactement la même structure que
  celle actuellement écrite en JSON). `write_pose3d_json(path, records)` garde exactement le même
  comportement observable (inchangé pour ses appelants existants), mais délègue maintenant à
  `build_pose3d_payload`.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `tests/test_pose3d_export.py` :

```python
from tms_vision.pose3d_export import build_pose3d_payload


def test_build_pose3d_payload_returns_one_dict_per_frame():
    records = [
        Pose3DFrameRecord(
            0, 0.0, True, {"NOSE": Landmark(0.1, 0.2, 0.3, 0.9)}, "acceptable",
            {"neck": "acceptable", "trunk": "investigation_recommandee",
             "upper_arm": "acceptable", "lower_arm": "acceptable"},
        ),
        Pose3DFrameRecord(1, 1.0, False, None, None, None),
    ]

    payload = build_pose3d_payload(records)

    assert len(payload) == 2
    assert payload[0]["frame_index"] == 0
    assert payload[0]["landmarks"]["NOSE"] == [0.1, 0.2, 0.3]
    assert payload[0]["segment_action_levels"]["trunk"] == "investigation_recommandee"
    assert payload[1]["landmarks"] is None
    assert payload[1]["action_level"] is None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_pose3d_export.py -v`
Expected: FAIL avec `ImportError: cannot import name 'build_pose3d_payload'`

- [ ] **Step 3: Extraire `build_pose3d_payload`**

Remplacer dans `src/tms_vision/pose3d_export.py` la fonction `write_pose3d_json` (lignes 57-77)
par :

```python
def build_pose3d_payload(records: list[Pose3DFrameRecord]) -> list[dict]:
    payload = []
    for record in records:
        landmarks = None
        if record.landmarks is not None:
            landmarks = {
                name: [landmark.x, landmark.y, landmark.z]
                for name, landmark in record.landmarks.items()
            }
        payload.append(
            {
                "frame_index": record.frame_index,
                "timestamp_seconds": record.timestamp_seconds,
                "detected": record.detected,
                "landmarks": landmarks,
                "action_level": record.action_level,
                "segment_action_levels": record.segment_action_levels,
            }
        )
    return payload


def write_pose3d_json(path: str, records: list[Pose3DFrameRecord]) -> None:
    with open(path, "w") as f:
        json.dump(build_pose3d_payload(records), f, ensure_ascii=False)
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_pose3d_export.py -v`
Expected: PASS (7 tests, dont les 6 existants inchangés)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/pose3d_export.py tests/test_pose3d_export.py
git commit -m "refactor: extrait build_pose3d_payload, fonction pure réutilisable"
```

---

### Task 7: `pipeline.py` — `analyze_video()` devient pur

**Files:**
- Modify: `src/tms_vision/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `ResultsExporter()`, `.add_frame()`, `.rows()`, `.summary()` (Task 5),
  `Pose3DFrameRecord`, `smooth_world_landmarks` (inchangés, `pose3d_export.py`).
- Produces: `pipeline.generate_run_id() -> str` (extrait, réutilisé par `cli.py` et `api.py`),
  `pipeline.analyze_video(source: str, side: str, load_kg: float, wrist_twist: str) ->
  AnalysisResult` (signature sans `output_dir`), `AnalysisResult(empty: bool, video_bytes: bytes |
  None = None, frame_rows: list[dict] | None = None, summary: dict | None = None,
  pose3d_records: list[Pose3DFrameRecord] | None = None)`. `frame_rows` contient déjà les 4 clés
  `{neck,trunk,upper_arm,lower_arm}_segment_action_level` en plus de `CSV_FIELDS` (fusionnées
  depuis `pose3d_records` à l'intérieur de `analyze_video`).

- [ ] **Step 1: Réécrire le test qui échoue**

Remplacer entièrement `tests/test_pipeline.py` :

```python
import cv2
import numpy as np
import pytest

from tms_vision.pipeline import analyze_video, generate_run_id, AnalysisResult, _RunningMean
from tms_vision.capture import Frame
from tms_vision.pose_estimation import Landmark, PoseEstimator, PoseResult
from tms_vision.pose3d_export import build_pose3d_payload


def test_generate_run_id_has_timestamp_and_hex_suffix():
    run_id = generate_run_id()
    date_part, time_part, hex_part = run_id.split("-")
    assert len(date_part) == 8
    assert len(time_part) == 6
    assert len(hex_part) == 6
    int(hex_part, 16)  # ne lève pas si c'est bien de l'hexadécimal


def test_running_mean_starts_at_none():
    mean = _RunningMean()
    assert mean.value is None


def test_running_mean_computes_average_incrementally():
    mean = _RunningMean()
    mean.update(2.0)
    assert mean.value == 2.0
    mean.update(4.0)
    assert mean.value == 3.0
    mean.update(9.0)
    assert mean.value == 5.0


class _EmptyFrameSource:
    def __init__(self, *_args, **_kwargs):
        pass

    def fps(self):
        return 30.0

    def __iter__(self):
        return iter([])

    def release(self):
        pass


def test_analyze_video_with_zero_frames_returns_empty_result(monkeypatch, capsys):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _EmptyFrameSource)

    result = analyze_video(source="webcam", side="right", load_kg=0.0, wrist_twist="normal")

    assert result == AnalysisResult(empty=True)
    captured = capsys.readouterr()
    assert "Aucune frame capturée" in captured.err


def _write_synthetic_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()


def test_analyze_video_end_to_end_on_a_blank_synthetic_video(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    result = analyze_video(source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal")

    assert result.empty is False
    assert isinstance(result.video_bytes, bytes)
    assert len(result.video_bytes) > 0
    assert len(result.frame_rows) == 3
    assert result.summary["frame_count"] == 3
    assert len(result.pose3d_records) == 3


def test_analyze_video_writes_browser_playable_h264_not_mp4v(tmp_path):
    """Régression pour 9d6a9da : le fourcc d'écriture doit être "avc1" (H.264,
    lisible par les navigateurs), pas "mp4v". Écrit result.video_bytes dans un
    fichier temporaire pour le relire via cv2.VideoCapture, puisque
    analyze_video() ne renvoie plus de chemin de fichier."""
    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    result = analyze_video(source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal")

    assert result.empty is False
    readback_path = tmp_path / "readback.mp4"
    readback_path.write_bytes(result.video_bytes)
    cap = cv2.VideoCapture(str(readback_path))
    try:
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = fourcc_int.to_bytes(4, byteorder="little").decode("ascii", errors="replace")
    finally:
        cap.release()

    assert fourcc == "h264", (
        f"Codec vidéo attendu 'h264' (lisible en navigateur), obtenu {fourcc!r} -- "
        "vérifier que analyze_video encode toujours avec "
        "cv2.VideoWriter_fourcc(*'avc1') et non 'mp4v'"
    )


class _InterruptingFrameSource:
    def __init__(self, *_args, **_kwargs):
        self.released = False

    def fps(self):
        return 30.0

    def __iter__(self):
        for i in range(2):
            yield Frame(
                index=i, timestamp_seconds=i / 30.0,
                image=np.zeros((64, 64, 3), dtype=np.uint8),
            )
        raise KeyboardInterrupt

    def release(self):
        self.released = True


def test_analyze_video_with_keyboard_interrupt_during_capture_still_returns_partial_result(
    monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _InterruptingFrameSource)

    result = analyze_video(source="webcam", side="right", load_kg=0.0, wrist_twist="normal")

    captured = capsys.readouterr()
    assert "Capture interrompue" in captured.out
    assert result.empty is False
    assert len(result.frame_rows) == 2


def test_analyze_video_produces_pose3d_records(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    result = analyze_video(source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal")

    payload = build_pose3d_payload(result.pose3d_records)
    assert len(payload) == 3
    for entry in payload:
        assert entry["detected"] is False
        assert entry["landmarks"] is None
        assert entry["action_level"] is None
        assert entry["segment_action_levels"] is None


def _lm(x, y, z=0.0, visibility=1.0):
    return Landmark(x=x, y=y, z=z, visibility=visibility)


def test_analyze_video_merges_segment_action_levels_into_frame_rows(tmp_path, monkeypatch):
    """Les 4 colonnes {neck,trunk,upper_arm,lower_arm}_segment_action_level de
    frame_rows doivent correspondre exactement aux segment_action_levels du
    pose3d_record de la même frame (fusion faite par analyze_video, voir
    architecture)."""

    def _neutral_landmarks_2d_right_side():
        return {
            "LEFT_SHOULDER": _lm(0.50, 0.30), "RIGHT_SHOULDER": _lm(0.50, 0.30),
            "LEFT_HIP": _lm(0.50, 0.55), "RIGHT_HIP": _lm(0.50, 0.55),
            "NOSE": _lm(0.52, 0.20), "RIGHT_EAR": _lm(0.51, 0.22),
            "RIGHT_ELBOW": _lm(0.50, 0.45), "RIGHT_WRIST": _lm(0.50, 0.60),
            "RIGHT_INDEX": _lm(0.50, 0.63),
        }

    def _world_landmarks():
        return {
            "LEFT_SHOULDER": _lm(-0.1, -0.3, 0.0), "RIGHT_SHOULDER": _lm(0.1, -0.3, 0.0),
            "LEFT_HIP": _lm(-0.1, 0.0, 0.0), "RIGHT_HIP": _lm(0.1, 0.0, 0.0),
            "NOSE": _lm(0.0, -0.5, 0.05), "RIGHT_EAR": _lm(0.05, -0.48, 0.02),
            "RIGHT_ELBOW": _lm(0.15, -0.1, 0.0), "RIGHT_WRIST": _lm(0.15, 0.15, 0.0),
        }

    fake_result = PoseResult(
        landmarks=_neutral_landmarks_2d_right_side(), world_landmarks=_world_landmarks(),
    )
    monkeypatch.setattr(PoseEstimator, "process", lambda self, image_bgr: fake_result)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    result = analyze_video(source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal")

    pose3d_payload = build_pose3d_payload(result.pose3d_records)
    for row, pose3d_entry in zip(result.frame_rows, pose3d_payload):
        segments = pose3d_entry["segment_action_levels"]
        assert row["neck_segment_action_level"] == segments["neck"]
        assert row["trunk_segment_action_level"] == segments["trunk"]
        assert row["upper_arm_segment_action_level"] == segments["upper_arm"]
        assert row["lower_arm_segment_action_level"] == segments["lower_arm"]


def test_analyze_video_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        analyze_video(source="does-not-exist.mp4", side="right", load_kg=0.0, wrist_twist="normal")
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL (`TypeError: analyze_video() missing 1 required positional argument: 'output_dir'`
ou `ImportError: cannot import name 'generate_run_id'`)

- [ ] **Step 3: Réécrire `pipeline.py`**

Remplacer entièrement `src/tms_vision/pipeline.py` :

```python
"""Pipeline Phase 1 réutilisable : capture -> pose -> angles -> score RULA ->
overlay vidéo, entièrement en mémoire (voir
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md). Le seul
fichier écrit sur disque est un fichier temporaire imposé par
cv2.VideoWriter (qui n'accepte pas d'écrire directement en mémoire) --
supprimé avant que la fonction ne retourne. Persister le résultat (fichiers
locaux pour la CLI, DuckDB pour l'API web) est la responsabilité de
l'appelant (tms_vision.cli, tms_vision.api / tms_vision.storage).
"""
import secrets
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from tms_vision.capture import FrameSource
from tms_vision.pose_estimation import PoseEstimator
from tms_vision.angles import compute_joint_angles
from tms_vision.rula.scoring import action_level, compute_rula_score, detect_muscle_use
from tms_vision.overlay import draw_overlay
from tms_vision.export import FrameRecord, ResultsExporter
from tms_vision.pose3d_export import Pose3DFrameRecord, build_pose3d_payload, smooth_world_landmarks

WRIST_TWIST_CODES = {"normal": 1, "extreme": 2}


def generate_run_id() -> str:
    """Identifiant unique horodaté, réutilisé à la fois comme préfixe de nom
    de fichier (CLI) et comme clé primaire d'analyse (DuckDB) -- deux espaces
    de noms indépendants qui partagent simplement ce même format."""
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


class _RunningMean:
    """Moyenne mobile incrémentale simple (compteur + somme cumulée), utilisée
    pour donner à compute_joint_angles() une référence stable de la hauteur
    "au repos" de l'épaule (shoulder_baseline_y) plutôt que la position de la
    seule frame courante."""

    def __init__(self) -> None:
        self._count = 0
        self._total = 0.0

    def update(self, value: float) -> None:
        self._count += 1
        self._total += value

    @property
    def value(self) -> float | None:
        if self._count == 0:
            return None
        return self._total / self._count


@dataclass
class AnalysisResult:
    empty: bool
    video_bytes: bytes | None = None
    frame_rows: list[dict] | None = None
    summary: dict | None = None
    pose3d_records: list[Pose3DFrameRecord] | None = None


def analyze_video(source: str, side: str, load_kg: float, wrist_twist: str) -> AnalysisResult:
    wrist_twist_code = WRIST_TWIST_CODES[wrist_twist]

    frame_source = FrameSource(source)
    estimator = PoseEstimator()

    frames = []
    try:
        for frame in frame_source:
            frames.append(frame)
    except KeyboardInterrupt:
        print("\nCapture interrompue par l'utilisateur, traitement des frames déjà capturées...")
    finally:
        frame_source.release()

    if not frames:
        print("Aucune frame capturée, rien à analyser.", file=sys.stderr)
        estimator.close()
        return AnalysisResult(empty=True)

    per_frame_angles = []
    posture_load_history: list[tuple[float, float]] = []
    shoulder_key = f"{side.upper()}_SHOULDER"
    shoulder_y_baseline = _RunningMean()

    for frame in frames:
        pose_result = estimator.process(frame.image)
        angles = None
        if pose_result.landmarks is not None:
            angles = compute_joint_angles(
                pose_result.landmarks, side=side, shoulder_baseline_y=shoulder_y_baseline.value
            )
            current_shoulder = pose_result.landmarks.get(shoulder_key)
            if current_shoulder is not None:
                shoulder_y_baseline.update(current_shoulder.y)
        per_frame_angles.append((frame, pose_result, angles))
        if angles is not None:
            posture_load = angles.trunk_flexion_deg + angles.upper_arm_flexion_deg
            posture_load_history.append((frame.timestamp_seconds, posture_load))

    estimator.close()

    muscle_use_score = 1 if detect_muscle_use(posture_load_history) else 0

    height, width = frames[0].image.shape[:2]
    exporter = ResultsExporter()

    raw_world_landmarks = [pose_result.world_landmarks for _, pose_result, _ in per_frame_angles]
    smoothed_world_landmarks = smooth_world_landmarks(raw_world_landmarks)
    pose3d_records: list[Pose3DFrameRecord] = []

    tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    video_tmp_path = Path(tmp_video.name)
    tmp_video.close()
    try:
        # "avc1" (H.264/AVC) est lisible par les navigateurs (Chromium/
        # Firefox), contrairement à "mp4v" -- voir commit 9d6a9da et
        # test_analyze_video_writes_browser_playable_h264_not_mp4v.
        writer = cv2.VideoWriter(
            str(video_tmp_path), cv2.VideoWriter_fourcc(*"avc1"),
            frame_source.fps() or 30.0, (width, height),
        )
        for (frame, pose_result, angles), world_landmarks in zip(per_frame_angles, smoothed_world_landmarks):
            score = None
            if angles is not None:
                score = compute_rula_score(
                    angles, wrist_twist=wrist_twist_code, load_kg=load_kg,
                    muscle_use_score=muscle_use_score,
                )
            segment_action_levels = None
            if score is not None:
                segment_action_levels = {
                    "neck": action_level(score.neck),
                    "trunk": action_level(score.trunk),
                    "upper_arm": action_level(score.upper_arm),
                    "lower_arm": action_level(score.lower_arm),
                }
            annotated = draw_overlay(frame.image, pose_result.landmarks, score)
            writer.write(annotated)
            exporter.add_frame(
                FrameRecord(
                    frame_index=frame.index,
                    timestamp_seconds=frame.timestamp_seconds,
                    detected=angles is not None,
                    angles=angles,
                    score=score,
                )
            )
            pose3d_records.append(
                Pose3DFrameRecord(
                    frame_index=frame.index,
                    timestamp_seconds=frame.timestamp_seconds,
                    detected=angles is not None,
                    landmarks=world_landmarks,
                    action_level=score.action_level if score is not None else None,
                    segment_action_levels=segment_action_levels,
                )
            )
        writer.release()
        video_bytes = video_tmp_path.read_bytes()
    finally:
        video_tmp_path.unlink(missing_ok=True)

    frame_rows = exporter.rows()
    pose3d_payload = build_pose3d_payload(pose3d_records)
    for row, pose3d_entry in zip(frame_rows, pose3d_payload):
        segments = pose3d_entry["segment_action_levels"] or {}
        row["neck_segment_action_level"] = segments.get("neck")
        row["trunk_segment_action_level"] = segments.get("trunk")
        row["upper_arm_segment_action_level"] = segments.get("upper_arm")
        row["lower_arm_segment_action_level"] = segments.get("lower_arm")

    return AnalysisResult(
        empty=False,
        video_bytes=video_bytes,
        frame_rows=frame_rows,
        summary=exporter.summary(),
        pose3d_records=pose3d_records,
    )
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/pipeline.py tests/test_pipeline.py
git commit -m "refactor: analyze_video() devient pur, plus d'écriture disque durable"
```

---

### Task 8: `cli.py` — écrit les fichiers depuis le résultat en mémoire

**Files:**
- Modify: `src/tms_vision/cli.py`
- Verify: `tests/test_cli.py` (ne devrait nécessiter aucune modification -- voir Step 3)

**Interfaces:**
- Consumes: `pipeline.analyze_video(source, side, load_kg, wrist_twist)`,
  `pipeline.generate_run_id()`, `export.write_frames_csv(rows, path)`,
  `export.write_summary_json(summary, path)`, `pose3d_export.write_pose3d_json(path, records)`
  (toutes de Tasks 5-7).

- [ ] **Step 1: Lancer la suite CLI existante pour confirmer l'état actuel (référence avant
  modification)**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL sur les tests qui appellent `run(args)` (car `analyze_video()` n'accepte plus
`output_dir`, cf Task 7) -- confirme que `cli.py` doit être adapté.

- [ ] **Step 2: Réécrire `cli.py`**

Remplacer entièrement `src/tms_vision/cli.py` :

```python
"""Point d'entrée CLI : parse les arguments, délègue le calcul à
tms_vision.pipeline.analyze_video() (pur, voir ce module), puis écrit
vidéo/CSV/JSON dans --output-dir -- seul endroit du projet qui écrit encore
ces résultats sur le système de fichiers (voir
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md : l'API
web persiste en DuckDB via tms_vision.storage, pas sur disque).

Conseil de prise de vue : pour des angles fiables (flexion/extension du cou,
du tronc et du bras), filmer la personne DE PROFIL plutôt que de face.
"""
import argparse
import sys
from pathlib import Path

from tms_vision.pipeline import analyze_video, generate_run_id
from tms_vision.export import write_frames_csv, write_summary_json
from tms_vision.pose3d_export import write_pose3d_json


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--load-kg doit être positif ou nul")
    return parsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse ergonomique RULA d'une vidéo de poste de travail."
    )
    parser.add_argument("--source", required=True, help='"webcam" ou chemin vers un fichier vidéo')
    parser.add_argument("--side", choices=["left", "right"], default="right")
    parser.add_argument("--load-kg", type=_non_negative_float, default=0.0)
    parser.add_argument("--wrist-twist", choices=["normal", "extreme"], default="normal")
    parser.add_argument("--output-dir", default="outputs")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    result = analyze_video(
        source=args.source, side=args.side, load_kg=args.load_kg, wrist_twist=args.wrist_twist,
    )
    if result.empty:
        return

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    run_id = generate_run_id()

    video_path = output_path / f"{run_id}_annotated.mp4"
    video_path.write_bytes(result.video_bytes)

    csv_path = output_path / f"{run_id}_frames.csv"
    write_frames_csv(result.frame_rows, str(csv_path))

    summary_path = output_path / f"{run_id}_summary.json"
    write_summary_json(result.summary, str(summary_path))

    pose3d_path = output_path / f"{run_id}_pose3d.json"
    write_pose3d_json(str(pose3d_path), result.pose3d_records)

    print(f"Vidéo annotée : {video_path}")
    print(f"Export CSV/JSON : {csv_path}, {summary_path}")


def main() -> None:
    args = parse_args(sys.argv[1:])
    try:
        run(args)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Traitement interrompu par l'utilisateur.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Lancer la suite CLI pour vérifier qu'elle passe sans modification**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (6 tests, fichier de test inchangé -- les assertions existantes portent sur les
messages affichés et les codes de sortie, pas sur les chemins de fichiers exacts, donc restent
valides telles quelles)

- [ ] **Step 4: Commit**

```bash
git add src/tms_vision/cli.py
git commit -m "refactor: cli.py écrit lui-même vidéo/CSV/JSON depuis le résultat en mémoire"
```

---

### Task 9: `api.py` — nouvelles routes `/analyses/...`, suppression de `/outputs`

**Files:**
- Modify: `src/tms_vision/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `storage.save_analysis`, `storage.get_analysis`, `storage.list_analyses`,
  `storage.get_video_bytes`, `storage.get_pose3d_json`, `storage.frames_csv_text` (Tasks 2-4),
  `pipeline.analyze_video`, `pipeline.generate_run_id` (Task 7),
  `pose3d_export.build_pose3d_payload` (Task 6).
- Produces: réponses JSON de `POST /analyses` et `POST /uploads/{id}/complete` avec les clés
  `analysis_id`, `summary`, `annotated_video_url`, `csv_url`, `pose3d_url`, `side` (URLs sous
  forme `/analyses/{id}/...`) ; `GET /analyses`, `GET /analyses/{id}`, `GET /analyses/{id}/video`,
  `GET /analyses/{id}/pose3d`, `GET /analyses/{id}/frames.csv`.

- [ ] **Step 1: Réécrire le test qui échoue**

Remplacer entièrement `tests/test_api.py` :

```python
import tempfile
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from tms_vision import storage
from tms_vision.api import app


def _write_synthetic_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()


def _patch_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")


def test_create_analysis_with_no_detectable_person_returns_empty_summary(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["detected_frame_count"] == 0
    assert body["summary"]["max_score"] == 0
    assert body["annotated_video_url"] == f"/analyses/{body['analysis_id']}/video"
    assert body["csv_url"] == f"/analyses/{body['analysis_id']}/frames.csv"
    assert body["pose3d_url"] == f"/analyses/{body['analysis_id']}/pose3d"
    assert body["side"] == "right"


def test_create_analysis_accepts_worker_and_poste_label(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={
                "side": "right", "load_kg": "0", "wrist_twist": "normal",
                "worker_label": "Marie D.", "poste_label": "Poste emballage",
            },
        )

    assert response.status_code == 200
    analysis_id = response.json()["analysis_id"]
    stored = storage.get_analysis(analysis_id)
    assert stored["worker_label"] == "Marie D."
    assert stored["poste_label"] == "Poste emballage"


def test_create_analysis_rejects_negative_load_kg(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "-1", "wrist_twist": "normal"},
        )

    assert response.status_code == 422


def test_create_analysis_rejects_invalid_side(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "up", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 422


def test_create_analysis_rejects_unreadable_video(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    garbage_path = tmp_path / "not_a_video.mp4"
    garbage_path.write_bytes(b"this is not a real video file")

    client = TestClient(app)
    with open(garbage_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("not_a_video.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 422


def test_analysis_resources_are_actually_served_at_returned_urls(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 200
    body = response.json()

    video_response = client.get(body["annotated_video_url"])
    assert video_response.status_code == 200
    assert len(video_response.content) > 0
    assert "attachment" in video_response.headers.get("content-disposition", "")

    csv_response = client.get(body["csv_url"])
    assert csv_response.status_code == 200
    assert len(csv_response.content) > 0
    assert "attachment" in csv_response.headers.get("content-disposition", "")

    pose3d_response = client.get(body["pose3d_url"])
    assert pose3d_response.status_code == 200
    assert len(pose3d_response.content) > 0


def test_get_analysis_video_returns_404_for_unknown_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.get("/analyses/does-not-exist/video").status_code == 404
    assert client.get("/analyses/does-not-exist/pose3d").status_code == 404
    assert client.get("/analyses/does-not-exist/frames.csv").status_code == 404
    assert client.get("/analyses/does-not-exist").status_code == 404


def test_list_analyses_returns_created_analysis(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        create_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    analysis_id = create_response.json()["analysis_id"]

    list_response = client.get("/analyses")

    assert list_response.status_code == 200
    ids = [item["id"] for item in list_response.json()]
    assert analysis_id in ids


def test_create_analysis_cleans_up_temp_file_when_upload_copy_fails(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    created_paths = []
    original_named_temporary_file = tempfile.NamedTemporaryFile

    def _tracking_named_temporary_file(*args, **kwargs):
        handle = original_named_temporary_file(*args, **kwargs)
        created_paths.append(Path(handle.name))
        return handle

    monkeypatch.setattr(
        "tms_vision.api.tempfile.NamedTemporaryFile", _tracking_named_temporary_file
    )

    def _raise_copyfileobj(*_args, **_kwargs):
        raise OSError("disque plein simulé")

    monkeypatch.setattr("tms_vision.api.shutil.copyfileobj", _raise_copyfileobj)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app, raise_server_exceptions=False)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 500
    assert len(created_paths) == 1
    assert not created_paths[0].exists()


def test_start_upload_creates_session_with_metadata(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "3"})

    assert response.status_code == 200
    upload_id = response.json()["upload_id"]
    meta_path = tmp_path / ".uploads" / upload_id / "meta.json"
    assert meta_path.is_file()


def test_start_upload_rejects_zero_total_chunks(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "0"})

    assert response.status_code == 422


def test_upload_chunk_writes_chunk_file(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 200
    chunk_path = tmp_path / ".uploads" / upload_id / "chunk_000000"
    assert chunk_path.read_bytes() == b"hello"


def test_upload_chunk_rejects_unknown_upload_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.put(
        "/uploads/does-not-exist/chunks/0",
        files={"file": ("chunk-0", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 404


def test_upload_chunk_rejects_out_of_range_index(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/5",
        files={"file": ("chunk-5", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 400


def test_upload_chunks_then_complete_matches_direct_analysis(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)
    video_bytes = video_path.read_bytes()
    midpoint = len(video_bytes) // 2
    chunks = [video_bytes[:midpoint], video_bytes[midpoint:]]

    client = TestClient(app)
    start_response = client.post(
        "/uploads", data={"filename": "synthetic.mp4", "total_chunks": str(len(chunks))}
    )
    upload_id = start_response.json()["upload_id"]

    for index, chunk in enumerate(chunks):
        chunk_response = client.put(
            f"/uploads/{upload_id}/chunks/{index}",
            files={"file": (f"chunk-{index}", chunk, "application/octet-stream")},
        )
        assert chunk_response.status_code == 200

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["annotated_video_url"] == f"/analyses/{body['analysis_id']}/video"
    assert body["side"] == "right"
    assert not (tmp_path / ".uploads" / upload_id).exists()

    with open(video_path, "rb") as video_file:
        direct_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    assert direct_response.status_code == 200
    assert body["summary"] == direct_response.json()["summary"]


def test_chunks_reassembled_by_index_regardless_of_arrival_order(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)
    video_bytes = video_path.read_bytes()
    midpoint = len(video_bytes) // 2
    chunks = [video_bytes[:midpoint], video_bytes[midpoint:]]

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "synthetic.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    client.put(
        f"/uploads/{upload_id}/chunks/1",
        files={"file": ("chunk-1", chunks[1], "application/octet-stream")},
    )
    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", chunks[0], "application/octet-stream")},
    )

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["frame_count"] == 3


def test_complete_upload_fails_when_chunk_missing(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"data", "application/octet-stream")},
    )

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 422


def test_complete_upload_rejects_unknown_upload_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/uploads/does-not-exist/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 404


def test_create_analysis_rejects_video_estimated_too_large(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("tms_vision.api.MAX_ESTIMATED_MEMORY_BYTES", 1)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 422


def test_complete_upload_cleans_up_session_on_analysis_failure(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "garbage.mp4", "total_chunks": "1"})
    upload_id = start_response.json()["upload_id"]

    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"this is not a real video file", "application/octet-stream")},
    )

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 422
    assert not (tmp_path / ".uploads" / upload_id).exists()


def test_upload_chunk_overwrite_keeps_last_write(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "1"})
    upload_id = start_response.json()["upload_id"]

    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"first-attempt", "application/octet-stream")},
    )
    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"second-attempt-wins", "application/octet-stream")},
    )

    chunk_path = tmp_path / ".uploads" / upload_id / "chunk_000000"
    assert chunk_path.read_bytes() == b"second-attempt-wins"


def test_start_upload_rejects_excessive_total_chunks(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "100000"})

    assert response.status_code == 422


def test_upload_chunk_rejects_malformed_upload_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.put(
        "/uploads/not-a-uuid/chunks/0",
        files={"file": ("chunk-0", b"data", "application/octet-stream")},
    )

    assert response.status_code == 404
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_api.py -v`
Expected: FAIL (routes `/analyses/{id}/video` etc. inexistantes -> 404 inattendus, ou
`TypeError` sur les form fields `worker_label`/`poste_label`)

- [ ] **Step 3: Réécrire `api.py`**

Remplacer entièrement `src/tms_vision/api.py` :

```python
"""API FastAPI : expose le pipeline Phase 1 (tms_vision.pipeline) pour la
capture web. Reçoit un clip vidéo (enregistré dans le navigateur en un seul
POST /analyses, ou importé et envoyé par chunks via POST /uploads + PUT
.../chunks/{index} + POST .../complete), lance l'analyse RULA existante,
persiste le résultat en DuckDB (tms_vision.storage) et renvoie le résumé +
les liens vers les ressources produites (voir
docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md,
docs/superpowers/specs/2026-09-15-web-upload-chunked-design.md et
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md)."""
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import cv2
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from tms_vision import storage
from tms_vision.pipeline import analyze_video, generate_run_id
from tms_vision.pose3d_export import build_pose3d_payload

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Garde-fou mémoire : analyze_video() garde toutes les frames décodées en
# mémoire pour tout traiter par lots (voir pipeline.py). Sans ce garde-fou,
# une vidéo HD/4K longue importée par upload (qui n'a pas la limite
# 640x480/30s imposée à la capture caméra) peut faire monter le process à
# plusieurs Go de RAM. Seuil choisi à partir d'une mesure empirique (revue
# finale de la tranche 2) : ~6.4 Mo par frame en 1080p.
MAX_ESTIMATED_MEMORY_BYTES = 2 * 1024**3  # 2 Gio

# Par défaut, seul le serveur de dev Next.js local est autorisé. Pour tester
# depuis un autre appareil (ex. iPhone via un tunnel HTTPS), surcharger avec
# ALLOWED_ORIGINS="https://mon-tunnel.trycloudflare.com" (une ou plusieurs
# origines séparées par des virgules) avant de lancer uvicorn.
_default_origins = "http://localhost:3000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "PUT"],
    allow_headers=["*"],
)


def _reject_if_estimated_too_large(video_path: Path) -> None:
    capture = cv2.VideoCapture(str(video_path))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()

    estimated_bytes = frame_count * width * height * 3 * 2
    if estimated_bytes > MAX_ESTIMATED_MEMORY_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                "Vidéo trop volumineuse pour être analysée (résolution et/ou durée trop "
                "élevées pour la mémoire disponible du serveur). Réduisez la résolution ou "
                "la durée du clip."
            ),
        )


async def _analyze_and_build_response(
    video_path: Path,
    side: str,
    load_kg: float,
    wrist_twist: str,
    worker_label: str | None,
    poste_label: str | None,
) -> dict:
    """Appelle analyze_video sur un fichier déjà sur disque, persiste le
    résultat en DuckDB et construit la réponse JSON standard. Partagé par
    create_analysis (upload direct) et complete_upload (upload par chunks) :
    les deux finissent par produire un seul fichier vidéo local, traité de
    façon identique à partir de ce point."""
    _reject_if_estimated_too_large(video_path)
    try:
        result = await run_in_threadpool(
            analyze_video, source=str(video_path), side=side, load_kg=load_kg,
            wrist_twist=wrist_twist,
        )
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.empty:
        raise HTTPException(
            status_code=422,
            detail="Vidéo illisible ou vide : aucune frame n'a pu être extraite.",
        )

    analysis_id = generate_run_id()
    pose3d_json = json.dumps(build_pose3d_payload(result.pose3d_records), ensure_ascii=False)
    storage.save_analysis(
        analysis_id=analysis_id,
        created_at=datetime.now(timezone.utc),
        side=side, load_kg=load_kg, wrist_twist=wrist_twist,
        worker_label=worker_label, poste_label=poste_label,
        summary=result.summary, video_bytes=result.video_bytes, pose3d_json=pose3d_json,
        frame_rows=result.frame_rows,
    )

    return {
        "analysis_id": analysis_id,
        "summary": result.summary,
        "annotated_video_url": f"/analyses/{analysis_id}/video",
        "csv_url": f"/analyses/{analysis_id}/frames.csv",
        "pose3d_url": f"/analyses/{analysis_id}/pose3d",
        "side": side,
    }


@app.post("/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(..., ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
    worker_label: str | None = Form(None),
    poste_label: str | None = Form(None),
) -> dict:
    suffix = Path(file.filename or "").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            shutil.copyfileobj(file.file, tmp)
        return await _analyze_and_build_response(
            upload_path, side, load_kg, wrist_twist, worker_label, poste_label
        )
    finally:
        upload_path.unlink(missing_ok=True)


@app.post("/uploads")
async def start_upload(
    filename: str = Form(...),
    total_chunks: int = Form(..., ge=1, le=10000),
) -> dict:
    """Démarre une session d'upload par chunks. L'état de la session vit
    entièrement sur le système de fichiers (meta.json + fichiers chunk_NNNNNN
    écrits par upload_chunk/complete_upload) : pas de dict en mémoire, pour
    survivre à un redémarrage d'uvicorn --reload en cours d'upload. C'est un
    état transitoire de transport, pas un résultat d'analyse -- il reste
    hors DuckDB, voir docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md."""
    upload_id = uuid.uuid4().hex
    session_dir = OUTPUT_DIR / ".uploads" / upload_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"filename": filename, "total_chunks": total_chunks})
    )
    return {"upload_id": upload_id}


def _resolve_session_dir(upload_id: str) -> Path:
    try:
        uuid.UUID(upload_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Session d'envoi introuvable.") from error
    return OUTPUT_DIR / ".uploads" / upload_id


@app.put("/uploads/{upload_id}/chunks/{index}")
async def upload_chunk(upload_id: str, index: int, file: UploadFile = File(...)) -> dict:
    session_dir = _resolve_session_dir(upload_id)
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Session d'envoi introuvable.")

    total_chunks = json.loads(meta_path.read_text())["total_chunks"]
    if not 0 <= index < total_chunks:
        raise HTTPException(status_code=400, detail="Index de morceau hors limites.")

    chunk_path = session_dir / f"chunk_{index:06d}"
    with open(chunk_path, "wb") as chunk_file:
        shutil.copyfileobj(file.file, chunk_file)

    return {"received": index}


@app.post("/uploads/{upload_id}/complete")
async def complete_upload(
    upload_id: str,
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(..., ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
    worker_label: str | None = Form(None),
    poste_label: str | None = Form(None),
) -> dict:
    session_dir = _resolve_session_dir(upload_id)
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Session d'envoi introuvable.")

    meta = json.loads(meta_path.read_text())
    total_chunks = meta["total_chunks"]
    chunk_paths = [session_dir / f"chunk_{i:06d}" for i in range(total_chunks)]
    missing = [i for i, path in enumerate(chunk_paths) if not path.is_file()]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Morceau(x) manquant(s) : {missing}. Réessayez l'import du fichier.",
        )

    suffix = Path(meta["filename"]).suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            for chunk_path in chunk_paths:
                with open(chunk_path, "rb") as chunk_file:
                    shutil.copyfileobj(chunk_file, tmp)
        return await _analyze_and_build_response(
            upload_path, side, load_kg, wrist_twist, worker_label, poste_label
        )
    finally:
        upload_path.unlink(missing_ok=True)
        shutil.rmtree(session_dir, ignore_errors=True)


@app.get("/analyses")
async def list_analyses(
    worker_label: str | None = None,
    poste_label: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    return storage.list_analyses(
        worker_label=worker_label, poste_label=poste_label, since=since, until=until
    )


@app.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str) -> dict:
    analysis = storage.get_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return analysis


@app.get("/analyses/{analysis_id}/video")
async def get_analysis_video(analysis_id: str) -> Response:
    video_bytes = storage.get_video_bytes(analysis_id)
    if video_bytes is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return Response(
        content=video_bytes, media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{analysis_id}_annotated.mp4"'},
    )


@app.get("/analyses/{analysis_id}/pose3d")
async def get_analysis_pose3d(analysis_id: str) -> Response:
    pose3d_json = storage.get_pose3d_json(analysis_id)
    if pose3d_json is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return Response(content=pose3d_json, media_type="application/json")


@app.get("/analyses/{analysis_id}/frames.csv")
async def get_analysis_frames_csv(analysis_id: str) -> Response:
    csv_text = storage.frames_csv_text(analysis_id)
    if csv_text is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{analysis_id}_frames.csv"'},
    )
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_api.py -v`
Expected: PASS (24 tests)

- [ ] **Step 5: Lancer toute la suite Python pour vérifier l'absence de régression**

Run: `pytest -v`
Expected: PASS (tous les tests, y compris `test_storage.py`, `test_export.py`,
`test_pose3d_export.py`, `test_pipeline.py`, `test_cli.py`, `test_api.py` et tous les tests déjà
existants non touchés par ce plan)

- [ ] **Step 6: Commit**

```bash
git add src/tms_vision/api.py tests/test_api.py
git commit -m "feat: routes /analyses/... backées par DuckDB, suppression de /outputs"
```

---

### Task 10: Documentation — README

**Files:**
- Modify: `README.md`

**Interfaces:** (aucune — tâche de documentation)

- [ ] **Step 1: Ajouter une entrée dans la liste des documents de référence (section
  "Pour reprendre le projet plus tard")**

Dans `README.md`, juste après la ligne citant
`docs/superpowers/specs/2026-09-21-3d-posture-muscle-segment-coloring-design.md` et son plan
associé, ajouter :

```markdown
- `docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md` — la spec du stockage des
  analyses RULA en DuckDB (persistance dans le temps, migration hors du système de fichiers pour
  le flux API web).
- `docs/superpowers/plans/2026-09-22-duckdb-analysis-storage-plan.md` — le plan d'implémentation
  de cette tranche.
```

- [ ] **Step 2: Documenter la tranche livrée dans la section Phase 2 du roadmap**

Ajouter, après le dernier bloc "Avatar 3D de posture, Tranche 4" existant dans la section
"Phase 2 : Création des Contenus & Interface" :

```markdown
#### ✅ Stockage des analyses en DuckDB — TERMINÉE

- **Contexte** : depuis la Tranche 1, chaque analyse écrivait 4 fichiers isolés dans `outputs/`
  (vidéo annotée, CSV, résumé JSON, landmarks 3D), sans aucun moyen de lister ou d'interroger les
  analyses passées. Cette tranche migre ce stockage vers DuckDB, avec un historique interrogeable
  — préalable nécessaire à la recommandation de capsules par zone (tranche suivante).
- **`src/tms_vision/storage.py`** (nouveau) : deux tables DuckDB (`data/tms_vision.duckdb`,
  non committé) — `analyses` (métadonnées, résumé agrégé, blobs vidéo/pose3D) et
  `analysis_frames` (une ligne par frame, scores RULA et zones d'action par segment
  interrogeables en SQL).
- **`src/tms_vision/pipeline.py`** : `analyze_video()` devient pur (retourne bytes/dicts en
  mémoire), n'écrit plus aucun fichier durable.
- **`src/tms_vision/api.py`** : `POST /analyses` et `POST /uploads/{id}/complete` acceptent
  désormais `worker_label`/`poste_label` (tags texte libres, pas d'authentification) et persistent
  en DuckDB. `GET /outputs/{filename}` est remplacé par `GET /analyses`, `GET /analyses/{id}`,
  `GET /analyses/{id}/video`, `GET /analyses/{id}/pose3d`, `GET /analyses/{id}/frames.csv`.
- **`src/tms_vision/cli.py`** (workflow Phase 1 local) : continue d'écrire vidéo/CSV/JSON dans
  `--output-dir` comme avant — seule la CLI écrit encore sur le système de fichiers, l'API web
  persiste exclusivement en DuckDB.
- **Ce qui n'est pas dans cette tranche** : UI d'historique/dashboard consommant `GET /analyses`,
  migration des runs déjà présents dans `outputs/`, authentification, support des requêtes
  `Range` pour le streaming vidéo (voir spec pour le détail).
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: documente le stockage des analyses en DuckDB dans le README"
```

---

## Self-Review

**Couverture de la spec** : architecture (Task 7 pipeline pur + Task 1-4 storage.py),
modèle de données (Task 1), API (Task 9), limite Range acceptée (documentée, aucune implémentation
requise), gestion d'erreurs 404 (Task 9), CLI préservée (Task 8), tests par module (Tasks 1-9),
hors périmètre (non implémenté, conforme à la spec). Tout couvert.

**Scan de placeholders** : aucun "TBD"/"TODO" ; chaque étape de code contient du code complet et
exécutable, pas de description sans implémentation.

**Cohérence des types/signatures** : vérifié que `analyze_video(source, side, load_kg,
wrist_twist)` (Task 7) est appelé avec les mêmes 4 arguments partout (Task 8 `cli.py`, Task 9
`api.py`) ; `ResultsExporter().rows()`/`.summary()` (Task 5) utilisés identiquement dans Task 7 ;
`storage.save_analysis(...)` (Task 2) appelé avec exactement les mêmes noms de paramètres dans
Task 9 ; `CSV_FIELDS` importé de `export.py` dans `storage.py` (Tasks 1, 4) et dans les tests
(Task 2-4) ; `build_pose3d_payload` (Task 6) utilisé de façon identique dans Task 7 (fusion des
segments) et Task 9 (sérialisation JSON pour le blob).
