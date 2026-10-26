"""Le pipeline n'écrit jamais l'image brute dans la vidéo annotée : les têtes sont pixellisées
avant l'écriture (voir face_blur.py). Ces tests remplacent la source d'images, la pose, le
détecteur de visages et l'écriture vidéo par des doubles, pour vérifier ce qui est réellement
ÉCRIT, sans dépendre d'un encodeur H.264."""
import cv2
import numpy as np
import pytest

from tms_vision import pipeline
from tms_vision.capture import Frame
from tms_vision.pipeline import analyze_video
from tms_vision.pose_estimation import Landmark, PoseResult

WIDTH, HEIGHT, FRAME_COUNT, FPS = 160, 120, 6, 10.0


def noisy_frame(seed):
    return np.random.default_rng(seed).integers(0, 256, (HEIGHT, WIDTH, 3), dtype=np.uint8)


ORIGINAL_FRAMES = [noisy_frame(seed) for seed in range(FRAME_COUNT)]


class FakeFrameSource:
    def __init__(self, *_args, **_kwargs):
        pass

    def fps(self):
        return FPS

    def __iter__(self):
        for index, image in enumerate(ORIGINAL_FRAMES):
            yield Frame(index=index, timestamp_seconds=index / FPS, image=image.copy())

    def release(self):
        pass


def lm(x, y):
    return Landmark(x=x, y=y, z=0.0, visibility=1.0)


# Tête vers (0.52, 0.20) de l'image ; le reste du corps sous elle.
LANDMARKS = {
    "LEFT_SHOULDER": lm(0.50, 0.30), "RIGHT_SHOULDER": lm(0.50, 0.30),
    "LEFT_HIP": lm(0.50, 0.55), "RIGHT_HIP": lm(0.50, 0.55),
    "NOSE": lm(0.52, 0.20), "RIGHT_EAR": lm(0.51, 0.22),
    "RIGHT_ELBOW": lm(0.50, 0.45), "RIGHT_WRIST": lm(0.50, 0.60), "RIGHT_INDEX": lm(0.50, 0.63),
}
HEAD_PIXELS = (slice(18, 32), slice(76, 90))      # autour du nez : (y, x)
FAR_PIXELS = (slice(90, None), slice(0, 60))      # bas gauche de l'image, loin de la tête


class FakeEstimator:
    def __init__(self, *_args, **_kwargs):
        pass

    def process(self, image_bgr):
        return PoseResult(landmarks=dict(LANDMARKS), world_landmarks=None)

    def close(self):
        pass


class FakeDetector:
    instances = []

    def __init__(self, *_args, **_kwargs):
        self.closed = False
        FakeDetector.instances.append(self)

    def detect(self, image_bgr):
        return []

    def close(self):
        self.closed = True


class RecordingWriter:
    """Remplace cv2.VideoWriter : garde les images qu'on lui demande d'écrire."""

    instances = []

    def __init__(self, *_args, **_kwargs):
        self.frames = []
        RecordingWriter.instances.append(self)

    def isOpened(self):
        return True

    def write(self, frame):
        self.frames.append(frame.copy())

    def release(self):
        pass


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    RecordingWriter.instances.clear()
    FakeDetector.instances.clear()
    monkeypatch.setattr(pipeline, "FrameSource", FakeFrameSource)
    monkeypatch.setattr(pipeline, "PoseEstimator", FakeEstimator)
    monkeypatch.setattr(pipeline, "default_face_detector", FakeDetector)
    monkeypatch.setattr(cv2, "VideoWriter", RecordingWriter)
    # On isole le floutage : le squelette et le badge de score ne doivent pas brouiller la mesure.
    monkeypatch.setattr(pipeline, "draw_overlay", lambda image, landmarks, score: image.copy())


def written_frames():
    assert len(RecordingWriter.instances) == 1
    return RecordingWriter.instances[0].frames


def mean_abs_diff(a, b):
    return float(np.mean(np.abs(a.astype(int) - b.astype(int))))


