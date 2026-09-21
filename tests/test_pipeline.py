import json

import numpy as np
import cv2
import pytest

from tms_vision.pipeline import analyze_video, AnalysisResult, _RunningMean
from tms_vision.capture import Frame
from tms_vision.pose_estimation import Landmark, PoseEstimator, PoseResult


def test_running_mean_starts_at_none():
    mean = _RunningMean()
    assert mean.value is None


def test_running_mean_computes_average_incrementally():
    mean = _RunningMean()
    mean.update(2.0)
    assert mean.value == 2.0
    mean.update(4.0)
    assert mean.value == 3.0
    mean.update(9.0)
    assert mean.value == 5.0


class _EmptyFrameSource:
    """Simule une source vidéo qui s'ouvre correctement mais ne produit aucune
    frame -- le cas que le garde-fou "aucune frame capturée" doit intercepter
    avant toute tentative d'ouverture d'un cv2.VideoWriter en taille (0, 0)."""

    def __init__(self, *_args, **_kwargs):
        pass

    def fps(self):
        return 30.0

    def __iter__(self):
        return iter([])

    def release(self):
        pass


def test_analyze_video_with_zero_frames_returns_empty_result_without_writing(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _EmptyFrameSource)

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source="webcam", side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result == AnalysisResult(empty=True)
    captured = capsys.readouterr()
    assert "Aucune frame capturée" in captured.err
    assert list(output_dir.glob("*_annotated.mp4")) == []
    assert list(output_dir.glob("*_frames.csv")) == []
    assert list(output_dir.glob("*_summary.json")) == []


