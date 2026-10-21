"""Essai sur de VRAIS visages : une photo réelle (domaine public, fournie par scikit-image) passe
dans les vraies détections MediaPipe, puis dans l'anonymisation ; le critère est qu'un détecteur
de visages ne trouve plus aucun visage ensuite.

ATTENTION à ce critère : « le détecteur ne trouve plus de visage » est valable sur cette photo
nette, mais PAS sur de vraies vidéos, où le détecteur se déclenche sur la mosaïque elle-même (voir
docs/superpowers/specs/2026-10-22-face-blur-design.md) ; il y faut une relecture visuelle.

Ignoré si scikit-image n'est pas installé (`pip install scikit-image`) ou si cette version de
mediapipe n'a pas l'API `solutions` (voir requirements.txt)."""
import cv2
import mediapipe as mp
import numpy as np
import pytest

skimage_data = pytest.importorskip("skimage.data")
pytestmark = pytest.mark.skipif(
    not hasattr(mp, "solutions"), reason="mediapipe sans l'API solutions (voir requirements.txt)"
)

from tms_vision.face_blur import FaceAnonymizer, MediaPipeFaceDetector  # noqa: E402
from tms_vision.pose_estimation import PoseEstimator  # noqa: E402


@pytest.fixture(scope="module")
def photo():
    return cv2.cvtColor(skimage_data.astronaut(), cv2.COLOR_RGB2BGR)


@pytest.fixture(scope="module")
def checker():
    detector = MediaPipeFaceDetector()
    yield detector
    detector.close()


def pose_landmarks(image):
    estimator = PoseEstimator()
    try:
        return estimator.process(image).landmarks
    finally:
        estimator.close()


def test_sanity_the_photo_does_contain_a_detectable_face(photo, checker):
    assert len(checker.detect(photo)) == 1


def test_the_head_found_by_the_pose_alone_is_no_longer_a_detectable_face(photo, checker):
    landmarks = pose_landmarks(photo)
    assert landmarks is not None

    output = FaceAnonymizer(fps=10).anonymize(photo, landmarks)

    assert checker.detect(output) == []


def test_the_face_found_by_the_detector_alone_is_no_longer_detectable(photo, checker):
    anonymizer = FaceAnonymizer(fps=10, detector=MediaPipeFaceDetector())
    try:
        output = anonymizer.anonymize(photo, None)  # pose perdue
    finally:
        anonymizer.close()

    assert checker.detect(output) == []


def test_a_second_person_is_only_covered_thanks_to_the_detector(photo, checker):
    two_people = np.concatenate([photo, photo], axis=1)
    assert len(checker.detect(two_people)) == 2
    landmarks = pose_landmarks(two_people)  # la pose ne suit qu'une seule personne

    pose_only = FaceAnonymizer(fps=10).anonymize(two_people, landmarks)
    anonymizer = FaceAnonymizer(fps=10, detector=MediaPipeFaceDetector())
    try:
        both = anonymizer.anonymize(two_people, landmarks)
    finally:
        anonymizer.close()

    assert len(checker.detect(pose_only)) == 1  # la seconde personne resterait visible
    assert checker.detect(both) == []


def test_the_background_outside_the_head_is_kept(photo):
    landmarks = pose_landmarks(photo)

    output = FaceAnonymizer(fps=10).anonymize(photo, landmarks)

    assert (output[300:, :200] == photo[300:, :200]).all()  # combinaison et drapeau, loin de la tête