def run(**kwargs):
    return analyze_video(source="ignored.mp4", side="right", load_kg=0.0, wrist_twist="normal", **kwargs)


def test_every_written_frame_has_its_head_pixelated():
    run()

    frames = written_frames()
    assert len(frames) == FRAME_COUNT
    for original, written in zip(ORIGINAL_FRAMES, frames):
        assert mean_abs_diff(written[HEAD_PIXELS], original[HEAD_PIXELS]) > 30


def test_the_rest_of_the_image_is_left_untouched():
    run()

    for original, written in zip(ORIGINAL_FRAMES, written_frames()):
        assert (written[FAR_PIXELS] == original[FAR_PIXELS]).all()


def test_anonymization_is_on_by_default_and_can_only_be_turned_off_explicitly():
    run(anonymize=False)

    for original, written in zip(ORIGINAL_FRAMES, written_frames()):
        assert (written == original).all()


def test_the_face_detector_is_created_and_closed_around_the_analysis():
    run()

    assert len(FakeDetector.instances) == 1
    assert FakeDetector.instances[0].closed is True


def test_no_face_detector_is_created_when_anonymization_is_off():
    run(anonymize=False)

    assert FakeDetector.instances == []


def test_the_analysis_results_are_unaffected_by_the_anonymization():
    with_blur = run()
    without_blur = run(anonymize=False)

    assert with_blur.summary == without_blur.summary
    assert with_blur.frame_rows == without_blur.frame_rows


def test_the_detector_receives_the_unblurred_frames(monkeypatch):
    seen = []

    class SpyDetector(FakeDetector):
        def detect(self, image_bgr):
            seen.append(image_bgr.copy())
            return []

    monkeypatch.setattr(pipeline, "default_face_detector", SpyDetector)
    run()

    assert len(seen) == FRAME_COUNT
    for original, frame in zip(ORIGINAL_FRAMES, seen):
        assert (frame == original).all()


def test_a_face_detector_that_cannot_start_aborts_the_analysis_instead_of_skipping_the_blur(monkeypatch):
    class Broken:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("modèle introuvable")

    monkeypatch.setattr(pipeline, "default_face_detector", Broken)

    with pytest.raises(RuntimeError, match="modèle introuvable"):
        run()

    assert RecordingWriter.instances == []  # rien n'a été écrit


def test_a_file_is_read_twice_and_keeps_no_image_in_memory_between_the_passes(monkeypatch):
    opened = []
    real = FakeFrameSource

    class CountingSource(real):
        def __init__(self, source, *_args, **_kwargs):
            opened.append(source)

    monkeypatch.setattr(pipeline, "FrameSource", CountingSource)
    kept = []
    real_replace = pipeline.replace

    def spy_replace(obj, **changes):
        clone = real_replace(obj, **changes)
        if isinstance(obj, Frame) and "image" in changes:
            kept.append(clone.image)
        return clone

    monkeypatch.setattr(pipeline, "replace", spy_replace)

    result = analyze_video(source="clip.mp4", side="right", load_kg=0.0, wrist_twist="normal")

    assert opened == ["clip.mp4", "clip.mp4"]
    assert len(result.frame_rows) == FRAME_COUNT
    # Première passe : les images sont retirées des frames conservées (image=None) ;
    # seconde passe : chaque image relue est rendue à l'écriture, une à la fois.
    assert sum(image is None for image in kept) == FRAME_COUNT
    assert sum(image is not None for image in kept) == FRAME_COUNT
    assert len(written_frames()) == FRAME_COUNT


def test_the_webcam_is_read_once_because_it_cannot_be_replayed(monkeypatch):
    opened = []

    class CountingSource(FakeFrameSource):
        def __init__(self, source, *_args, **_kwargs):
            opened.append(source)

    monkeypatch.setattr(pipeline, "FrameSource", CountingSource)

    result = analyze_video(source="webcam", side="right", load_kg=0.0, wrist_twist="normal")

    assert opened == ["webcam"]
    assert len(result.frame_rows) == FRAME_COUNT
