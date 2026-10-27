"""Persistance des résultats d'analyse RULA en DuckDB (voir
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md). Chaque
fonction publique ouvre puis referme sa propre connexion -- suffisant à
l'échelle actuelle du projet (un seul process uvicorn, pas de charge
concurrente à optimiser)."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone
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
    ankle_flexion_deg DOUBLE,
    finger_curl_deg DOUBLE,
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
    hand_segment_action_level VARCHAR,
    foot_segment_action_level VARCHAR,
    PRIMARY KEY (analysis_id, frame_index)
)
"""

CREATE_BILANS_TABLE = """
CREATE TABLE IF NOT EXISTS bilans (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    label VARCHAR,
    workday_hours DOUBLE NOT NULL
)
"""

CREATE_BILAN_FOLDERS_TABLE = """
CREATE TABLE IF NOT EXISTS bilan_folders (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    name VARCHAR NOT NULL
)
"""

CREATE_BILAN_ANALYSES_TABLE = """
CREATE TABLE IF NOT EXISTS bilan_analyses (
    bilan_id VARCHAR NOT NULL REFERENCES bilans(id),
    analysis_id VARCHAR NOT NULL REFERENCES analyses(id),
    activity_hours DOUBLE NOT NULL,
    representative BOOLEAN NOT NULL,
    attached_at TIMESTAMP NOT NULL,
    PRIMARY KEY (bilan_id, analysis_id)
)
"""

CREATE_METIER_MODELS_TABLE = """
CREATE TABLE IF NOT EXISTS metier_models (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    title VARCHAR NOT NULL,
    description VARCHAR,
    workday_hours DOUBLE NOT NULL,
    tasks_json VARCHAR NOT NULL
)
"""

CREATE_BILAN_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS bilan_tasks (
    id VARCHAR PRIMARY KEY,
    bilan_id VARCHAR NOT NULL REFERENCES bilans(id),
    created_at TIMESTAMP NOT NULL,
    name VARCHAR NOT NULL,
    zones_json VARCHAR NOT NULL,
    activity_hours DOUBLE NOT NULL,
    time_slots_json VARCHAR,
    days_per_week DOUBLE,
    cycles_per_minute DOUBLE,
    cycle_seconds DOUBLE,
    static_seconds DOUBLE,
    load_kg DOUBLE,
    analysis_id VARCHAR,
    source VARCHAR NOT NULL,
    notes VARCHAR,
    zone_cycles_json VARCHAR,
    workstation VARCHAR,
    breaks VARCHAR
)
"""

# Colonnes ajoutées après la première version de bilan_tasks. `cycles_per_minute`
# (une fréquence pour toutes les zones) n'est plus écrite : lue seulement pour les
# anciennes lignes, voir _task_record.
_BILAN_TASKS_LATER_COLUMNS = [
    ("zone_cycles_json", "VARCHAR"),
    ("workstation", "VARCHAR"),
    ("breaks", "VARCHAR"),
]

CREATE_ANALYSIS_LOADS_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_loads (
    analysis_id VARCHAR PRIMARY KEY REFERENCES analyses(id),
    kind VARCHAR NOT NULL,
    kg DOUBLE,
    kg_min DOUBLE,
    kg_max DOUBLE,
    original_load_kg DOUBLE NOT NULL,
    score_range VARCHAR,
    updated_at TIMESTAMP NOT NULL
)
"""

CREATE_LIBRARY_SHARES_TABLE = """
CREATE TABLE IF NOT EXISTS library_shares (
    token VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    recipient_email VARCHAR NOT NULL,
    practitioner_name VARCHAR,
    message VARCHAR,
    items_json VARCHAR NOT NULL,
    email_status VARCHAR NOT NULL
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


_TRANCHE_5_COLUMNS = [
    ("ankle_flexion_deg", "DOUBLE"),
    ("finger_curl_deg", "DOUBLE"),
    ("hand_segment_action_level", "VARCHAR"),
    ("foot_segment_action_level", "VARCHAR"),
]


# Modèle de pose utilisé (NULL = anciennes analyses : MediaPipe Pose 33), options activées (JSON)
# et nombre de points par personne.
_POSE_MODEL_COLUMNS = [
    ("pose_model", "VARCHAR"),
    ("pose_options", "VARCHAR"),
    ("keypoint_count", "INTEGER"),
    ("hands_metrics", "VARCHAR"),  # JSON : par côté, flexion des doigts, préhensions, cadence
]

# Points des modèles complémentaires (mains, plus tard whole-body et points custom), au format
# normalisé (pose_models/schema.py) : une ligne par image et par modèle. Les 33 points de Pose
# restent dans analyses.pose3d_json ; cette table n'est écrite que si un modèle complémentaire est
# actif, donc une analyse standard ne coûte rien de plus.
CREATE_ANALYSIS_KEYPOINTS_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_keypoints (
    analysis_id VARCHAR NOT NULL REFERENCES analyses(id),
    frame_index INTEGER NOT NULL,
    model VARCHAR NOT NULL,
    keypoints_json VARCHAR NOT NULL,
    PRIMARY KEY (analysis_id, frame_index, model)
)
"""


