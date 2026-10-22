from datetime import datetime, timezone

import pytest

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
    row["hand_segment_action_level"] = "investigation_recommandee"
    row["foot_segment_action_level"] = None
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

    assert {
        "analyses", "analysis_frames", "bilans", "bilan_analyses", "bilan_tasks", "analysis_loads",
    } <= table_names


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


def test_get_frame_angles_returns_ordered_angles_and_segment_levels(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    summary = {
        "frame_count": 2, "detected_frame_count": 1, "max_score": 1,
        "average_score": 1.0, "time_by_action_level": {"acceptable": 1.0},
    }
    row0 = _frame_row(
        frame_index=0, timestamp_seconds=0.0, neck_flexion_deg=12.5, trunk_flexion_deg=30.0,
        upper_arm_flexion_deg=45.0, lower_arm_angle_deg=80.0,
    )
    row1 = _frame_row(
        frame_index=1, timestamp_seconds=1.0, detected=False, neck_flexion_deg=None,
        trunk_flexion_deg=None, upper_arm_flexion_deg=None, lower_arm_angle_deg=None,
    )
    storage.save_analysis(
        analysis_id="ang-1", created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=[row1, row0],
    )

    frames = storage.get_frame_angles("ang-1")

    assert frames is not None
    assert [f["frame_index"] for f in frames] == [0, 1]
    assert frames[0]["detected"] is True
    assert frames[0]["neck_flexion_deg"] == 12.5
    assert frames[0]["trunk_flexion_deg"] == 30.0
    assert frames[0]["upper_arm_flexion_deg"] == 45.0
    assert frames[0]["lower_arm_angle_deg"] == 80.0
    assert frames[0]["trunk_segment_action_level"] == "investigation_recommandee"
    assert frames[1]["detected"] is False
    assert frames[1]["trunk_flexion_deg"] is None
    assert set(frames[0].keys()) == {
        "frame_index", "timestamp_seconds", "detected", *storage.ANGLE_COLUMNS,
        *storage.SEGMENT_COLUMNS,
    }


def test_get_frame_angles_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    assert storage.get_frame_angles("does-not-exist") is None


def _save_minimal_analysis(analysis_id):
    storage.save_analysis(
        analysis_id=analysis_id, created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary={
            "frame_count": 0, "detected_frame_count": 0, "max_score": 0,
            "average_score": 0, "time_by_action_level": {},
        },
        video_bytes=b"x", pose3d_json="[]", frame_rows=[],
    )


def test_create_bilan_then_get_bilan_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    storage.create_bilan(
        bilan_id="b-1", created_at=datetime(2026, 10, 21, 8, 30, tzinfo=timezone.utc),
        label="Quai 3", workday_hours=9.0,
    )

    bilan = storage.get_bilan("b-1")

    assert bilan == {
        "id": "b-1", "created_at": "2026-10-21T08:30:00+00:00", "label": "Quai 3",
        "workday_hours": 9.0, "items": [], "tasks": [],
    }


def test_get_bilan_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    assert storage.get_bilan("nope") is None


def test_attach_analysis_adds_item_in_attachment_order(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_minimal_analysis("a-1")
    _save_minimal_analysis("a-2")
    storage.create_bilan(
        bilan_id="b-1", created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        label=None, workday_hours=9.0,
    )

    storage.attach_analysis(bilan_id="b-1", analysis_id="a-2", activity_hours=3.0, representative=False)
    storage.attach_analysis(bilan_id="b-1", analysis_id="a-1", activity_hours=5.0, representative=True)

    assert storage.get_bilan("b-1")["items"] == [
        {"analysis_id": "a-2", "activity_hours": 3.0, "representative": False},
        {"analysis_id": "a-1", "activity_hours": 5.0, "representative": True},
    ]


def test_attach_analysis_rejects_unknown_bilan_and_unknown_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_minimal_analysis("a-1")
    storage.create_bilan(
        bilan_id="b-1", created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        label=None, workday_hours=9.0,
    )

    with pytest.raises(KeyError):
        storage.attach_analysis(bilan_id="nope", analysis_id="a-1", activity_hours=1.0, representative=True)
    with pytest.raises(KeyError):
        storage.attach_analysis(bilan_id="b-1", analysis_id="nope", activity_hours=1.0, representative=True)


def test_attach_analysis_twice_to_same_bilan_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_minimal_analysis("a-1")
    storage.create_bilan(
        bilan_id="b-1", created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        label=None, workday_hours=9.0,
    )
    storage.attach_analysis(bilan_id="b-1", analysis_id="a-1", activity_hours=1.0, representative=True)

    with pytest.raises(ValueError):
        storage.attach_analysis(bilan_id="b-1", analysis_id="a-1", activity_hours=2.0, representative=True)


def test_same_analysis_can_belong_to_two_bilans(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_minimal_analysis("a-1")
    for bilan_id in ("b-1", "b-2"):
        storage.create_bilan(
            bilan_id=bilan_id, created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
            label=None, workday_hours=9.0,
        )
        storage.attach_analysis(bilan_id=bilan_id, analysis_id="a-1", activity_hours=1.0, representative=True)

    assert len(storage.get_bilan("b-1")["items"]) == 1
    assert len(storage.get_bilan("b-2")["items"]) == 1


def test_list_bilans_orders_most_recent_first_without_items(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    storage.create_bilan(
        bilan_id="old", created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        label="vieux", workday_hours=9.0,
    )
    storage.create_bilan(
        bilan_id="new", created_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        label="recent", workday_hours=7.0,
    )

    bilans = storage.list_bilans()

    assert [b["id"] for b in bilans] == ["new", "old"]
    assert "items" not in bilans[0]


def _scored_frame_row(index, final_score=3, level="investigation_recommandee"):
    row = _frame_row(frame_index=index, timestamp_seconds=float(index))
    row.update(
        posture_score_a=3, posture_score_b=4, muscle_use_score=1,
        force_load_score=0, final_score=final_score, action_level=level,
    )
    return row


def _save_scored_analysis(analysis_id="load-1", load_kg=0.0, frame_count=3):
    storage.save_analysis(
        analysis_id=analysis_id, created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        side="right", load_kg=load_kg, wrist_twist="normal", worker_label=None, poste_label=None,
        summary={
            "frame_count": frame_count, "detected_frame_count": frame_count, "max_score": 3,
            "average_score": 3.0, "time_by_action_level": {"investigation_recommandee": 2.0},
        },
        video_bytes=b"x", pose3d_json="[]",
        frame_rows=[_scored_frame_row(i) for i in range(frame_count)],
    )


def _rescored(index, final_score, level, force=2):
    return {
        "frame_index": index, "force_load_score": force, "final_score": final_score,
        "action_level": level,
    }


_NEW_SUMMARY = {
    "frame_count": 3, "detected_frame_count": 3, "max_score": 6, "average_score": 6.0,
    "time_by_action_level": {"investigation_et_changement_bientot": 2.0},
}
_EXACT_15 = {"kind": "exact", "kg": 15.0, "kg_min": None, "kg_max": None}


def _update_to_15kg(analysis_id="load-1", score_range=None):
    storage.update_load(
        analysis_id, load=_EXACT_15, effective_load_kg=15.0,
        frame_scores=[_rescored(i, 6, "investigation_et_changement_bientot") for i in range(3)],
        summary=_NEW_SUMMARY, score_range=score_range,
    )


def test_update_load_works_when_the_analysis_is_attached_to_a_bilan(tmp_path, monkeypatch):
    # Risque DuckDB : mettre a jour une ligne parente referencee par des cles etrangeres
    # (analysis_frames, bilan_analyses) doit rester possible.
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_scored_analysis()
    storage.create_bilan(
        bilan_id="b-1", created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        label=None, workday_hours=9.0,
    )
    storage.attach_analysis(bilan_id="b-1", analysis_id="load-1", activity_hours=2.0, representative=True)

    _update_to_15kg()

    assert storage.get_analysis("load-1")["max_score"] == 6
    assert storage.get_bilan("b-1")["items"][0]["analysis_id"] == "load-1"


def test_get_analysis_exposes_legacy_load_as_exact(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_scored_analysis(load_kg=7.5)

    assert storage.get_analysis("load-1")["load"] == {
        "kind": "exact", "kg": 7.5, "kg_min": None, "kg_max": None,
        "original_load_kg": 7.5, "score_range": None,
    }


def test_update_load_rewrites_frames_summary_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_scored_analysis(load_kg=0.0)

    _update_to_15kg()

    analysis = storage.get_analysis("load-1")
    assert analysis["max_score"] == 6
    assert analysis["average_score"] == 6.0
    assert analysis["load_kg"] == 15.0
    assert analysis["time_by_action_level"] == {"investigation_et_changement_bientot": 2.0}
    assert analysis["load"] == {
        "kind": "exact", "kg": 15.0, "kg_min": None, "kg_max": None,
        "original_load_kg": 0.0, "score_range": None,
    }
    csv_rows = storage.frames_csv_text("load-1").splitlines()
    header = csv_rows[0].split(",")
    first = dict(zip(header, csv_rows[1].split(",")))
    assert first["force_load_score"] == "2"
    assert first["final_score"] == "6"
    assert first["action_level"] == "investigation_et_changement_bientot"
    # Les sous-scores de posture ne bougent pas.
    assert first["posture_score_a"] == "3"
    assert first["posture_score_b"] == "4"


def test_update_load_keeps_the_first_original_load_on_later_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_scored_analysis(load_kg=3.0)
    _update_to_15kg()

    storage.update_load(
        "load-1", load={"kind": "range", "kg": None, "kg_min": 8.0, "kg_max": 12.0},
        effective_load_kg=12.0,
        frame_scores=[_rescored(i, 5, "investigation_et_changement_bientot") for i in range(3)],
        summary={**_NEW_SUMMARY, "max_score": 5, "average_score": 5.0},
        score_range={"low": {"max_score": 4, "average_score": 4.0},
                     "high": {"max_score": 5, "average_score": 5.0}},
    )

    analysis = storage.get_analysis("load-1")
    assert analysis["load_kg"] == 12.0
    assert analysis["load"]["kind"] == "range"
    assert (analysis["load"]["kg_min"], analysis["load"]["kg_max"]) == (8.0, 12.0)
    assert analysis["load"]["original_load_kg"] == 3.0
    assert analysis["load"]["score_range"]["low"]["max_score"] == 4


def test_update_load_unknown_analysis_raises_key_error(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    with pytest.raises(KeyError):
        storage.update_load(
            "nope", load=_EXACT_15, effective_load_kg=15.0, frame_scores=[],
            summary=_NEW_SUMMARY, score_range=None,
        )


def test_update_load_rolls_back_everything_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_scored_analysis(load_kg=0.0)
    bad_scores = [_rescored(0, 6, "investigation_et_changement_bientot"), {"frame_index": 1}]

    with pytest.raises(KeyError):
        storage.update_load(
            "load-1", load=_EXACT_15, effective_load_kg=15.0, frame_scores=bad_scores,
            summary=_NEW_SUMMARY, score_range=None,
        )

    analysis = storage.get_analysis("load-1")
    assert analysis["max_score"] == 3
    assert analysis["load_kg"] == 0.0
    assert analysis["load"]["kg"] == 0.0  # toujours la valeur legacy : aucune ligne analysis_loads
    first_row = storage.frames_csv_text("load-1").splitlines()[1].split(",")
    assert "6" not in first_row[storage.CSV_FIELDS.index("final_score")]


def test_get_frame_scores_returns_the_inputs_needed_for_rescoring(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_scored_analysis(frame_count=2)

    frames = storage.get_frame_scores("load-1")

    assert frames == [
        {"frame_index": 0, "timestamp_seconds": 0.0, "detected": True,
         "posture_score_a": 3, "posture_score_b": 4, "muscle_use_score": 1},
        {"frame_index": 1, "timestamp_seconds": 1.0, "detected": True,
         "posture_score_a": 3, "posture_score_b": 4, "muscle_use_score": 1},
    ]


def test_get_frame_scores_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    assert storage.get_frame_scores("nope") is None


def test_update_load_rolls_back_frame_updates_when_the_summary_write_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_scored_analysis(load_kg=0.0)

    # Les frames sont ecrites AVANT le resume : un resume incomplet fait echouer
    # la derniere etape, apres que les frames et analysis_loads ont ete modifies.
    with pytest.raises(KeyError):
        storage.update_load(
            "load-1", load=_EXACT_15, effective_load_kg=15.0,
            frame_scores=[_rescored(i, 6, "investigation_et_changement_bientot") for i in range(3)],
            summary={}, score_range=None,
        )

    header = storage.frames_csv_text("load-1").splitlines()[0].split(",")
    for line in storage.frames_csv_text("load-1").splitlines()[1:]:
        values = dict(zip(header, line.split(",")))
        assert values["final_score"] == "3"
        assert values["force_load_score"] == "0"
    assert storage.get_analysis("load-1")["load"]["original_load_kg"] == 0.0
    assert storage.get_analysis("load-1")["load"]["kind"] == "exact"


def test_connect_adds_hand_and_foot_columns_to_a_database_created_before_they_existed(
    tmp_path, monkeypatch
):
    import duckdb

    db_path = tmp_path / "old.duckdb"
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    old = duckdb.connect(str(db_path))
    old_schema = storage.CREATE_ANALYSIS_FRAMES_TABLE
    for column in ("ankle_flexion_deg DOUBLE,", "finger_curl_deg DOUBLE,",
                   "hand_segment_action_level VARCHAR,", "foot_segment_action_level VARCHAR,"):
        old_schema = old_schema.replace(column, "")
    old.execute(storage.CREATE_ANALYSES_TABLE)
    old.execute(old_schema)
    old.close()

    conn = storage._connect()
    try:
        columns = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'analysis_frames'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"ankle_flexion_deg", "finger_curl_deg", "hand_segment_action_level",
            "foot_segment_action_level"} <= columns


def _bilan_with_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    _save_minimal_analysis("a-1")
    storage.create_bilan(
        bilan_id="b-1", created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        label=None, workday_hours=9.0,
    )
    storage.attach_analysis(bilan_id="b-1", analysis_id="a-1", activity_hours=5.0, representative=True)


def _task_fields(**overrides):
    fields = {
        "name": "Peindre un plafond", "zones": ["neck", "upper_arm"], "activity_hours": 2.0,
        "time_slots": [{"start": "08:00", "end": "10:00"}], "days_per_week": 5.0,
        "cycles_per_minute": 12.0, "cycle_seconds": 5.0, "static_seconds": 30.0,
        "load_kg": 2.0, "analysis_id": None, "source": "practitioner", "notes": "bras levés",
    }
    return {**fields, **overrides}


def test_bilan_task_create_read_update_delete(tmp_path, monkeypatch):
    _bilan_with_analysis(tmp_path, monkeypatch)
    when = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)

    storage.create_bilan_task(task_id="t-1", bilan_id="b-1", created_at=when, task=_task_fields())

    [task] = storage.get_bilan("b-1")["tasks"]
    assert task == {
        "id": "t-1", "bilan_id": "b-1", "created_at": "2026-10-22T09:00:00+00:00",
        **_task_fields(),
    }

    storage.update_bilan_task(
        task_id="t-1", bilan_id="b-1",
        task=_task_fields(name="Saisie", time_slots=None, cycles_per_minute=None,
                          analysis_id="a-1"),
    )
    [updated] = storage.list_bilan_tasks("b-1")
    assert updated["name"] == "Saisie"
    assert updated["time_slots"] is None
    assert updated["cycles_per_minute"] is None
    assert updated["analysis_id"] == "a-1"

    storage.delete_bilan_task(task_id="t-1", bilan_id="b-1")
    assert storage.list_bilan_tasks("b-1") == []


def test_bilan_task_rejects_unknown_bilan_task_and_foreign_analysis(tmp_path, monkeypatch):
    _bilan_with_analysis(tmp_path, monkeypatch)
    when = datetime(2026, 10, 22, tzinfo=timezone.utc)

    with pytest.raises(KeyError):
        storage.create_bilan_task(task_id="t", bilan_id="nope", created_at=when, task=_task_fields())
    with pytest.raises(ValueError):
        storage.create_bilan_task(
            task_id="t", bilan_id="b-1", created_at=when,
            task=_task_fields(analysis_id="inconnue"),
        )
    with pytest.raises(KeyError):
        storage.update_bilan_task(task_id="nope", bilan_id="b-1", task=_task_fields())
    with pytest.raises(KeyError):
        storage.delete_bilan_task(task_id="nope", bilan_id="b-1")
