from datetime import datetime, timezone

from tms_vision import storage
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


def test_save_analysis_round_trips_created_at_as_exact_utc_instant(tmp_path, monkeypatch):
    """Régression pour la revue finale de tranche : created_at doit revenir
    exactement à l'instant UTC écrit, suffixe +00:00 inclus -- pas décalé de
    l'heure locale du serveur DuckDB (voir storage._to_naive_utc/_attach_utc)."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    summary = {
        "frame_count": 0, "detected_frame_count": 0, "max_score": 0,
        "average_score": 0.0, "time_by_action_level": {},
    }
    written = datetime(2026, 9, 22, 13, 45, 30, tzinfo=timezone.utc)
    storage.save_analysis(
        analysis_id="tz-1", created_at=written, side="right", load_kg=0.0,
        wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=[],
    )

    analysis = storage.get_analysis("tz-1")

    assert analysis["created_at"] == "2026-09-22T13:45:30+00:00"
    assert datetime.fromisoformat(analysis["created_at"]) == written


def test_get_analysis_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    assert storage.get_analysis("does-not-exist") is None


def test_analysis_frames_columns_match_frame_value_columns(tmp_path, monkeypatch):
    """Garde-fou anti-dérive de schéma : FRAME_VALUE_COLUMNS (dérivé de
    export.CSV_FIELDS) doit rester exactement synchronisé avec les colonnes
    réellement présentes dans analysis_frames (DDL maintenue à la main) --
    sinon l'INSERT généré par save_analysis référence une colonne
    inexistante, sans que rien ne le détecte avant une erreur en
    production."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    conn = storage._connect()
    try:
        actual_columns = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'analysis_frames'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert set(storage.FRAME_VALUE_COLUMNS) | {"analysis_id"} == actual_columns


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
    assert [
        r["id"]
        for r in storage.list_analyses(worker_label="Marie D.", poste_label="Emballage")
    ] == ["a"]
    assert storage.list_analyses(worker_label="Marie D.", poste_label="Poste inexistant") == []


def test_list_analyses_filters_by_date_range(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    _save("a", datetime(2026, 9, 20, tzinfo=timezone.utc))
    _save("b", datetime(2026, 9, 22, tzinfo=timezone.utc))

    results = storage.list_analyses(
        since=datetime(2026, 9, 21, tzinfo=timezone.utc),
        until=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )

    assert [r["id"] for r in results] == ["b"]


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


def test_frames_csv_text_is_header_only_when_analysis_has_zero_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    summary = {
        "frame_count": 0, "detected_frame_count": 0, "max_score": 0,
        "average_score": 0.0, "time_by_action_level": {},
    }
    storage.save_analysis(
        analysis_id="csv-empty", created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=[],
    )

    csv_text = storage.frames_csv_text("csv-empty")

    assert csv_text is not None
    lines = csv_text.strip("\r\n").splitlines()
    assert lines == [",".join(CSV_FIELDS)]


def test_get_frame_segments_returns_ordered_rows_with_segment_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    summary = {
        "frame_count": 2, "detected_frame_count": 2, "max_score": 1,
        "average_score": 1.0, "time_by_action_level": {"acceptable": 2.0},
    }
    row0 = _frame_row(frame_index=0, timestamp_seconds=0.0)
    row0["neck_segment_action_level"] = "acceptable"
    row0["trunk_segment_action_level"] = "changement_immediat"
    row0["upper_arm_segment_action_level"] = "acceptable"
    row0["lower_arm_segment_action_level"] = "acceptable"
    row1 = _frame_row(frame_index=1, timestamp_seconds=1.0)
    row1["neck_segment_action_level"] = "investigation_recommandee"
    row1["trunk_segment_action_level"] = "acceptable"
    row1["upper_arm_segment_action_level"] = "acceptable"
    row1["lower_arm_segment_action_level"] = "acceptable"

    storage.save_analysis(
        analysis_id="seg-1", created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=[row0, row1],
    )

    frames = storage.get_frame_segments("seg-1")

    assert frames is not None
    assert len(frames) == 2
    assert frames[0]["frame_index"] == 0
    assert frames[0]["timestamp_seconds"] == 0.0
    assert frames[0]["trunk_segment_action_level"] == "changement_immediat"
    assert frames[1]["frame_index"] == 1
    assert frames[1]["neck_segment_action_level"] == "investigation_recommandee"
    assert set(frames[0].keys()) == {"frame_index", "timestamp_seconds", *storage.SEGMENT_COLUMNS}


def test_get_frame_segments_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    assert storage.get_frame_segments("does-not-exist") is None