def _connect() -> "duckdb.DuckDBPyConnection":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(CREATE_ANALYSES_TABLE)
    conn.execute(CREATE_ANALYSIS_FRAMES_TABLE)
    conn.execute(CREATE_ANALYSIS_KEYPOINTS_TABLE)
    conn.execute(CREATE_BILANS_TABLE)
    conn.execute(CREATE_BILAN_FOLDERS_TABLE)
    conn.execute(CREATE_BILAN_ANALYSES_TABLE)
    conn.execute(CREATE_BILAN_TASKS_TABLE)
    conn.execute(CREATE_METIER_MODELS_TABLE)
    conn.execute(CREATE_ANALYSIS_LOADS_TABLE)
    conn.execute(CREATE_LIBRARY_SHARES_TABLE)
    # Archivage des bilans (ajouté après coup) : NULL = bilan actif.
    conn.execute("ALTER TABLE bilans ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP")
    # Rangement des bilans en dossiers (par entreprise, par exemple) : NULL = sans dossier.
    conn.execute("ALTER TABLE bilans ADD COLUMN IF NOT EXISTS folder_id VARCHAR")
    # Réglages du programme d'étirements d'un bilan : nombre d'exercices et sélection du praticien
    # (liste JSON d'identifiants d'exercices). NULL = réglage par défaut / programme automatique.
    conn.execute("ALTER TABLE bilans ADD COLUMN IF NOT EXISTS program_size INTEGER")
    conn.execute("ALTER TABLE bilans ADD COLUMN IF NOT EXISTS program_selection VARCHAR")
    # Dossiers dans des dossiers (entreprise > service > poste) : NULL = à la racine.
    conn.execute("ALTER TABLE bilan_folders ADD COLUMN IF NOT EXISTS parent_id VARCHAR")
    for column, column_type in _BILAN_TASKS_LATER_COLUMNS:
        conn.execute(f"ALTER TABLE bilan_tasks ADD COLUMN IF NOT EXISTS {column} {column_type}")
    # Bases créées avant la Tranche 5 (mains et pieds) : les nouvelles colonnes restent NULL.
    for column, column_type in _TRANCHE_5_COLUMNS:
        conn.execute(f"ALTER TABLE analysis_frames ADD COLUMN IF NOT EXISTS {column} {column_type}")
    for column, column_type in _POSE_MODEL_COLUMNS:
        conn.execute(f"ALTER TABLE analyses ADD COLUMN IF NOT EXISTS {column} {column_type}")
    return conn


SEGMENT_COLUMNS = [
    "neck_segment_action_level",
    "trunk_segment_action_level",
    "upper_arm_segment_action_level",
    "lower_arm_segment_action_level",
    "hand_segment_action_level",
    "foot_segment_action_level",
]
ANGLE_COLUMNS = [
    "neck_flexion_deg",
    "trunk_flexion_deg",
    "upper_arm_flexion_deg",
    "lower_arm_angle_deg",
    "wrist_flexion_deg",
    "ankle_flexion_deg",
]
FRAME_VALUE_COLUMNS = CSV_FIELDS + SEGMENT_COLUMNS

_ANALYSIS_COLUMNS = [
    "id", "created_at", "side", "load_kg", "wrist_twist", "worker_label", "poste_label",
    "frame_count", "detected_frame_count", "max_score", "average_score", "time_by_action_level",
    "pose_model", "pose_options", "keypoint_count", "hands_metrics",
]


