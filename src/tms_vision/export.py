"""Export CSV par frame et résumé JSON de fin d'analyse."""
import csv
import json
from dataclasses import dataclass

from tms_vision.angles import JointAngles
from tms_vision.rula.scoring import RulaScore

CSV_FIELDS = [
    "frame_index", "timestamp_seconds", "detected",
    "neck_flexion_deg", "trunk_flexion_deg", "upper_arm_flexion_deg",
    "lower_arm_angle_deg", "wrist_flexion_deg",
    "upper_arm", "lower_arm", "wrist", "neck", "trunk", "legs",
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
    def __init__(self, csv_path: str, summary_json_path: str):
        self._csv_path = csv_path
        self._summary_json_path = summary_json_path
        self._records: list[FrameRecord] = []

    def add_frame(self, record: FrameRecord) -> None:
        self._records.append(record)

    def _row_for(self, record: FrameRecord) -> dict:
        row = {field: "" for field in CSV_FIELDS}
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
            row["neck"] = record.score.neck
            row["trunk"] = record.score.trunk
            row["legs"] = record.score.legs
            row["muscle_use_score"] = record.score.muscle_use_score
            row["force_load_score"] = record.score.force_load_score
            row["final_score"] = record.score.final_score
            row["action_level"] = record.score.action_level
        return row

    def _summary(self) -> dict:
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
        for index, record in enumerate(detected):
            # Find next frame (detected or not) in self._records
            next_timestamp = None
            for r in self._records:
                if r.frame_index > record.frame_index:
                    next_timestamp = r.timestamp_seconds
                    break

            # If no next frame found, use 1.0 only if single detected frame, else 0.0
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

    def finalize(self) -> None:
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for record in self._records:
                writer.writerow(self._row_for(record))

        with open(self._summary_json_path, "w") as f:
            json.dump(self._summary(), f, indent=2, ensure_ascii=False)
