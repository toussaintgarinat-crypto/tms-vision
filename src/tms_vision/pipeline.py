"""Pipeline Phase 1 réutilisable : capture -> pose -> angles -> score RULA ->
overlay vidéo + export CSV/JSON.

Extrait de cli.py pour être appelable aussi bien depuis la CLI que depuis
l'API FastAPI (api.py), sans dupliquer la logique (voir
docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md).
"""
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from tms_vision.capture import FrameSource
from tms_vision.pose_estimation import PoseEstimator
from tms_vision.angles import compute_joint_angles
from tms_vision.rula.scoring import compute_rula_score, detect_muscle_use
from tms_vision.overlay import draw_overlay
from tms_vision.export import FrameRecord, ResultsExporter

WRIST_TWIST_CODES = {"normal": 1, "extreme": 2}


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
    video_path: Path | None = None
    csv_path: Path | None = None
    summary_json_path: Path | None = None


def analyze_video(
    source: str, side: str, load_kg: float, wrist_twist: str, output_dir: str
) -> AnalysisResult:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"

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
            # Baseline = moyenne des frames PRÉCÉDENTES uniquement (pas la
            # frame courante) ; sur la toute première frame détectée, aucune
            # donnée antérieure n'existe -> None (repli sur le comportement
            # historique pour cette frame-là seulement).
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

    # `frames` est garanti non vide ici : le garde-fou `if not frames: ...
    # return` ci-dessus a déjà court-circuité la fonction sinon.
    height, width = frames[0].image.shape[:2]
    # "mp4v" (MPEG-4 Part 2) n'est décodable par aucun navigateur (Chromium/
    # Firefox renvoient MediaError code 4 sur le <video> de web/app/page.tsx).
    # "avc1" (H.264/AVC) est vérifié disponible dans ce build d'OpenCV (FFMPEG
    # avec fallback automatique vers le tag avc1, testé avec isOpened() +
    # ffprobe + lecture réelle dans Chromium via Playwright) et reste dans un
    # conteneur .mp4 classique.
    video_path = output_path / f"{run_id}_annotated.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"avc1"), frame_source.fps() or 30.0, (width, height)
    )

    csv_path = output_path / f"{run_id}_frames.csv"
    summary_json_path = output_path / f"{run_id}_summary.json"
    exporter = ResultsExporter(str(csv_path), str(summary_json_path))

    for frame, pose_result, angles in per_frame_angles:
        score = None
        if angles is not None:
            score = compute_rula_score(
                angles, wrist_twist=wrist_twist_code, load_kg=load_kg, muscle_use_score=muscle_use_score
            )
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

    writer.release()
    exporter.finalize()

    return AnalysisResult(
        empty=False, video_path=video_path, csv_path=csv_path, summary_json_path=summary_json_path
    )