def _normalize_pose_fields(record: dict) -> None:
    """Analyses antérieures au sélecteur de modèle : MediaPipe Pose 33, aucune option."""
    record["pose_model"] = record["pose_model"] or "mediapipe_pose_33"
    record["pose_options"] = json.loads(record["pose_options"]) if record["pose_options"] else {}
    record["keypoint_count"] = record["keypoint_count"] or 33
    record["hands_metrics"] = json.loads(record["hands_metrics"]) if record["hands_metrics"] else None


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
    pose_model: str = "mediapipe_pose_33",
    pose_options: str | None = None,
    keypoint_count: int = 33,
    hands_metrics: str | None = None,
    keypoint_frames: list[dict] | None = None,
) -> None:
    """`keypoint_frames` : points des modèles complémentaires, au format `FramePose.to_dict()`."""
    conn = _connect()
    try:
        conn.begin()
        try:
            conn.execute(
                """
                INSERT INTO analyses (
                    id, created_at, side, load_kg, wrist_twist, worker_label, poste_label,
                    frame_count, detected_frame_count, max_score, average_score,
                    time_by_action_level, video_bytes, pose3d_json,
                    pose_model, pose_options, keypoint_count, hands_metrics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    analysis_id, _to_naive_utc(created_at), side, load_kg, wrist_twist,
                    worker_label, poste_label,
                    summary["frame_count"], summary["detected_frame_count"], summary["max_score"],
                    summary["average_score"],
                    json.dumps(summary["time_by_action_level"], ensure_ascii=False),
                    video_bytes, pose3d_json,
                    pose_model, pose_options, keypoint_count, hands_metrics,
                ],
            )
            if keypoint_frames:
                conn.executemany(
                    "INSERT INTO analysis_keypoints (analysis_id, frame_index, model, keypoints_json) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        [analysis_id, entry["frame"], entry["model"],
                         json.dumps(entry["keypoints"], ensure_ascii=False, separators=(",", ":"))]
                        for entry in keypoint_frames
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


def get_keypoints(analysis_id: str) -> list[dict] | None:
    """Points des modèles complémentaires d'une analyse, au format normalisé, ou `None` si
    l'analyse n'existe pas (liste vide si aucun modèle complémentaire n'était actif)."""
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM analyses WHERE id = ?", [analysis_id]).fetchone() is None:
            return None
        rows = conn.execute(
            "SELECT frame_index, model, keypoints_json FROM analysis_keypoints "
            "WHERE analysis_id = ? ORDER BY frame_index, model",
            [analysis_id],
        ).fetchall()
    finally:
        conn.close()
    return [
        {"frame": frame, "person_id": 1, "model": model, "keypoints": json.loads(keypoints_json)}
        for frame, model, keypoints_json in rows
    ]


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
    _normalize_pose_fields(record)
    record["created_at"] = _attach_utc(record["created_at"]).isoformat()
    record["load"] = _read_load(analysis_id, record["load_kg"])
    return record


def _read_load(analysis_id: str, analysis_load_kg: float) -> dict:
    """Poids d'une analyse. Sans ligne analysis_loads (analyse jamais mise à
    jour, ou antérieure à cette fonctionnalité), le poids est le `load_kg`
    d'origine, lu comme un poids précis."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT kind, kg, kg_min, kg_max, original_load_kg, score_range "
            "FROM analysis_loads WHERE analysis_id = ?",
            [analysis_id],
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {
            "kind": "exact", "kg": analysis_load_kg, "kg_min": None, "kg_max": None,
            "original_load_kg": analysis_load_kg, "score_range": None,
        }
    kind, kg, kg_min, kg_max, original_load_kg, score_range = row
    return {
        "kind": kind, "kg": kg, "kg_min": kg_min, "kg_max": kg_max,
        "original_load_kg": original_load_kg,
        "score_range": json.loads(score_range) if score_range is not None else None,
    }


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
        _normalize_pose_fields(record)
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


_BILAN_COLUMNS = ["id", "created_at", "label", "workday_hours", "archived_at", "folder_id"]


def _bilan_record(row) -> dict:
    record = dict(zip(_BILAN_COLUMNS, row))
    record["created_at"] = _attach_utc(record["created_at"]).isoformat()
    if record["archived_at"] is not None:
        record["archived_at"] = _attach_utc(record["archived_at"]).isoformat()
    return record


def create_bilan(
    *, bilan_id: str, created_at: datetime, label: str | None, workday_hours: float
) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO bilans (id, created_at, label, workday_hours) VALUES (?, ?, ?, ?)",
            [bilan_id, _to_naive_utc(created_at), label, workday_hours],
        )
    finally:
        conn.close()


def attach_analysis(
    *, bilan_id: str, analysis_id: str, activity_hours: float, representative: bool
) -> None:
    """Rattache une analyse à un bilan. KeyError si le bilan ou l'analyse est
    inconnu, ValueError si l'analyse est déjà rattachée à ce bilan."""
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM bilans WHERE id = ?", [bilan_id]).fetchone() is None:
            raise KeyError(f"bilan {bilan_id}")
        if conn.execute("SELECT 1 FROM analyses WHERE id = ?", [analysis_id]).fetchone() is None:
            raise KeyError(f"analysis {analysis_id}")
        already_attached = conn.execute(
            "SELECT 1 FROM bilan_analyses WHERE bilan_id = ? AND analysis_id = ?",
            [bilan_id, analysis_id],
        ).fetchone()
        if already_attached is not None:
            raise ValueError(f"analysis {analysis_id} already attached to bilan {bilan_id}")
        conn.execute(
            "INSERT INTO bilan_analyses "
            "(bilan_id, analysis_id, activity_hours, representative, attached_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                bilan_id, analysis_id, activity_hours, representative,
                _to_naive_utc(datetime.now(timezone.utc)),
            ],
        )
    finally:
        conn.close()


def get_bilan(bilan_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {', '.join(_BILAN_COLUMNS)} FROM bilans WHERE id = ?", [bilan_id]
        ).fetchone()
        if row is None:
            return None
        item_rows = conn.execute(
            "SELECT analysis_id, activity_hours, representative FROM bilan_analyses "
            "WHERE bilan_id = ? ORDER BY attached_at, analysis_id",
            [bilan_id],
        ).fetchall()
    finally:
        conn.close()

    record = _bilan_record(row)
    record["items"] = [
        {"analysis_id": a, "activity_hours": h, "representative": r} for a, h, r in item_rows
    ]
    record["tasks"] = list_bilan_tasks(bilan_id)
    return record


_TASK_FIELDS = [
    "name", "zones", "activity_hours", "time_slots", "days_per_week", "zone_cycles",
    "cycle_seconds", "static_seconds", "load_kg", "analysis_id", "source", "notes",
    "workstation", "breaks",
]
_TASK_SELECT = (
    "id, bilan_id, created_at, name, zones_json, activity_hours, time_slots_json, "
    "days_per_week, cycles_per_minute, cycle_seconds, static_seconds, load_kg, "
    "analysis_id, source, notes, zone_cycles_json, workstation, breaks"
)


def _task_record(row) -> dict:
    (task_id, bilan_id, created_at, name, zones_json, activity_hours, time_slots_json,
     days_per_week, cycles_per_minute, cycle_seconds, static_seconds, load_kg,
     analysis_id, source, notes, zone_cycles_json, workstation, breaks) = row
    zones = json.loads(zones_json)
    if zone_cycles_json is not None:
        zone_cycles = json.loads(zone_cycles_json)
    elif cycles_per_minute is not None:
        zone_cycles = {zone: cycles_per_minute for zone in zones}
    else:
        zone_cycles = {}
    return {
        "id": task_id, "bilan_id": bilan_id,
        "created_at": _attach_utc(created_at).isoformat(),
        "name": name, "zones": zones,
        "activity_hours": activity_hours,
        "time_slots": json.loads(time_slots_json) if time_slots_json is not None else None,
        "days_per_week": days_per_week, "zone_cycles": zone_cycles,
        "cycle_seconds": cycle_seconds, "static_seconds": static_seconds,
        "load_kg": load_kg, "analysis_id": analysis_id, "source": source, "notes": notes,
        "workstation": workstation, "breaks": breaks,
    }


def _check_task_analysis(conn, bilan_id: str, analysis_id: str | None) -> None:
    """ValueError si la fiche prétend compléter une analyse absente de ce bilan."""
    if analysis_id is None:
        return
    attached = conn.execute(
        "SELECT 1 FROM bilan_analyses WHERE bilan_id = ? AND analysis_id = ?",
        [bilan_id, analysis_id],
    ).fetchone()
    if attached is None:
        raise ValueError(f"analysis {analysis_id} is not attached to bilan {bilan_id}")


def _task_values(task: dict) -> list:
    slots = task.get("time_slots")
    return [
        task["name"], json.dumps(task["zones"]), task["activity_hours"],
        json.dumps(slots) if slots is not None else None,
        task.get("days_per_week"), None, task.get("cycle_seconds"),
        task.get("static_seconds"), task.get("load_kg"), task.get("analysis_id"),
        task["source"], task.get("notes"),
        json.dumps(task.get("zone_cycles") or {}), task.get("workstation"), task.get("breaks"),
    ]


def list_bilan_tasks(bilan_id: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT {_TASK_SELECT} FROM bilan_tasks WHERE bilan_id = ? ORDER BY created_at, id",
            [bilan_id],
        ).fetchall()
    finally:
        conn.close()
    return [_task_record(row) for row in rows]


def create_bilan_task(*, task_id: str, bilan_id: str, created_at: datetime, task: dict) -> None:
    """Ajoute une fiche d'activité. KeyError si le bilan est inconnu, ValueError si
    `analysis_id` n'est pas rattachée à ce bilan. `task` : champs de _TASK_FIELDS."""
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM bilans WHERE id = ?", [bilan_id]).fetchone() is None:
            raise KeyError(f"bilan {bilan_id}")
        _check_task_analysis(conn, bilan_id, task.get("analysis_id"))
        conn.execute(
            "INSERT INTO bilan_tasks (id, bilan_id, created_at, name, zones_json, "
            "activity_hours, time_slots_json, days_per_week, cycles_per_minute, "
            "cycle_seconds, static_seconds, load_kg, analysis_id, source, notes, "
            "zone_cycles_json, workstation, breaks) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [task_id, bilan_id, _to_naive_utc(created_at), *_task_values(task)],
        )
    finally:
        conn.close()


def duplicate_bilan(
    *, source_id: str, new_id: str, created_at: datetime, label: str | None, task_ids: list[str]
) -> None:
    """Crée `new_id` à partir de `source_id` : durée de la journée et fiches d'activité (dans le
    même ordre, avec les identifiants `task_ids`). Les analyses ne sont pas rattachées à la copie,
    donc les fiches perdent leur lien avec une analyse. KeyError si `source_id` est inconnu."""
    source = get_bilan(source_id)
    if source is None:
        raise KeyError(f"bilan {source_id}")
    create_bilan(
        bilan_id=new_id, created_at=created_at, label=label,
        workday_hours=source["workday_hours"],
    )
    # Une copie reste dans le dossier d'origine (même entreprise, autre personne).
    if source["folder_id"] is not None:
        set_bilan_folder(bilan_id=new_id, folder_id=source["folder_id"])
    for index, (task_id, task) in enumerate(zip(task_ids, source["tasks"], strict=True)):
        copied = {field: task[field] for field in _TASK_FIELDS}
        copied["analysis_id"] = None
        # Un décalage de quelques microsecondes garde l'ordre d'origine des fiches.
        create_bilan_task(
            task_id=task_id, bilan_id=new_id,
            created_at=created_at + timedelta(microseconds=index), task=copied,
        )


def _metier_model_record(row) -> dict:
    model_id, created_at, title, description, workday_hours, tasks_json = row
    return {
        "id": model_id, "created_at": _attach_utc(created_at).isoformat(), "title": title,
        "description": description or "", "workday_hours": workday_hours,
        "tasks": json.loads(tasks_json),
    }


_METIER_MODEL_SELECT = "id, created_at, title, description, workday_hours, tasks_json"


def create_metier_model(
    *, model_id: str, created_at: datetime, title: str, description: str | None,
    workday_hours: float, tasks: list[dict],
) -> None:
    """Enregistre un modèle de métier créé par le praticien. `tasks` : fiches types (voir
    metiers.validate_task), stockées telles quelles."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO metier_models (id, created_at, title, description, workday_hours, "
            "tasks_json) VALUES (?, ?, ?, ?, ?, ?)",
            [model_id, _to_naive_utc(created_at), title, description, workday_hours,
             json.dumps(tasks)],
        )
    finally:
        conn.close()


def list_metier_models() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT {_METIER_MODEL_SELECT} FROM metier_models ORDER BY created_at DESC, id"
        ).fetchall()
    finally:
        conn.close()
    return [_metier_model_record(row) for row in rows]


def get_metier_model(model_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {_METIER_MODEL_SELECT} FROM metier_models WHERE id = ?", [model_id]
        ).fetchone()
    finally:
        conn.close()
    return _metier_model_record(row) if row is not None else None


def delete_metier_model(model_id: str) -> bool:
    """Supprime un modèle créé par le praticien ; False s'il n'existe pas."""
    conn = _connect()
    try:
        existed = conn.execute(
            "SELECT 1 FROM metier_models WHERE id = ?", [model_id]
        ).fetchone() is not None
        conn.execute("DELETE FROM metier_models WHERE id = ?", [model_id])
    finally:
        conn.close()
    return existed


def update_bilan_task(*, task_id: str, bilan_id: str, task: dict) -> None:
    """Remplace les champs d'une fiche. KeyError si la fiche n'existe pas dans ce
    bilan, ValueError si `analysis_id` n'est pas rattachée à ce bilan."""
    conn = _connect()
    try:
        exists = conn.execute(
            "SELECT 1 FROM bilan_tasks WHERE id = ? AND bilan_id = ?", [task_id, bilan_id]
        ).fetchone()
        if exists is None:
            raise KeyError(f"task {task_id}")
        _check_task_analysis(conn, bilan_id, task.get("analysis_id"))
        conn.execute(
            "UPDATE bilan_tasks SET name = ?, zones_json = ?, activity_hours = ?, "
            "time_slots_json = ?, days_per_week = ?, cycles_per_minute = ?, "
            "cycle_seconds = ?, static_seconds = ?, load_kg = ?, analysis_id = ?, "
            "source = ?, notes = ?, zone_cycles_json = ?, workstation = ?, breaks = ? "
            "WHERE id = ? AND bilan_id = ?",
            [*_task_values(task), task_id, bilan_id],
        )
    finally:
        conn.close()


def delete_bilan_task(*, task_id: str, bilan_id: str) -> None:
    """KeyError si la fiche n'existe pas dans ce bilan."""
    conn = _connect()
    try:
        exists = conn.execute(
            "SELECT 1 FROM bilan_tasks WHERE id = ? AND bilan_id = ?", [task_id, bilan_id]
        ).fetchone()
        if exists is None:
            raise KeyError(f"task {task_id}")
        conn.execute("DELETE FROM bilan_tasks WHERE id = ? AND bilan_id = ?", [task_id, bilan_id])
    finally:
        conn.close()


def set_bilan_archived(*, bilan_id: str, archived_at: datetime | None) -> None:
    """Archive un bilan (date d'archivage) ou le restaure (`None`). KeyError s'il est inconnu."""
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM bilans WHERE id = ?", [bilan_id]).fetchone() is None:
            raise KeyError(f"bilan {bilan_id}")
        conn.execute(
            "UPDATE bilans SET archived_at = ? WHERE id = ?",
            [_to_naive_utc(archived_at) if archived_at is not None else None, bilan_id],
        )
    finally:
        conn.close()


_FOLDER_SELECT = "id, created_at, name, parent_id"


def _folder_record(row) -> dict:
    folder_id, created_at, name, parent_id = row
    return {
        "id": folder_id, "created_at": _attach_utc(created_at).isoformat(), "name": name,
        "parent_id": parent_id,
    }


def _check_folder_name_free(
    conn, name: str, parent_id: str | None, *, except_id: str | None = None
) -> None:
    """ValueError si un autre dossier du même parent porte déjà ce nom (sans tenir compte des
    majuscules) : deux entreprises ne peuvent pas s'appeler pareil, mais deux entreprises peuvent
    chacune avoir un service « Production »."""
    taken = conn.execute(
        "SELECT id FROM bilan_folders "
        "WHERE lower(name) = lower(?) AND parent_id IS NOT DISTINCT FROM ?",
        [name, parent_id],
    ).fetchall()
    if any(row[0] != except_id for row in taken):
        raise ValueError(f"folder name {name!r} already used")


def list_bilan_folders() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT {_FOLDER_SELECT} FROM bilan_folders ORDER BY lower(name), id"
        ).fetchall()
    finally:
        conn.close()
    return [_folder_record(row) for row in rows]


