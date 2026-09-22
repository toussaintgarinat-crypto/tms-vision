"""Point d'entrée CLI : parse les arguments, délègue le calcul à
tms_vision.pipeline.analyze_video() (pur, voir ce module), puis écrit
vidéo/CSV/JSON dans --output-dir -- seul endroit du projet qui écrit encore
ces résultats sur le système de fichiers (voir
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md : l'API
web persiste en DuckDB via tms_vision.storage, pas sur disque).

Conseil de prise de vue : pour des angles fiables (flexion/extension du cou,
du tronc et du bras), filmer la personne DE PROFIL plutôt que de face.
"""
import argparse
import sys
from pathlib import Path

from tms_vision.pipeline import analyze_video, generate_run_id
from tms_vision.export import write_frames_csv, write_summary_json
from tms_vision.pose3d_export import write_pose3d_json


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
    result = analyze_video(
        source=args.source, side=args.side, load_kg=args.load_kg, wrist_twist=args.wrist_twist,
    )
    if result.empty:
        return

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    run_id = generate_run_id()

    video_path = output_path / f"{run_id}_annotated.mp4"
    video_path.write_bytes(result.video_bytes)

    csv_path = output_path / f"{run_id}_frames.csv"
    write_frames_csv(result.frame_rows, str(csv_path))

    summary_path = output_path / f"{run_id}_summary.json"
    write_summary_json(result.summary, str(summary_path))

    pose3d_path = output_path / f"{run_id}_pose3d.json"
    write_pose3d_json(str(pose3d_path), result.pose3d_records)

    print(f"Vidéo annotée : {video_path}")
    print(f"Export CSV/JSON : {csv_path}, {summary_path}")


def main() -> None:
    args = parse_args(sys.argv[1:])
    try:
        run(args)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)
    # Un premier Ctrl+C est déjà intercepté à l'intérieur de la boucle de
    # capture de frames d'analyze_video() (arrête proprement la capture et
    # renvoie ce qui a été collecté jusque-là). Ce second except couvre un
    # Ctrl+C pendant la boucle de traitement/encodage qui suit -- run() n'est
    # alors plus dans analyze_video() et rien d'autre n'intercepterait cette
    # interruption avant qu'elle ne remonte jusqu'ici.
    except KeyboardInterrupt:
        print("Traitement interrompu par l'utilisateur.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
