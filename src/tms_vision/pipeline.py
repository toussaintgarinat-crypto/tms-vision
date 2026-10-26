"""Pipeline Phase 1 réutilisable : capture -> pose -> angles -> score RULA ->
overlay vidéo, entièrement en mémoire (voir
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md). Le seul
fichier écrit sur disque est un fichier temporaire imposé par
cv2.VideoWriter (qui n'accepte pas d'écrire directement en mémoire) --
supprimé avant que la fonction ne retourne. Persister le résultat (fichiers
locaux pour la CLI, DuckDB pour l'API web) est la responsabilité de
l'appelant (tms_vision.cli, tms_vision.api / tms_vision.storage).
"""
import os
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

import cv2

from tms_vision.capture import FrameSource
from tms_vision.face_blur import FaceAnonymizer, default_face_detector
from tms_vision.extremities import (
    classify_foot, classify_hand, extremity_action_level, load_extremity_thresholds,
)
from tms_vision.hand_estimation import HandEstimator
from tms_vision.pose_estimation import PoseEstimator
from tms_vision.angles import compute_ankle_flexion, compute_joint_angles
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


def _h264_with_ffmpeg(video_path: Path, ffmpeg: str) -> None:
    """Réencode la vidéo en H.264 lisible par les navigateurs, sur place. Sert à l'application de
    bureau : les builds d'OpenCV pour Windows et macOS n'embarquent pas toujours l'encodeur « avc1 »,
    alors que ffmpeg (fourni avec l'application, voir desktop.py) sait toujours le faire."""
    encoded = video_path.with_suffix(".h264.mp4")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(video_path), "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(encoded)],
            check=True, capture_output=True,
        )
        encoded.replace(video_path)
    finally:
        encoded.unlink(missing_ok=True)