def get_bilan_folder(folder_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {_FOLDER_SELECT} FROM bilan_folders WHERE id = ?", [folder_id]
        ).fetchone()
    finally:
        conn.close()
    return _folder_record(row) if row is not None else None


def create_bilan_folder(
    *, folder_id: str, created_at: datetime, name: str, parent_id: str | None = None
) -> None:
    """KeyError si le dossier parent est inconnu, ValueError si le nom est déjà pris dans ce
    parent."""
    conn = _connect()
    try:
        if parent_id is not None and conn.execute(
            "SELECT 1 FROM bilan_folders WHERE id = ?", [parent_id]
        ).fetchone() is None:
            raise KeyError(f"folder {parent_id}")
        _check_folder_name_free(conn, name, parent_id)
        conn.execute(
            "INSERT INTO bilan_folders (id, created_at, name, parent_id) VALUES (?, ?, ?, ?)",
            [folder_id, _to_naive_utc(created_at), name, parent_id],
        )
    finally:
        conn.close()


def rename_bilan_folder(*, folder_id: str, name: str) -> None:
    """KeyError si le dossier est inconnu, ValueError si le nom est déjà pris dans son parent."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT parent_id FROM bilan_folders WHERE id = ?", [folder_id]
        ).fetchone()
        if row is None:
            raise KeyError(f"folder {folder_id}")
        _check_folder_name_free(conn, name, row[0], except_id=folder_id)
        conn.execute("UPDATE bilan_folders SET name = ? WHERE id = ?", [name, folder_id])
    finally:
        conn.close()


class FolderCycleError(ValueError):
    """Un dossier ne peut pas être placé dans lui-même ni dans l'un de ses sous-dossiers."""


