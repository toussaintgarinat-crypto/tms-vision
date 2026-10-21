import numpy as np
import pytest

from tms_vision.face_blur import (
    FACE_LANDMARKS,
    FaceAnonymizer,
    Region,
    head_region_from_landmarks,
    pixelate_frame,
    pixelate_regions,
)
from tms_vision.pose_estimation import Landmark

WIDTH, HEIGHT = 320, 240


def noisy_image(width=WIDTH, height=HEIGHT, seed=0):
    return np.random.default_rng(seed).integers(0, 256, (height, width, 3), dtype=np.uint8)


def ellipse_mask(region: Region, width=WIDTH, height=HEIGHT):
    ys, xs = np.mgrid[0:height, 0:width]
    return ((xs - region.cx) / region.rx) ** 2 + ((ys - region.cy) / region.ry) ** 2 <= 1.0


def mean_abs_diff(a, b):
    return float(np.mean(np.abs(a.astype(int) - b.astype(int))))


def lm(x_px, y_px, visibility=1.0, width=WIDTH, height=HEIGHT):
    return Landmark(x=x_px / width, y=y_px / height, z=0.0, visibility=visibility)


def head_landmarks(cx=160, cy=70, head_width=40, with_shoulders=True):
    """Points du visage d'une personne de face, `head_width` pixels de large (oreille à oreille)."""
    half = head_width / 2
    landmarks = {
        "NOSE": lm(cx, cy + 0.10 * head_width),
        "LEFT_EYE_INNER": lm(cx + 0.12 * head_width, cy - 0.12 * head_width),
        "LEFT_EYE": lm(cx + 0.22 * head_width, cy - 0.12 * head_width),
        "LEFT_EYE_OUTER": lm(cx + 0.32 * head_width, cy - 0.10 * head_width),
        "RIGHT_EYE_INNER": lm(cx - 0.12 * head_width, cy - 0.12 * head_width),
        "RIGHT_EYE": lm(cx - 0.22 * head_width, cy - 0.12 * head_width),
        "RIGHT_EYE_OUTER": lm(cx - 0.32 * head_width, cy - 0.10 * head_width),
        "LEFT_EAR": lm(cx + half, cy),
        "RIGHT_EAR": lm(cx - half, cy),
        "MOUTH_LEFT": lm(cx + 0.15 * head_width, cy + 0.32 * head_width),
        "MOUTH_RIGHT": lm(cx - 0.15 * head_width, cy + 0.32 * head_width),
    }
    if with_shoulders:
        shoulder_y = cy + 1.4 * head_width
        landmarks["LEFT_SHOULDER"] = lm(cx + 1.3 * head_width, shoulder_y)
        landmarks["RIGHT_SHOULDER"] = lm(cx - 1.3 * head_width, shoulder_y)
    return landmarks


def inside(region: Region, x, y):
    return ((x - region.cx) / region.rx) ** 2 + ((y - region.cy) / region.ry) ** 2 <= 1.0


# --- Région de la tête déduite de la pose -------------------------------------------------

def test_head_region_covers_every_face_landmark():
    landmarks = head_landmarks()

    region = head_region_from_landmarks(landmarks, WIDTH, HEIGHT)

    assert region is not None
    for name in FACE_LANDMARKS:
        point = landmarks[name]
        assert inside(region, point.x * WIDTH, point.y * HEIGHT), name


def test_head_region_leaves_a_margin_around_the_ears_and_chin():
    landmarks = head_landmarks(head_width=40)
    region = head_region_from_landmarks(landmarks, WIDTH, HEIGHT)

    # Largeur de la tête : 40 px d'une oreille à l'autre. La région doit déborder nettement.
    assert region.rx >= 40 * 0.7
    assert region.ry >= region.rx  # plus haute que large (front, cheveux, menton)


def test_head_region_scales_with_the_size_of_the_head():
    small = head_region_from_landmarks(head_landmarks(head_width=30), WIDTH, HEIGHT)
    large = head_region_from_landmarks(head_landmarks(head_width=60), WIDTH, HEIGHT)

    assert large.rx == pytest.approx(2 * small.rx, rel=0.2)


def test_head_region_still_covers_the_face_when_only_some_landmarks_are_visible():
    landmarks = head_landmarks()
    for name in ("LEFT_EAR", "LEFT_EYE", "LEFT_EYE_INNER", "LEFT_EYE_OUTER", "MOUTH_LEFT"):
        del landmarks[name]  # visage de trois quarts : un côté non détecté

    region = head_region_from_landmarks(landmarks, WIDTH, HEIGHT)

    for name in landmarks:
        if name in FACE_LANDMARKS:
            assert inside(region, landmarks[name].x * WIDTH, landmarks[name].y * HEIGHT), name


def test_head_region_with_only_the_nose_uses_the_shoulder_width_for_its_size():
    landmarks = {
        "NOSE": lm(160, 70),
        "LEFT_SHOULDER": lm(220, 130), "RIGHT_SHOULDER": lm(100, 130),
    }

    region = head_region_from_landmarks(landmarks, WIDTH, HEIGHT)

    assert region.rx >= 0.29 * 120  # environ 30 % de la largeur des épaules, au minimum
    assert inside(region, 160, 70)


