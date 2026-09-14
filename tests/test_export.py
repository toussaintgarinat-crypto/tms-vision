import csv
import json

from tms_vision.angles import JointAngles
from tms_vision.rula.scoring import RulaScore
from tms_vision.export import FrameRecord, ResultsExporter


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


def test_export_writes_csv_row_per_frame_and_summary_json(tmp_path):
    csv_path = tmp_path / "frames.csv"
    summary_path = tmp_path / "summary.json"
    exporter = ResultsExporter(str(csv_path), str(summary_path))

    exporter.add_frame(FrameRecord(0, 0.0, True, _angles(), _score(1, "acceptable")))
    exporter.add_frame(FrameRecord(1, 1.0, True, _angles(), _score(7, "changement_immediat")))
    exporter.add_frame(FrameRecord(2, 2.0, False, None, None))
    exporter.finalize()

    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert rows[0]["detected"] == "True"
    assert rows[0]["final_score"] == "1"
    assert rows[2]["detected"] == "False"
    assert rows[2]["final_score"] == ""
    assert rows[0]["posture_score_a"] == "1"
    assert rows[0]["posture_score_b"] == "1"
    assert rows[0]["wrist_twist"] == "1"
    assert rows[2]["posture_score_a"] == ""

    with open(summary_path) as f:
        summary = json.load(f)
    assert summary["frame_count"] == 3
    assert summary["detected_frame_count"] == 2
    assert summary["max_score"] == 7
    assert summary["average_score"] == 4.0
    assert summary["time_by_action_level"]["acceptable"] == 1.0
    assert summary["time_by_action_level"]["changement_immediat"] == 1.0


def test_export_with_no_detected_frames_gives_zeroed_summary(tmp_path):
    csv_path = tmp_path / "frames.csv"
    summary_path = tmp_path / "summary.json"
    exporter = ResultsExporter(str(csv_path), str(summary_path))
    exporter.add_frame(FrameRecord(0, 0.0, False, None, None))
    exporter.finalize()

    with open(summary_path) as f:
        summary = json.load(f)
    assert summary["max_score"] == 0
    assert summary["average_score"] == 0
    assert summary["time_by_action_level"] == {}