def move_bilan_folder(*, folder_id: str, parent_id: str | None) -> None:
    """Place un dossier dans un autre (`None` : à la racine). KeyError si l'un des deux est
    inconnu, FolderCycleError si la destination est le dossier ou l'un de ses descendants,
    ValueError si le nom est déjà pris dans la destination."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT name FROM bilan_folders WHERE id = ?", [folder_id]
        ).fetchone()
        if row is None:
            raise KeyError(f"folder {folder_id}")
        if parent_id is not None:
            # On remonte de la destination vers la racine : si on croise le dossier déplacé, c'est
            # un descendant (ou lui-même).
            current, seen = parent_id, set()
            while current is not None:
                if current == folder_id:
                    raise FolderCycleError(f"folder {folder_id} cannot go into itself")
                if current in seen:
                    break
                seen.add(current)
                parent = conn.execute(
                    "SELECT parent_id FROM bilan_folders WHERE id = ?", [current]
                ).fetchone()
                if parent is None:
                    raise KeyError(f"folder {parent_id}")
                current = parent[0]
        _check_folder_name_free(conn, row[0], parent_id, except_id=folder_id)
        conn.execute(
            "UPDATE bilan_folders SET parent_id = ? WHERE id = ?", [parent_id, folder_id]
        )
    finally:
        conn.close()


def delete_bilan_folder(folder_id: str) -> bool:
    """Supprime le dossier seulement : ses sous-dossiers et ses bilans montent d'un niveau, dans
    le dossier parent (ou à la racine). False si le dossier est inconnu. ValueError si un
    sous-dossier porte le même nom qu'un dossier du parent (il faut d'abord le renommer)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT parent_id FROM bilan_folders WHERE id = ?", [folder_id]
        ).fetchone()
        if row is None:
            return False
        parent_id = row[0]
        children = conn.execute(
            "SELECT id, name FROM bilan_folders WHERE parent_id = ?", [folder_id]
        ).fetchall()
        for child_id, child_name in children:
            _check_folder_name_free(conn, child_name, parent_id, except_id=child_id)
        conn.execute(
            "UPDATE bilan_folders SET parent_id = ? WHERE parent_id = ?", [parent_id, folder_id]
        )
        conn.execute("UPDATE bilans SET folder_id = ? WHERE folder_id = ?", [parent_id, folder_id])
        conn.execute("DELETE FROM bilan_folders WHERE id = ?", [folder_id])
    finally:
        conn.close()
    return True


