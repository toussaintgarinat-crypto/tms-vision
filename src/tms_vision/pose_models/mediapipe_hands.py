"""MediaPipe Hands, 21 points par main : modèle complémentaire de MediaPipe Pose.

Les points sont nommés `{côté}_{doigt}_{articulation}` (`right_index_tip`, `left_thumb_cmc`...) et
`{côté}_hand_wrist` pour le poignet de la main (distinct du `left_wrist` de Pose). Le côté est
donné par la proximité avec le poignet de Pose quand il est fourni (comme `HandEstimator`) ; sinon
par l'étiquette de MediaPipe, inversée parce que les vidéos ne sont pas en miroir."""
import numpy as np

from tms_vision.landmark import Landmark
from tms_vision.pose_models.base import BasePoseModel, ModelMetadata, ModelUnavailableError
from tms_vision.pose_models.schema import FramePose, Keypoint

MODEL_ID = "mediapipe_hands_21"

# Distance maximale (fraction de la diagonale de l'image) entre le poignet de Pose et celui de
# Hands pour considérer qu'il s'agit de la même main (même valeur que hand_estimation.py).
MAX_WRIST_DISTANCE = 0.15

_FINGERS = ("thumb", "index", "middle", "ring", "pinky")
# Ordre des 21 points MediaPipe Hands : poignet, puis 4 points par doigt.
_JOINTS = {"thumb": ("cmc", "mcp", "ip", "tip")}
HAND_POINT_SUFFIXES = ("hand_wrist",) + tuple(
    f"{finger}_{joint}"
    for finger in _FINGERS
    for joint in _JOINTS.get(finger, ("mcp", "pip", "dip", "tip"))
)
assert len(HAND_POINT_SUFFIXES) == 21

# Segments à tracer (indices dans HAND_POINT_SUFFIXES) : le poignet puis chaque doigt.
HAND_CONNECTIONS = tuple(
    (0 if joint == 0 else 4 * f + joint, 4 * f + joint + 1)
    for f in range(5) for joint in range(4)
)


def hand_point_names(side: str) -> list[str]:
    return [f"{side}_{suffix}" for suffix in HAND_POINT_SUFFIXES]


class MediaPipeHandsModel(BasePoseModel):
    metadata = ModelMetadata(
        id=MODEL_ID, label="MediaPipe Hands 21", keypoint_count=42, groups=("hands",),
        description="21 points par main, en complément de Pose : gestes fins, préhension.",
        requires=("mediapipe",), primary=False,
    )

    def __init__(self, max_hands: int = 2) -> None:
        super().__init__()
        self._max_hands = max_hands
        self._hands = None

    def load(self) -> None:
        if self._hands is not None:
            return
        try:
            import mediapipe as mp
        except ImportError as error:
            raise ModelUnavailableError(
                "MediaPipe n'est pas installé (pip install 'mediapipe>=0.10.14,<0.10.30', "
                "Python 3.11)."
            ) from error
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False, max_num_hands=self._max_hands,
            min_detection_confidence=0.5, min_tracking_confidence=0.5,
        )

    def process_frame(
        self, frame: np.ndarray, frame_index: int = 0,
        pose_wrists: dict[str, Landmark] | None = None,
    ) -> list[FramePose]:
        """`pose_wrists` : poignets de Pose par côté (`{"left": Landmark, "right": Landmark}`).
        S'il est donné, seules les mains proches d'un de ces poignets sont gardées (les autres
        sont celles d'une autre personne)."""
        import cv2

        self.load()
        height, width = frame.shape[:2]
        results = self._hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not results.multi_hand_landmarks:
            self._last = []
            return self._last

        diagonal = float(np.hypot(width, height))
        candidates = []  # (distance, index de main, côté)
        sides_by_hand: dict[int, tuple[str, float]] = {}
        for index, hand in enumerate(results.multi_hand_landmarks):
            label = results.multi_handedness[index].classification[0]
            if pose_wrists:
                wrist = hand.landmark[0]
                for side, pose_wrist in pose_wrists.items():
                    distance = float(np.hypot((wrist.x - pose_wrist.x) * width / diagonal,
                                              (wrist.y - pose_wrist.y) * height / diagonal))
                    if distance < MAX_WRIST_DISTANCE:
                        candidates.append((distance, index, side))
            else:
                # Image non miroir : l'étiquette « Left » de MediaPipe est la main droite.
                sides_by_hand[index] = ("right" if label.label == "Left" else "left", label.score)

        if pose_wrists:
            taken_sides: set[str] = set()
            for distance, index, side in sorted(candidates):
                if index in sides_by_hand or side in taken_sides:
                    continue
                score = results.multi_handedness[index].classification[0].score
                sides_by_hand[index] = (side, score)
                taken_sides.add(side)

        keypoints: list[Keypoint] = []
        used_sides: set[str] = set()
        for index, (side, score) in sorted(sides_by_hand.items()):
            if side in used_sides:
                continue
            used_sides.add(side)
            for name, point in zip(hand_point_names(side), results.multi_hand_landmarks[index].landmark):
                keypoints.append(Keypoint(name=name, x=point.x, y=point.y, z=point.z,
                                          confidence=score, visibility=score))
        self._last = [FramePose(frame=frame_index, model=MODEL_ID, keypoints=keypoints)] if keypoints else []
        return self._last

    def close(self) -> None:
        if self._hands is not None:
            self._hands.close()
            self._hands = None
