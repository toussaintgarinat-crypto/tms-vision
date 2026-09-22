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