def set_bilan_folder(*, bilan_id: str, folder_id: str | None) -> None:
    """Range un bilan dans un dossier (`None` : sans dossier). KeyError si le bilan ou le dossier
    est inconnu."""
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM bilans WHERE id = ?", [bilan_id]).fetchone() is None:
            raise KeyError(f"bilan {bilan_id}")
        if folder_id is not None and conn.execute(
            "SELECT 1 FROM bilan_folders WHERE id = ?", [folder_id]
        ).fetchone() is None:
            raise KeyError(f"folder {folder_id}")
        conn.execute("UPDATE bilans SET folder_id = ? WHERE id = ?", [folder_id, bilan_id])
    finally:
        conn.close()


def get_program_settings(bilan_id: str) -> dict:
    """Réglages du programme d'étirements du bilan : `size` (None : valeur par défaut) et
    `exercise_ids` (None : programme automatique). KeyError si le bilan est inconnu."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT program_size, program_selection FROM bilans WHERE id = ?", [bilan_id]
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise KeyError(f"bilan {bilan_id}")
    return {"size": row[0], "exercise_ids": json.loads(row[1]) if row[1] is not None else None}


def set_program_settings(
    *, bilan_id: str, size: int | None, exercise_ids: list[str] | None
) -> None:
    """Enregistre les réglages du programme du bilan. KeyError si le bilan est inconnu."""
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM bilans WHERE id = ?", [bilan_id]).fetchone() is None:
            raise KeyError(f"bilan {bilan_id}")
        conn.execute(
            "UPDATE bilans SET program_size = ?, program_selection = ? WHERE id = ?",
            [size, json.dumps(exercise_ids) if exercise_ids is not None else None, bilan_id],
        )
    finally:
        conn.close()


def delete_bilan(bilan_id: str) -> bool:
    """Supprime définitivement un bilan, ses fiches d'activité et ses rattachements de vidéos.
    Les analyses (vidéos) restent : elles existent hors du bilan. False si le bilan est inconnu."""
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM bilans WHERE id = ?", [bilan_id]).fetchone() is None:
            return False
        conn.execute("DELETE FROM bilan_tasks WHERE bilan_id = ?", [bilan_id])
        conn.execute("DELETE FROM bilan_analyses WHERE bilan_id = ?", [bilan_id])
        conn.execute("DELETE FROM bilans WHERE id = ?", [bilan_id])
    finally:
        conn.close()
    return True


def list_bilans(*, archived: bool = False) -> list[dict]:
    """Bilans actifs, ou archivés si `archived` : les plus récents d'abord."""
    conn = _connect()
    try:
        condition = "IS NOT NULL" if archived else "IS NULL"
        rows = conn.execute(
            f"SELECT {', '.join(_BILAN_COLUMNS)} FROM bilans WHERE archived_at {condition} "
            "ORDER BY created_at DESC, id"
        ).fetchall()
    finally:
        conn.close()
    return [_bilan_record(row) for row in rows]


