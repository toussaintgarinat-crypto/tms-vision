import cv2
import numpy as np
import pytest

from tms_vision.custom_metrics import CONTACT_DISTANCE, CustomPointsAccumulator
from tms_vision.pipeline import analyze_video
from tms_vision.pose_models import CustomKeypointsModel, CustomSpec, PoseModelError, PoseOptions
from tms_vision.pose_models.custom_keypoints import slugify

W, H = 160, 120
SPEED = 2  # pixels par image


def _frame(step: int, visible: bool = True) -> np.ndarray:
    """Fond neutre + patch texturé (bruit fixe) qui se déplace vers la droite."""
    rng = np.random.default_rng(7)
    image = np.full((H, W, 3), 90, np.uint8)
    if visible:
        patch = rng.integers(0, 255, (30, 30, 3), dtype=np.uint8)
        x = 20 + SPEED * step
        image[45:75, x:x + 30] = patch
    return image


def _spec(reference_time=0.0, x=35 / W, y=60 / H):
    return CustomSpec.from_dict({"reference_time_seconds": reference_time,
                                 "points": [{"name": "Clé à molette", "x": x, "y": y}]})


def test_spec_normalizes_names_and_validates_input():
    spec = _spec()
    assert spec.points[0].name == "cle_a_molette" and spec.points[0].keypoint_name == "custom_cle_a_molette"
    assert slugify("  Zone de danger !! ") == "zone_de_danger"
    assert CustomSpec.from_dict(spec.to_dict()) == spec
    bad = [
        {}, {"points": []}, {"points": "x"},
        {"points": [{"name": "a", "x": 1.5, "y": 0.5}]},
        {"points": [{"name": "a", "y": 0.5}]},
        {"points": [{"name": "a", "x": 0.1, "y": 0.1}, {"name": "A", "x": 0.2, "y": 0.2}]},
        {"points": [{"x": 0.1, "y": 0.1}] * 11},
        {"points": [{"name": "a", "x": 0.1, "y": 0.1}], "reference_time_seconds": -1},
    ]
    for data in bad:
        with pytest.raises(PoseModelError):
            CustomSpec.from_dict(data)


def test_unnamed_points_get_default_names():
    spec = CustomSpec.from_dict({"points": [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.2}]})
    assert [p.name for p in spec.points] == ["point_1", "point_2"]


def test_tracker_follows_a_moving_textured_patch():
    model = CustomKeypointsModel(_spec())
    for step in range(25):
        poses = model.process_frame(_frame(step), step, timestamp_seconds=step / 10)
        assert len(poses) == 1, f"point perdu à l'image {step}"
        point = poses[0].keypoints[0]
        assert point.name == "custom_cle_a_molette"
        assert abs(point.x * W - (35 + SPEED * step)) < 2.0
        assert abs(point.y * H - 60) < 2.0
        assert 0 < point.confidence <= 1
    assert model.get_keypoints() == poses


def test_point_is_omitted_when_target_disappears_then_abandoned():
    model = CustomKeypointsModel(_spec())
    for step in range(5):
        model.process_frame(_frame(step), step)
    assert model.process_frame(_frame(5, visible=False), 5) == []  # cible disparue : omis, pas d'erreur
    for step in range(6, 30):
        assert model.process_frame(_frame(5, visible=False), step) == []


def test_nothing_before_the_reference_time():
    model = CustomKeypointsModel(_spec(reference_time=1.0, x=(20 + 2 * 10 + 15) / W))
    assert model.process_frame(_frame(0), 0, timestamp_seconds=0.0) == []
    first = model.process_frame(_frame(10), 10, timestamp_seconds=1.0)
    assert first[0].keypoints[0].confidence == 1.0  # position saisie par l'utilisateur
    assert abs(first[0].keypoints[0].x * W - 55) < 1e-3


def test_tracker_works_without_timestamps_and_with_edge_points():
    model = CustomKeypointsModel(CustomSpec.from_dict({"points": [{"name": "bord", "x": 1.0, "y": 0.5}]}))
    poses = model.process_frame(_frame(0), 0)
    assert poses[0].keypoints[0].x == 1.0
    model.process_frame(_frame(1), 1)  # ne doit pas lever même au bord de l'image


def test_accumulator_path_speed_contact_and_gaps():
    acc = CustomPointsAccumulator(["custom_a"])
    near = (0.5, 0.5)
    acc.update(0.0, 1.0, {"custom_a": (0.5, 0.5)}, [near])
    acc.update(0.5, 1.0, {"custom_a": (0.6, 0.5)}, [(0.9, 0.9)])  # loin de la main
    acc.update(1.0, 1.0, {}, [])  # perdu
    acc.update(1.5, 1.0, {"custom_a": (0.6, 0.5)}, [(0.6, 0.5 + CONTACT_DISTANCE / 2)])
    s = acc.summary()["custom_a"]
    assert s["tracked_frame_count"] == 3 and s["tracked_ratio"] == 0.75
    assert abs(s["path_length"] - 0.1) < 1e-9  # pas de segment relié à travers le trou
    assert abs(s["max_speed"] - 0.2) < 1e-9
    assert s["hand_contact_seconds"] == 0.5  # contact à la dernière image : intervalle depuis la précédente


def test_options_require_points_and_count_them():
    spec = _spec().to_dict()
    with pytest.raises(PoseModelError, match="au moins un point"):
        PoseOptions(custom_points=True).validate()
    with pytest.raises(PoseModelError, match="pas activé"):
        PoseOptions(custom_spec=spec).validate()
    options = PoseOptions(custom_points=True, custom_spec=spec).validate()
    assert options.keypoint_count == 34
    assert PoseOptions.from_json(options.to_json()) == options


def _write_patch_video(path, frames=30):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (W, H))
    for step in range(frames):
        writer.write(_frame(step))
    writer.release()


def test_pipeline_tracks_custom_point_through_a_real_video(tmp_path):
    video = tmp_path / "patch.mp4"
    _write_patch_video(video)
    options = PoseOptions(custom_points=True, custom_spec=_spec().to_dict())
    result = analyze_video(str(video), "right", 0.0, "normal", anonymize=False, pose_options=options)
    stats = result.custom_metrics["custom_cle_a_molette"]
    assert stats["tracked_ratio"] > 0.95
    expected_path = SPEED * 29 / H  # hauteurs d'image
    assert abs(stats["path_length"] - expected_path) < 0.1 * expected_path
    assert stats["hand_contact_seconds"] == 0  # aucune personne : pas de main, pas d'erreur
    assert result.keypoint_count == 34
    frames = [p for p in result.keypoint_frames if p.model == "custom_keypoints"]
    assert len(frames) >= 28 and frames[-1].keypoints[0].x * W > frames[0].keypoints[0].x * W + 40
    # l'overlay a dessiné le point (jaune) : comparaison avec la même vidéo analysée sans points
    plain = analyze_video(str(video), "right", 0.0, "normal", anonymize=False)
    assert _yellow_pixels(tmp_path, result.video_bytes) > _yellow_pixels(tmp_path, plain.video_bytes) + 20


def _yellow_pixels(tmp_path, video_bytes) -> int:
    capture = cv2.VideoCapture(str(_save(tmp_path, video_bytes)))
    ok, image = capture.read()
    assert ok
    b, g, r = (image[..., i].astype(int) for i in range(3))
    return int(((b < 80) & (g > 170) & (r > 170)).sum())


def _save(tmp_path, data):
    path = tmp_path / "annotated.mp4"
    path.write_bytes(data)
    return path