def test_head_region_without_any_face_point_is_placed_above_the_shoulders():
    landmarks = {"LEFT_SHOULDER": lm(220, 150), "RIGHT_SHOULDER": lm(100, 150)}

    region = head_region_from_landmarks(landmarks, WIDTH, HEIGHT)

    assert region is not None
    assert region.cy < 150
    assert abs(region.cx - 160) < 5
    assert region.rx >= 0.4 * 120


def test_head_region_is_none_without_face_points_or_both_shoulders():
    assert head_region_from_landmarks({}, WIDTH, HEIGHT) is None
    assert head_region_from_landmarks({"LEFT_SHOULDER": lm(220, 150)}, WIDTH, HEIGHT) is None
    assert head_region_from_landmarks({"RIGHT_HIP": lm(100, 200)}, WIDTH, HEIGHT) is None


# --- Pixellisation -------------------------------------------------------------------------

def test_pixelating_a_region_changes_the_inside_and_keeps_the_outside_identical():
    image = noisy_image()
    original = image.copy()
    region = Region(cx=160, cy=100, rx=40, ry=50)

    output = pixelate_regions(image, [region])

    mask = ellipse_mask(region)
    assert (output[~mask] == original[~mask]).all()
    assert mean_abs_diff(output[mask], original[mask]) > 30


def test_pixelating_destroys_the_detail_inside_the_region():
    region = Region(cx=160, cy=100, rx=40, ry=50)
    output = pixelate_regions(noisy_image(), [region])

    colours_inside = np.unique(output[ellipse_mask(region)].reshape(-1, 3), axis=0)
    colours_before = np.unique(noisy_image()[ellipse_mask(region)].reshape(-1, 3), axis=0)

    assert len(colours_inside) < 150
    assert len(colours_before) > 3000


def test_pixelating_never_modifies_its_input():
    image = noisy_image()
    original = image.copy()

    output = pixelate_regions(image, [Region(160, 100, 40, 50)])

    assert (image == original).all()
    assert output is not image


def test_a_region_partly_outside_the_image_is_clipped_without_error():
    image = noisy_image()
    region = Region(cx=5, cy=5, rx=40, ry=40)

    output = pixelate_regions(image, [region])

    assert output.shape == image.shape
    assert mean_abs_diff(output[:20, :20], image[:20, :20]) > 30
    assert (output[100:, 100:] == image[100:, 100:]).all()


def test_regions_outside_the_image_or_an_empty_list_change_nothing():
    image = noisy_image()

    assert (pixelate_regions(image, []) == image).all()
    assert (pixelate_regions(image, [Region(-500, -500, 20, 20)]) == image).all()
    assert (pixelate_regions(image, [Region(5000, 100, 20, 20)]) == image).all()


def test_several_regions_are_all_pixelated():
    image = noisy_image()
    first, second = Region(80, 100, 25, 30), Region(240, 100, 25, 30)

    output = pixelate_regions(image, [first, second])

    for region in (first, second):
        mask = ellipse_mask(region)
        assert mean_abs_diff(output[mask], image[mask]) > 30


def test_pixelating_the_whole_frame_destroys_it_and_keeps_the_shape():
    image = noisy_image()

    output = pixelate_frame(image)

    assert output.shape == image.shape and output.dtype == image.dtype
    assert mean_abs_diff(output, image) > 30
    assert len(np.unique(output.reshape(-1, 3), axis=0)) < 600
    assert (pixelate_frame(image) == output).all()  # déterministe


# --- Anonymisation d'une séquence ------------------------------------------------------------

class FakeDetector:
    def __init__(self, boxes_by_call=None):
        self.boxes_by_call = list(boxes_by_call or [])
        self.calls = 0
        self.closed = False

    def detect(self, image_bgr):
        boxes = self.boxes_by_call[self.calls] if self.calls < len(self.boxes_by_call) else []
        self.calls += 1
        return boxes

    def close(self):
        self.closed = True


def head_region_of(landmarks):
    return head_region_from_landmarks(landmarks, WIDTH, HEIGHT)


def test_the_head_found_by_the_pose_is_pixelated_and_the_rest_is_untouched():
    image = noisy_image()
    landmarks = head_landmarks()
    region = head_region_of(landmarks)

    output = FaceAnonymizer(fps=10).anonymize(image, landmarks)

    mask = ellipse_mask(region)
    assert (output[~mask] == image[~mask]).all()
    assert mean_abs_diff(output[mask], image[mask]) > 30


def test_a_face_found_by_the_detector_is_pixelated_even_without_a_pose():
    image = noisy_image()
    detector = FakeDetector([[(200, 40, 40, 40)]])  # x, y, largeur, hauteur en pixels

    output = FaceAnonymizer(fps=10, detector=detector).anonymize(image, None)

    assert mean_abs_diff(output[50:70, 210:230], image[50:70, 210:230]) > 30  # centre du visage
    assert (output[200:, :100] == image[200:, :100]).all()  # loin du visage : intact


