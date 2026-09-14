"""Point d'entrée CLI : orchestre capture -> pose -> angles -> score RULA ->
overlay vidéo + export CSV/JSON.

Conseil de prise de vue : pour des angles fiables (flexion/extension du cou,
du tronc et du bras), filmer la personne DE PROFIL plutôt que de face.
"""
import argparse
import sys
import time
from pathlib import Path

import cv2

from tms_vision.capture import FrameSource
from tms_vision.pose_estimation import PoseEstimator
from tms_vision.angles import compute_joint_angles
from tms_vision.rula.scoring import compute_rula_score, detect_muscle_use
from tms_vision.overlay import draw_overlay
from tms_vision.export import FrameRecord, ResultsExporter


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--load-kg doit être positif ou nul")
    return parsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse ergonomique RULA d'une vidéo de poste de travail."
    )
    parser.add_argument("--source", required=True, help='"webcam" ou chemin vers un fichier vidéo')
    parser.add_argument("--side", choices=["left", "right"], default="right")
    parser.add_argument("--load-kg", type=_non_negative_float, default=0.0)
    parser.add_argument("--wrist-twist", choices=["normal", "extreme"], default="normal")
    parser.add_argument("--output-dir", default="outputs")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S")

    wrist_twist = 1 if args.wrist_twist == "normal" else 2

    source = FrameSource(args.source)
    estimator = PoseEstimator()

    frames = list(source)
    source.release()

    per_frame_angles = []
    posture_load_history: list[tuple[float, float]] = []

    for frame in frames:
        pose_result = estimator.process(frame.image)
        angles = None
        if pose_result.landmarks is not None:
            angles = compute_joint_angles(pose_result.landmarks, side=args.side)
        per_frame_angles.append((frame, pose_result, angles))
        if angles is not None:
            posture_load = angles.trunk_flexion_deg + angles.upper_arm_flexion_deg
            posture_load_history.append((frame.timestamp_seconds, posture_load))

    estimator.close()

    muscle_use_score = 1 if detect_muscle_use(posture_load_history) else 0

    height, width = frames[0].image.shape[:2] if frames else (0, 0)
    video_path = output_dir / f"{run_id}_annotated.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), source.fps() or 30.0, (width, height)
    )

    exporter = ResultsExporter(
        str(output_dir / f"{run_id}_frames.csv"),
        str(output_dir / f"{run_id}_summary.json"),
    )

    for frame, pose_result, angles in per_frame_angles:
        score = None
        if angles is not None:
            score = compute_rula_score(
                angles, wrist_twist=wrist_twist, load_kg=args.load_kg, muscle_use_score=muscle_use_score
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
    print(f"Vidéo annotée : {video_path}")
    print(f"Export CSV/JSON : {output_dir}/{run_id}_frames.csv, {output_dir}/{run_id}_summary.json")


def main() -> None:
    args = parse_args(sys.argv[1:])
    try:
        run(args)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