def get_frame_scores(analysis_id: str) -> list[dict] | None:
    """Sous-scores par frame nécessaires au recalcul d'un score pour un autre
    poids (voir rescore.py)."""
    conn = _connect()
    try:
        exists = conn.execute(
            "SELECT 1 FROM analyses WHERE id = ?", [analysis_id]
        ).fetchone()
        if exists is None:
            return None
        columns = [
            "frame_index", "timestamp_seconds", "detected",
            "posture_score_a", "posture_score_b", "muscle_use_score",
        ]
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM analysis_frames "
            "WHERE analysis_id = ? ORDER BY frame_index",
            [analysis_id],
        ).fetchall()
    finally:
        conn.close()

    return [dict(zip(columns, row)) for row in rows]


def update_load(
    analysis_id: str,
    *,
    load: dict,
    effective_load_kg: float,
    frame_scores: list[dict],
    summary: dict,
    score_range: dict | None,
) -> None:
    """Enregistre le poids saisi et réécrit, dans une seule transaction, les
    scores par frame et le résumé de l'analyse (valeurs du cas défavorable,
    voir le plan de la Tranche 2). `original_load_kg` (poids utilisé pour le
    badge incrusté dans la vidéo annotée) n'est fixé qu'à la première mise à
    jour. KeyError si l'analyse est inconnue."""
    conn = _connect()
    try:
        conn.begin()
        try:
            row = conn.execute(
                "SELECT load_kg FROM analyses WHERE id = ?", [analysis_id]
            ).fetchone()
            if row is None:
                raise KeyError(f"analysis {analysis_id}")
            analysis_load_kg = row[0]

            previous = conn.execute(
                "SELECT original_load_kg FROM analysis_loads WHERE analysis_id = ?",
                [analysis_id],
            ).fetchone()
            original_load_kg = previous[0] if previous is not None else analysis_load_kg

            conn.execute(
                """
                INSERT INTO analysis_loads (
                    analysis_id, kind, kg, kg_min, kg_max, original_load_kg, score_range,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (analysis_id) DO UPDATE SET
                    kind = excluded.kind, kg = excluded.kg, kg_min = excluded.kg_min,
                    kg_max = excluded.kg_max, score_range = excluded.score_range,
                    updated_at = excluded.updated_at
                """,
                [
                    analysis_id, load["kind"], load["kg"], load["kg_min"], load["kg_max"],
                    original_load_kg,
                    json.dumps(score_range, ensure_ascii=False) if score_range is not None else None,
                    _to_naive_utc(datetime.now(timezone.utc)),
                ],
            )

            if frame_scores:
                conn.executemany(
                    "UPDATE analysis_frames SET force_load_score = ?, final_score = ?, "
                    "action_level = ? WHERE analysis_id = ? AND frame_index = ?",
                    [
                        [
                            frame["force_load_score"], frame["final_score"],
                            frame["action_level"], analysis_id, frame["frame_index"],
                        ]
                        for frame in frame_scores
                    ],
                )

            conn.execute(
                "UPDATE analyses SET load_kg = ?, max_score = ?, average_score = ?, "
                "time_by_action_level = ? WHERE id = ?",
                [
                    effective_load_kg, summary["max_score"], summary["average_score"],
                    json.dumps(summary["time_by_action_level"], ensure_ascii=False),
                    analysis_id,
                ],
            )
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        conn.close()


def save_library_share(
    *,
    token: str,
    created_at: datetime,
    recipient_email: str,
    practitioner_name: str | None,
    message: str | None,
    items: list[dict],
    email_status: str,
) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO library_shares (
                token, created_at, recipient_email, practitioner_name, message, items_json,
                email_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                token, _to_naive_utc(created_at), recipient_email, practitioner_name, message,
                json.dumps(items), email_status,
            ],
        )
    finally:
        conn.close()


def get_library_share(token: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT created_at, practitioner_name, message, items_json
            FROM library_shares WHERE token = ?
            """,
            [token],
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "created_at": _attach_utc(row[0]).isoformat(),
        "practitioner_name": row[1],
        "message": row[2],
        "items": json.loads(row[3]),
    }