def test_the_detector_adds_other_people_to_the_pose_subject():
    image = noisy_image()
    landmarks = head_landmarks(cx=90)
    detector = FakeDetector([[(220, 40, 40, 40)]])

    output = FaceAnonymizer(fps=10, detector=detector).anonymize(image, landmarks)

    main_head = ellipse_mask(head_region_of(landmarks))
    assert mean_abs_diff(output[main_head], image[main_head]) > 30
    assert mean_abs_diff(output[50:70, 230:250], image[50:70, 230:250]) > 30


def test_detector_boxes_are_enlarged_to_cover_the_whole_head():
    image = noisy_image()
    detector = FakeDetector([[(200, 100, 40, 40)]])

    output = FaceAnonymizer(fps=10, detector=detector).anonymize(image, None)

    # Hors de la boîte exacte (200..240, 100..140) mais dans la tête (cheveux, menton, oreilles).
    assert mean_abs_diff(output[88:100, 215:225], image[88:100, 215:225]) > 30
    assert mean_abs_diff(output[140:150, 215:225], image[140:150, 215:225]) > 30


def test_without_any_pose_or_history_the_whole_frame_is_pixelated():
    image = noisy_image()

    output = FaceAnonymizer(fps=10).anonymize(image, None)

    assert (output == pixelate_frame(image)).all()


def test_a_pose_that_gives_no_head_position_is_treated_as_no_detection():
    image = noisy_image()

    output = FaceAnonymizer(fps=10).anonymize(image, {"RIGHT_HIP": lm(100, 200)})

    assert (output == pixelate_frame(image)).all()


def test_the_last_head_position_is_kept_for_a_second_when_the_pose_is_lost():
    fps = 10
    anonymizer = FaceAnonymizer(fps=fps, hold_seconds=1.0)
    landmarks = head_landmarks()
    region = head_region_of(landmarks)
    anonymizer.anonymize(noisy_image(seed=1), landmarks)

    for n in range(1, fps + 1):
        image = noisy_image(seed=n + 1)
        output = anonymizer.anonymize(image, None)
        centre = (slice(int(region.cy) - 5, int(region.cy) + 5), slice(int(region.cx) - 5, int(region.cx) + 5))
        assert mean_abs_diff(output[centre], image[centre]) > 30, f"image {n}"
        far = (slice(200, None), slice(0, 100))
        assert (output[far] == image[far]).all(), f"image {n} : le reste doit rester intact"

    image = noisy_image(seed=99)
    assert (anonymizer.anonymize(image, None) == pixelate_frame(image)).all()


def test_the_held_region_is_enlarged_because_the_head_may_have_moved():
    anonymizer = FaceAnonymizer(fps=10)
    landmarks = head_landmarks()
    region = head_region_of(landmarks)
    anonymizer.anonymize(noisy_image(), landmarks)
    image = noisy_image(seed=5)

    output = anonymizer.anonymize(image, None)

    # Juste au-delà du bord de la région d'origine, côté droit : doit aussi être pixellisé.
    x = int(region.cx + region.rx * 1.15)
    y = int(region.cy)
    assert mean_abs_diff(output[y - 3:y + 3, x - 3:x + 3], image[y - 3:y + 3, x - 3:x + 3]) > 20


def test_finding_the_pose_again_ends_the_full_frame_blur():
    anonymizer = FaceAnonymizer(fps=10, hold_seconds=0.1)
    image = noisy_image()
    assert (anonymizer.anonymize(image, None) == pixelate_frame(image)).all()
    landmarks = head_landmarks()

    output = anonymizer.anonymize(image, landmarks)

    assert (output[200:, :100] == image[200:, :100]).all()


def test_a_detector_box_keeps_the_frame_from_being_fully_blurred_after_the_hold():
    anonymizer = FaceAnonymizer(fps=10, hold_seconds=0.1, detector=FakeDetector([[(200, 40, 40, 40)]] * 5))
    image = noisy_image()

    output = anonymizer.anonymize(image, None)

    assert not (output == pixelate_frame(image)).all()
    assert (output[200:, :100] == image[200:, :100]).all()


def test_the_anonymizer_never_modifies_the_frame_it_receives():
    image = noisy_image()
    original = image.copy()
    anonymizer = FaceAnonymizer(fps=10, detector=FakeDetector([[(10, 10, 30, 30)]]))

    anonymizer.anonymize(image, head_landmarks())
    anonymizer.anonymize(image, None)

    assert (image == original).all()


def test_close_closes_the_detector():
    detector = FakeDetector()

    FaceAnonymizer(fps=10, detector=detector).close()

    assert detector.closed is True


def test_the_hold_duration_is_converted_to_frames_using_the_frame_rate():
    anonymizer = FaceAnonymizer(fps=25, hold_seconds=2.0)

    assert anonymizer.hold_frames == 50
    assert FaceAnonymizer(fps=0, hold_seconds=1.0).hold_frames >= 1
