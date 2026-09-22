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
