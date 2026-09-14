"""Point d'entrée CLI : parse les arguments et délègue le pipeline à
tms_vision.pipeline.analyze_video() (voir ce module pour la logique complète).

Conseil de prise de vue : pour des angles fiables (flexion/extension du cou,
du tronc et du bras), filmer la personne DE PROFIL plutôt que de face.
"""
import argparse
import sys

from tms_vision.pipeline import analyze_video


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
        source=args.source,
        side=args.side,
        load_kg=args.load_kg,
        wrist_twist=args.wrist_twist,
        output_dir=args.output_dir,
    )
    if result.empty:
        return
    print(f"Vidéo annotée : {result.video_path}")
    print(f"Export CSV/JSON : {result.csv_path}, {result.summary_json_path}")


def main() -> None:
    args = parse_args(sys.argv[1:])
    try:
        run(args)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        # Un premier Ctrl+C pendant la capture est déjà intercepté à
        # l'intérieur de analyze_video() et traite les frames déjà capturées.
        # Un second Ctrl+C pendant la boucle de traitement qui suit (pose/
        # score/écriture vidéo) n'est en revanche pas couvert par ce
        # garde-fou interne : on l'attrape ici pour éviter une traceback
        # brute sans sortie utile.
        print("Traitement interrompu par l'utilisateur.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
