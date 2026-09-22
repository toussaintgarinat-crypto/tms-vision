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


def test_get_analysis_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    assert storage.get_analysis("does-not-exist") is None


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
