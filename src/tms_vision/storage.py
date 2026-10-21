"""Persistance des résultats d'analyse RULA en DuckDB (voir
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md). Chaque
fonction publique ouvre puis referme sa propre connexion -- suffisant à
l'échelle actuelle du projet (un seul process uvicorn, pas de charge
concurrente à optimiser)."""
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from tms_vision.export import CSV_FIELDS

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


def _to_naive_utc(value: datetime) -> datetime:
    """DuckDB stocke `created_at` en TIMESTAMP naïf. Note : la colonne
    TIMESTAMPTZ a été essayée pour ce champ, mais la conversion Python de ce
    type nécessite le paquet `pytz` (absent de requirements.txt) dans cette
    version de DuckDB -- échec à l'exécution ("Required module 'pytz' failed
    to import"). Solution retenue à la place : on convertit nous-mêmes tout
    datetime "aware" en UTC puis on retire le tzinfo avant l'écriture
    (`_to_naive_utc`), et on réattache `timezone.utc` à la lecture
    (`_attach_utc`) -- le round-trip est alors exact et sans ambiguïté, sans
    dépendre de l'heure locale du serveur DuckDB. Un datetime déjà naïf en
    entrée est supposé déjà exprimé en UTC et passe inchangé."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _attach_utc(value: datetime) -> datetime:
    """Inverse de _to_naive_utc : réattache timezone.utc à une valeur naïve
    lue depuis la colonne `created_at`, pour que .isoformat() produise un
    suffixe +00:00 explicite plutôt qu'une chaîne ambiguë."""
    return value.replace(tzinfo=timezone.utc)


def _connect() -> "duckdb.DuckDBPyConnection":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(CREATE_ANALYSES_TABLE)
    conn.execute(CREATE_ANALYSIS_FRAMES_TABLE)
    return conn


SEGMENT_COLUMNS = [
    "neck_segment_action_level",
    "trunk_segment_action_level",
    "upper_arm_segment_action_level",
    "lower_arm_segment_action_level",
]
ANGLE_COLUMNS = [
    "neck_flexion_deg",
    "trunk_flexion_deg",
    "upper_arm_flexion_deg",
    "lower_arm_angle_deg",
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
        conn.begin()
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
                    analysis_id, _to_naive_utc(created_at), side, load_kg, wrist_twist,
                    worker_label, poste_label,
                    summary["frame_count"], summary["detected_frame_count"], summary["max_score"],
                    summary["average_score"],
                    json.dumps(summary["time_by_action_level"], ensure_ascii=False),
                    video_bytes, pose3d_json,
                ],
            )
            if frame_rows:
                insert_frame_sql = (
                    "INSERT INTO analysis_frames (analysis_id, "
                    + ", ".join(FRAME_VALUE_COLUMNS)
                    + ") VALUES ("
                    + ", ".join(["?"] * (len(FRAME_VALUE_COLUMNS) + 1))
                    + ")"
                )
                conn.executemany(
                    insert_frame_sql,
                    [
                        [analysis_id] + [row.get(column) for column in FRAME_VALUE_COLUMNS]
                        for row in frame_rows
                    ],
                )
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
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
    record["created_at"] = _attach_utc(record["created_at"]).isoformat()
    return record


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
        params.append(_to_naive_utc(since))
    if until is not None:
        clauses.append("created_at <= ?")
        params.append(_to_naive_utc(until))
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
        record["created_at"] = _attach_utc(record["created_at"]).isoformat()
        results.append(record)
    return results


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


def get_frame_segments(analysis_id: str) -> list[dict] | None:
    conn = _connect()
    try:
        exists = conn.execute(
            "SELECT 1 FROM analyses WHERE id = ?", [analysis_id]
        ).fetchone()
        if exists is None:
            return None
        columns = ["frame_index", "timestamp_seconds"] + SEGMENT_COLUMNS
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM analysis_frames "
            "WHERE analysis_id = ? ORDER BY frame_index",
            [analysis_id],
        ).fetchall()
    finally:
        conn.close()

    return [dict(zip(columns, row)) for row in rows]


def get_frame_angles(analysis_id: str) -> list[dict] | None:
    conn = _connect()
    try:
        exists = conn.execute(
            "SELECT 1 FROM analyses WHERE id = ?", [analysis_id]
        ).fetchone()
        if exists is None:
            return None
        columns = ["frame_index", "timestamp_seconds", "detected"] + ANGLE_COLUMNS + SEGMENT_COLUMNS
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM analysis_frames "
            "WHERE analysis_id = ? ORDER BY frame_index",
            [analysis_id],
        ).fetchall()
    finally:
        conn.close()

    return [dict(zip(columns, row)) for row in rows]