def test_analyze_video_end_to_end_on_a_blank_synthetic_video(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result.empty is False
    assert result.video_path.exists()
    assert result.csv_path.exists()
    assert result.summary_json_path.exists()


def test_analyze_video_writes_browser_playable_h264_not_mp4v(tmp_path):
    """Régression pour 9d6a9da : le fourcc d'écriture doit être "avc1"
    (H.264, lisible par les navigateurs), pas "mp4v" (MPEG-4 Part 2, que
    Chromium/Firefox refusent de décoder). On vérifie via une relecture
    cv2.VideoCapture plutôt que via ffprobe (binaire externe non déclaré
    comme dépendance du projet). Sur ce build OpenCV/FFmpeg, CAP_PROP_FOURCC
    relit "h264" pour un fichier écrit avec le tag "avc1", et "FMP4" pour un
    fichier écrit avec "mp4v" -- vérifié empiriquement (y compris en
    ré-exécutant analyze_video) avant d'écrire cette assertion, donc "h264"
    est bien la valeur à verrouiller ici plutôt qu'un "avc1" deviné."""
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result.empty is False
    cap = cv2.VideoCapture(str(result.video_path))
    try:
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = fourcc_int.to_bytes(4, byteorder="little").decode("ascii", errors="replace")
    finally:
        cap.release()

    assert fourcc == "h264", (
        f"Codec vidéo attendu 'h264' (lisible en navigateur), obtenu {fourcc!r} -- "
        "vérifier que analyze_video encode toujours avec "
        "cv2.VideoWriter_fourcc(*'avc1') et non 'mp4v'"
    )


class _InterruptingFrameSource:
    """Simule une source vidéo qui produit quelques frames puis reçoit un
    Ctrl+C (KeyboardInterrupt) pendant la boucle de capture."""

    def __init__(self, *_args, **_kwargs):
        self.released = False

    def fps(self):
        return 30.0

    def __iter__(self):
        for i in range(2):
            yield Frame(
                index=i, timestamp_seconds=i / 30.0,
                image=np.zeros((64, 64, 3), dtype=np.uint8),
            )
        raise KeyboardInterrupt

    def release(self):
        self.released = True


def test_analyze_video_with_keyboard_interrupt_during_capture_still_writes_partial_outputs(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _InterruptingFrameSource)

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source="webcam", side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    captured = capsys.readouterr()
    assert "Capture interrompue" in captured.out
    assert result.empty is False
    assert result.video_path.exists()
    assert result.csv_path.exists()
    assert result.summary_json_path.exists()


def test_analyze_video_produces_pose3d_json(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result.pose3d_path is not None
    assert result.pose3d_path.exists()
    data = json.loads(result.pose3d_path.read_text())
    assert len(data) == 3
    for entry in data:
        assert entry["detected"] is False
        assert entry["landmarks"] is None
        assert entry["action_level"] is None
        assert entry["segment_action_levels"] is None


def _lm(x, y, z=0.0, visibility=1.0):
    return Landmark(x=x, y=y, z=z, visibility=visibility)


def test_analyze_video_pose3d_json_key_set_varies_per_frame_when_landmark_occluded(
    tmp_path, monkeypatch
):
    """Régression pour la revue finale du plan avatar 3D (Finding #4) : le
    contrat que consomme web/app/PostureAvatar3D.tsx n'est PAS seulement
    "landmarks: null pour les frames non détectées" (déjà couvert par
    test_analyze_video_produces_pose3d_json ci-dessus, sur une vidéo noire
    où aucune pose n'est jamais détectée) -- c'est aussi que, quand une pose
    EST détectée, l'ensemble des clés de `landmarks` peut varier d'une frame
    à l'autre (une articulation occultée une frame donnée est absente du
    dict cette frame-là précisément, pas juste sur des frames "detected:
    false"). C'est exactement le cas réel (vue de profil, bras/genou côté
    caméra opposée occultés quasi en continu) qui a permis Finding #1 (barre
    grise fantôme) de passer inaperçu côté frontend : aucun test existant ne
    fabrique un pose3d.json avec un jeu de clés variable sur des frames
    `detected: true`.

    On monkeypatch PoseEstimator.process (même style que _EmptyFrameSource /
    _InterruptingFrameSource plus haut dans ce fichier) pour renvoyer des
    PoseResult fabriqués à la main : landmarks 2D complets et constants (côté
    droit, posture debout neutre -- même motif que
    tests/test_integration_angles_to_score.py::_neutral_standing_landmarks,
    pour garantir detected=True et un action_level non-null sur chaque
    frame), mais des world_landmarks dont LEFT_ELBOW est présent sur les
    frames 0 et 2 et absent sur la frame 1 (simulation d'une occultation
    ponctuelle, comme LEFT_ELBOW/LEFT_KNEE sur la vidéo de référence réelle
    du projet filmée de profil)."""

    def _neutral_landmarks_2d_right_side():
        return {
            "LEFT_SHOULDER": _lm(0.50, 0.30),
            "RIGHT_SHOULDER": _lm(0.50, 0.30),
            "LEFT_HIP": _lm(0.50, 0.55),
            "RIGHT_HIP": _lm(0.50, 0.55),
            "NOSE": _lm(0.52, 0.20),
            "RIGHT_EAR": _lm(0.51, 0.22),
            "RIGHT_ELBOW": _lm(0.50, 0.45),
            "RIGHT_WRIST": _lm(0.50, 0.60),
            "RIGHT_INDEX": _lm(0.50, 0.63),
        }

    def _world_landmarks(include_left_elbow: bool):
        world = {
            "LEFT_SHOULDER": _lm(-0.1, -0.3, 0.0),
            "RIGHT_SHOULDER": _lm(0.1, -0.3, 0.0),
            "LEFT_HIP": _lm(-0.1, 0.0, 0.0),
            "RIGHT_HIP": _lm(0.1, 0.0, 0.0),
            "NOSE": _lm(0.0, -0.5, 0.05),
            "RIGHT_EAR": _lm(0.05, -0.48, 0.02),
            "RIGHT_ELBOW": _lm(0.15, -0.1, 0.0),
            "RIGHT_WRIST": _lm(0.15, 0.15, 0.0),
        }
        if include_left_elbow:
            world["LEFT_ELBOW"] = _lm(-0.15, -0.1, 0.0)
        return world

    fake_results = [
        PoseResult(
            landmarks=_neutral_landmarks_2d_right_side(),
            world_landmarks=_world_landmarks(include_left_elbow=True),
        ),
        PoseResult(
            landmarks=_neutral_landmarks_2d_right_side(),
            world_landmarks=_world_landmarks(include_left_elbow=False),
        ),
        PoseResult(
            landmarks=_neutral_landmarks_2d_right_side(),
            world_landmarks=_world_landmarks(include_left_elbow=True),
        ),
    ]
    call_count = {"n": 0}

    def fake_process(self, image_bgr):
        i = call_count["n"]
        call_count["n"] = i + 1
        return fake_results[i]

    monkeypatch.setattr(PoseEstimator, "process", fake_process)

    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result.pose3d_path is not None
    data = json.loads(result.pose3d_path.read_text())
    assert len(data) == 3

    for entry in data:
        assert entry["detected"] is True
        assert entry["landmarks"] is not None
        assert entry["action_level"] is not None
        assert entry["segment_action_levels"] is not None
        assert set(entry["segment_action_levels"].keys()) == {"neck", "trunk", "upper_arm", "lower_arm"}
        valid_levels = {
            "acceptable",
            "investigation_recommandee",
            "investigation_et_changement_bientot",
            "changement_immediat",
        }
        for level in entry["segment_action_levels"].values():
            assert level in valid_levels
        for name, coords in entry["landmarks"].items():
            assert isinstance(coords, list)
            assert len(coords) == 3
            assert all(isinstance(v, float) for v in coords)

    assert "LEFT_ELBOW" in data[0]["landmarks"], (
        "frame 0 doit conserver LEFT_ELBOW (présent dans les landmarks bruts "
        "de cette frame)"
    )
    assert "LEFT_ELBOW" not in data[1]["landmarks"], (
        "frame 1 doit exclure LEFT_ELBOW (absent des landmarks bruts de "
        "cette frame précisément -- Finding #1 : un frontend qui ne teste "
        "pas ce cas peut laisser une capsule à sa position de montage par "
        "défaut au lieu de la masquer)"
    )
    assert "LEFT_ELBOW" in data[2]["landmarks"]

    # Le reste des landmarks communs aux 3 frames doit être présent partout
    # (contrat : le jeu de clés ne varie que pour l'articulation
    # volontairement occultée dans ce test).
    for entry in data:
        for name in ("RIGHT_SHOULDER", "RIGHT_ELBOW", "RIGHT_WRIST", "NOSE"):
            assert name in entry["landmarks"]


def test_analyze_video_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        analyze_video(
            source="does-not-exist.mp4", side="right", load_kg=0.0,
            wrist_twist="normal", output_dir="outputs",
        )