def analyze_video(
    source: str, side: str, load_kg: float, wrist_twist: str, anonymize: bool = True
) -> AnalysisResult:
    """`anonymize` : pixelliser les têtes de la vidéo annotée avant son écriture (voir
    face_blur.py). Actif par défaut ; ni l'API ni la CLI ne le désactivent, il n'existe que pour
    les tests."""
    wrist_twist_code = WRIST_TWIST_CODES[wrist_twist]

    frame_source = FrameSource(source)
    estimator = PoseEstimator()
    hand_estimator = HandEstimator()
    extremity_thresholds = load_extremity_thresholds()

    per_frame_angles = []
    posture_load_history: list[tuple[float, float]] = []
    shoulder_key = f"{side.upper()}_SHOULDER"
    shoulder_y_baseline = _RunningMean()
    image_shape = None

    def estimate(frame):
        pose_result = estimator.process(frame.image)
        angles = None
        if pose_result.landmarks is not None:
            angles = compute_joint_angles(
                pose_result.landmarks, side=side, shoulder_baseline_y=shoulder_y_baseline.value
            )
            if angles is not None:
                angles = replace(
                    angles,
                    ankle_flexion_deg=(
                        compute_ankle_flexion(pose_result.world_landmarks, side)
                        if pose_result.world_landmarks is not None else None
                    ),
                    finger_curl_deg=hand_estimator.finger_curl(
                        frame.image, pose_result.landmarks.get(f"{side.upper()}_WRIST")
                    ),
                )
            current_shoulder = pose_result.landmarks.get(shoulder_key)
            if current_shoulder is not None:
                shoulder_y_baseline.update(current_shoulder.y)
        if angles is not None:
            posture_load = angles.trunk_flexion_deg + angles.upper_arm_flexion_deg
            posture_load_history.append((frame.timestamp_seconds, posture_load))
        return pose_result, angles

    # Un fichier vidéo est lu deux fois (mesure, puis vidéo annotée) au lieu de garder toutes ses
    # images en mémoire : la mémoire ne dépend plus de la durée. La webcam ne se relit pas : ses
    # images sont gardées (clip court).
    reread = source != "webcam"
    captured = []
    try:
        for frame in frame_source:
            if image_shape is None:
                image_shape = frame.image.shape[:2]
            if reread:
                pose_result, angles = estimate(frame)
                per_frame_angles.append((replace(frame, image=None), pose_result, angles))
            else:
                captured.append(frame)
    except KeyboardInterrupt:
        print("\nCapture interrompue par l'utilisateur, traitement des frames déjà capturées...")
    finally:
        frame_source.release()

    for frame in captured:
        pose_result, angles = estimate(frame)
        per_frame_angles.append((frame, pose_result, angles))

    if not per_frame_angles:
        print("Aucune frame capturée, rien à analyser.", file=sys.stderr)
        estimator.close()
        hand_estimator.close()
        return AnalysisResult(empty=True)

    estimator.close()
    hand_estimator.close()

    muscle_use_score = 1 if detect_muscle_use(posture_load_history) else 0

    height, width = image_shape
    exporter = ResultsExporter()

    raw_world_landmarks = [pose_result.world_landmarks for _, pose_result, _ in per_frame_angles]
    smoothed_world_landmarks = smooth_world_landmarks(raw_world_landmarks)
    pose3d_records: list[Pose3DFrameRecord] = []

    # Les images brutes (visages nets) ne vivent qu'en mémoire : seule l'image pixellisée est
    # écrite dans la vidéo annotée, donc jamais persistée.
    anonymizer = (
        FaceAnonymizer(fps=frame_source.fps() or 30.0, detector=default_face_detector())
        if anonymize else None
    )

    second_source = FrameSource(source) if reread else None
    tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    video_tmp_path = Path(tmp_video.name)
    tmp_video.close()
    try:
        # "avc1" (H.264/AVC) est lisible par les navigateurs (Chromium/
        # Firefox), contrairement à "mp4v" -- voir commit 9d6a9da et
        # test_analyze_video_writes_browser_playable_h264_not_mp4v.
        # Application de bureau (TMS_FFMPEG = chemin de ffmpeg) : écriture en "mp4v" puis réencodage
        # en H.264 par ffmpeg, car OpenCV n'y embarque pas toujours l'encodeur "avc1".
        ffmpeg = os.environ.get("TMS_FFMPEG", "").strip()
        writer = cv2.VideoWriter(
            str(video_tmp_path), cv2.VideoWriter_fourcc(*("mp4v" if ffmpeg else "avc1")),
            frame_source.fps() or 30.0, (width, height),
        )
        if not writer.isOpened():
            raise RuntimeError(
                "Impossible d'écrire la vidéo annotée : l'encodeur vidéo H.264 est indisponible "
                "sur cet ordinateur."
            )
        try:
            second_pass = iter(second_source) if second_source is not None else None
            for (frame, pose_result, angles), world_landmarks in zip(per_frame_angles, smoothed_world_landmarks):
                if second_pass is not None:
                    reread_frame = next(second_pass, None)
                    if reread_frame is None:
                        break  # le fichier a livré moins d'images la seconde fois : on s'arrête là
                    frame = replace(frame, image=reread_frame.image)
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
                    # Mains et pieds : hors RULA, absents quand rien n'est mesuré (jamais de
                    # couleur pour une donnée non mesurée).
                    for zone, extremity_score in (
                        ("hand", classify_hand(
                            angles.wrist_flexion_deg, angles.finger_curl_deg, extremity_thresholds
                        )),
                        ("foot", classify_foot(angles.ankle_flexion_deg, extremity_thresholds)),
                    ):
                        level = extremity_action_level(zone, extremity_score, extremity_thresholds)
                        if level is not None:
                            segment_action_levels[zone] = level
                image = (
                    anonymizer.anonymize(frame.image, pose_result.landmarks)
                    if anonymizer is not None else frame.image
                )
                annotated = draw_overlay(image, pose_result.landmarks, score)
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
        finally:
            # Portée volontairement restreinte au cycle de vie du writer : si
            # une exception survient en cours de boucle, on veut quand même
            # libérer le handle OS cv2.VideoWriter avant que le `finally`
            # englobant ne supprime video_tmp_path (sinon le fichier est bien
            # supprimé -- pas de fuite disque visible -- mais le handle reste
            # ouvert jusqu'au GC, ce qui n'est pas garanti immédiat).
            writer.release()
        if ffmpeg:
            _h264_with_ffmpeg(video_tmp_path, ffmpeg)
        video_bytes = video_tmp_path.read_bytes()
    finally:
        video_tmp_path.unlink(missing_ok=True)
        if second_source is not None:
            second_source.release()
        if anonymizer is not None:
            anonymizer.close()

    frame_rows = exporter.rows()
    pose3d_payload = build_pose3d_payload(pose3d_records)
    for row, pose3d_entry in zip(frame_rows, pose3d_payload):
        segments = pose3d_entry["segment_action_levels"] or {}
        row["neck_segment_action_level"] = segments.get("neck")
        row["trunk_segment_action_level"] = segments.get("trunk")
        row["upper_arm_segment_action_level"] = segments.get("upper_arm")
        row["lower_arm_segment_action_level"] = segments.get("lower_arm")
        row["hand_segment_action_level"] = segments.get("hand")
        row["foot_segment_action_level"] = segments.get("foot")

    return AnalysisResult(
        empty=False,
        video_bytes=video_bytes,
        frame_rows=frame_rows,
        summary=exporter.summary(),
        pose3d_records=pose3d_records,
    )
