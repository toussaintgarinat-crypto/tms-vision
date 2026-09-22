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
