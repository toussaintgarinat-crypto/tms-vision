"""Anonymisation des visages : pixellisation des têtes avant l'écriture de la vidéo annotée
(voir docs/superpowers/specs/2026-10-22-face-blur-design.md).

Principe de sûreté : en cas de doute, on floute PLUS, jamais moins. Une image où l'on ne sait
pas où est la tête (pose non détectée, détecteur muet, personne entrée dans le champ) est
pixellisée en entier plutôt que laissée nette.

La position de la tête vient de deux sources, réunies :
- la pose (points du visage et des épaules de MediaPipe Pose) : sûre pour la personne analysée,
  même de profil ou de dos ;
- un détecteur de visages indépendant (voir MediaPipeFaceDetector) : couvre les AUTRES personnes
  du champ, que la pose, limitée à une seule personne, ne voit pas.

Les images brutes ne vivent qu'en mémoire pendant l'analyse ; seule l'image pixellisée est écrite
(voir pipeline.analyze_video)."""
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

FACE_LANDMARKS = (
    "NOSE",
    "LEFT_EYE_INNER", "LEFT_EYE", "LEFT_EYE_OUTER",
    "RIGHT_EYE_INNER", "RIGHT_EYE", "RIGHT_EYE_OUTER",
    "LEFT_EAR", "RIGHT_EAR", "MOUTH_LEFT", "MOUTH_RIGHT",
)

# Nombre de blocs sur la plus grande dimension : peu de blocs = irréversible à l'œil.
BLOCKS_ACROSS_REGION = 8
BLOCKS_ACROSS_FRAME = 12

# Taille de la région autour des points du visage. Marges généreuses : la pose donne le nez, les
# yeux, les oreilles et la bouche, pas le front, les cheveux ni le menton.
EXTENT_MARGIN = 1.5            # rayon = 1.5 × l'écart maximal des points au centre
EAR_DISTANCE_FACTOR = 0.9      # ou 0.9 × la distance entre les oreilles, si elles sont visibles
SHOULDER_RADIUS_FACTOR = 0.3   # plancher : 30 % de la largeur des épaules (tête ≈ 42 % de celle-ci)
SHOULDERS_ONLY_RADIUS_FACTOR = 0.45
SHOULDERS_ONLY_HEIGHT_FACTOR = 0.65   # centre de la tête au-dessus de la ligne des épaules
MIN_RADIUS_FRACTION = 0.12     # sans épaules : 12 % de la plus grande dimension de l'image
HEAD_ASPECT = 1.25             # la tête est plus haute que large
HEAD_SHIFT_UP = 0.12           # le centre des points du visage est sous le centre de la tête

DETECTOR_BOX_EXPANSION = 1.6   # un visage détecté est élargi : oreilles, cheveux, menton
BOX_ASPECT = 1.2               # la boîte d'un visage détecté est étirée vers le haut et le bas
HELD_REGION_GROWTH = 1.4       # la tête a pu bouger depuis la dernière position connue
DEFAULT_HOLD_SECONDS = 1.0


@dataclass(frozen=True)
class Region:
    """Ellipse en pixels : centre (cx, cy), demi-axes (rx, ry)."""

    cx: float
    cy: float
    rx: float
    ry: float


class FaceDetector(Protocol):
    def detect(self, image_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Boîtes (x, y, largeur, hauteur), en pixels, des visages trouvés."""

    def close(self) -> None: ...


def _head_ellipse(cx: float, cy: float, radius: float) -> Region:
    return Region(
        cx=cx, cy=cy - HEAD_SHIFT_UP * radius, rx=radius, ry=radius * HEAD_ASPECT,
    )


def head_region_from_landmarks(landmarks, width: int, height: int) -> Region | None:
    """Ellipse couvrant la tête, déduite des landmarks de pose (normalisés). None si l'on ne
    peut pas la placer (ni point du visage, ni les deux épaules)."""
    if not landmarks:
        return None

    face_points = [
        (landmarks[name].x * width, landmarks[name].y * height)
        for name in FACE_LANDMARKS if name in landmarks
    ]
    shoulder_width = None
    if "LEFT_SHOULDER" in landmarks and "RIGHT_SHOULDER" in landmarks:
        left, right = landmarks["LEFT_SHOULDER"], landmarks["RIGHT_SHOULDER"]
        shoulder_width = math.hypot((left.x - right.x) * width, (left.y - right.y) * height)

    if face_points:
        cx = sum(x for x, _ in face_points) / len(face_points)
        cy = sum(y for _, y in face_points) / len(face_points)
        extent = max(math.hypot(x - cx, y - cy) for x, y in face_points)
        radius = EXTENT_MARGIN * extent
        if "LEFT_EAR" in landmarks and "RIGHT_EAR" in landmarks:
            ears = math.hypot(
                (landmarks["LEFT_EAR"].x - landmarks["RIGHT_EAR"].x) * width,
                (landmarks["LEFT_EAR"].y - landmarks["RIGHT_EAR"].y) * height,
            )
            radius = max(radius, EAR_DISTANCE_FACTOR * ears)
        if shoulder_width:
            radius = max(radius, SHOULDER_RADIUS_FACTOR * shoulder_width)
        else:
            radius = max(radius, MIN_RADIUS_FRACTION * max(width, height))
        return _head_ellipse(cx, cy, radius)

    if shoulder_width:
        left, right = landmarks["LEFT_SHOULDER"], landmarks["RIGHT_SHOULDER"]
        mid_x = (left.x + right.x) / 2 * width
        mid_y = (left.y + right.y) / 2 * height
        dx = (right.x - left.x) * width
        dy = (right.y - left.y) * height
        norm = math.hypot(dx, dy)
        # Perpendiculaire à la ligne des épaules, orientée vers le haut de l'image.
        up_x, up_y = dy / norm, -dx / norm
        if up_y > 0:
            up_x, up_y = -up_x, -up_y
        offset = SHOULDERS_ONLY_HEIGHT_FACTOR * shoulder_width
        return _head_ellipse(
            mid_x + up_x * offset, mid_y + up_y * offset, SHOULDERS_ONLY_RADIUS_FACTOR * shoulder_width
        )
    return None


def region_from_box(box: tuple[int, int, int, int], expansion: float = DETECTOR_BOX_EXPANSION) -> Region:
    x, y, w, h = box
    return Region(
        cx=x + w / 2,
        cy=y + h / 2,
        rx=w / 2 * expansion,
        ry=h / 2 * expansion * BOX_ASPECT,
    )


def _grown(region: Region, factor: float) -> Region:
    return Region(region.cx, region.cy, region.rx * factor, region.ry * factor)


def _pixelate(crop: np.ndarray, block: int) -> np.ndarray:
    height, width = crop.shape[:2]
    small = cv2.resize(
        crop, (max(1, width // block), max(1, height // block)), interpolation=cv2.INTER_AREA
    )
    return cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)


def pixelate_regions(image_bgr: np.ndarray, regions: list[Region]) -> np.ndarray:
    """Copie de l'image où l'intérieur de chaque ellipse est pixellisé. Hors des ellipses, les
    pixels sont strictement identiques. L'image reçue n'est jamais modifiée."""
    output = image_bgr.copy()
    height, width = output.shape[:2]

    for region in regions:
        x0 = max(0, int(math.floor(region.cx - region.rx)))
        x1 = min(width, int(math.ceil(region.cx + region.rx)) + 1)
        y0 = max(0, int(math.floor(region.cy - region.ry)))
        y1 = min(height, int(math.ceil(region.cy + region.ry)) + 1)
        if x0 >= x1 or y0 >= y1:
            continue

        ys, xs = np.mgrid[y0:y1, x0:x1]
        mask = ((xs - region.cx) / region.rx) ** 2 + ((ys - region.cy) / region.ry) ** 2 <= 1.0
        block = max(2, int(round(2 * max(region.rx, region.ry) / BLOCKS_ACROSS_REGION)))
        crop = output[y0:y1, x0:x1]
        crop[mask] = _pixelate(crop, block)[mask]
    return output


def pixelate_frame(image_bgr: np.ndarray) -> np.ndarray:
    """Copie de l'image entièrement pixellisée (filet de sécurité)."""
    block = max(2, max(image_bgr.shape[:2]) // BLOCKS_ACROSS_FRAME)
    return _pixelate(image_bgr, block)


class MediaPipeFaceDetector:
    """Détecteur de visages MediaPipe (BlazeFace). Le modèle « longue portée » (1) couvre jusqu'à
    environ 5 m, adapté à un poste de travail filmé à distance ; le seuil de confiance est bas
    exprès : une fausse détection floute un objet, une non-détection laisse un visage net."""

    def __init__(self, model_selection: int = 1, min_confidence: float = 0.3):
        import mediapipe as mp

        self._detector = mp.solutions.face_detection.FaceDetection(
            model_selection=model_selection, min_detection_confidence=min_confidence
        )

    def detect(self, image_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
        height, width = image_bgr.shape[:2]
        results = self._detector.process(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        boxes = []
        for detection in results.detections or []:
            box = detection.location_data.relative_bounding_box
            boxes.append((
                int(box.xmin * width), int(box.ymin * height),
                int(box.width * width), int(box.height * height),
            ))
        return boxes

    def close(self) -> None:
        self._detector.close()


# Modèle YuNet (détecteur de visages d'OpenCV Zoo, licence MIT : voir models/LICENSE-yunet et
# NOTICE.md), embarqué pour que l'analyse reste entièrement locale.
DEFAULT_YUNET_MODEL = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"


class YuNetFaceDetector:
    """Détecteur de visages YuNet (OpenCV). Entraîné sur des visages difficiles : petits (une
    vingtaine de pixels), de trois quarts, sous un casque ou des lunettes de soleil. Complète
    BlazeFace, qui rate ces cas. Le seuil est bas exprès : une fausse détection floute un bout
    de décor, une non-détection laisse un visage net."""

    def __init__(
        self,
        model_path: Path | str = DEFAULT_YUNET_MODEL,
        score_threshold: float = 0.4,
        nms_threshold: float = 0.3,
    ):
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"Modèle YuNet introuvable : {path}")
        self.score_threshold = score_threshold
        self._size = (320, 320)
        self._detector = cv2.FaceDetectorYN.create(
            str(path), "", self._size, score_threshold, nms_threshold, 5000
        )

    def detect(self, image_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
        height, width = image_bgr.shape[:2]
        if (width, height) != self._size:
            self._detector.setInputSize((width, height))
            self._size = (width, height)
        _, faces = self._detector.detect(image_bgr)
        if faces is None:
            return []
        return [tuple(int(value) for value in face[:4]) for face in faces]

    def close(self) -> None:
        pass


class CompositeFaceDetector:
    """Réunit les visages trouvés par plusieurs détecteurs : chacun rate des cas que les autres
    voient, et en matière d'anonymisation on garde la réunion."""

    def __init__(self, detectors: list[FaceDetector]):
        self.detectors = list(detectors)

    def detect(self, image_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
        boxes: list[tuple[int, int, int, int]] = []
        for detector in self.detectors:
            boxes.extend(detector.detect(image_bgr))
        return boxes

    def close(self) -> None:
        first_error = None
        for detector in self.detectors:
            try:
                detector.close()
            except Exception as error:  # on ferme tous les détecteurs avant de signaler l'échec
                first_error = first_error or error
        if first_error is not None:
            raise first_error


def default_face_detector() -> CompositeFaceDetector:
    """Détecteur utilisé par le pipeline : BlazeFace (MediaPipe) + YuNet (OpenCV)."""
    return CompositeFaceDetector([MediaPipeFaceDetector(), YuNetFaceDetector()])


class FaceAnonymizer:
    """Anonymise une séquence d'images. Garde en mémoire la dernière position connue de la tête :
    si la pose est perdue, on continue de la flouter (élargie) pendant `hold_seconds`, puis on
    pixellise toute l'image tant qu'on ne sait plus où est la tête."""

    def __init__(
        self,
        fps: float,
        detector: FaceDetector | None = None,
        hold_seconds: float = DEFAULT_HOLD_SECONDS,
    ):
        self._detector = detector
        self.hold_frames = max(1, round(hold_seconds * fps)) if fps > 0 else 1
        self._last_region: Region | None = None
        self._missing_frames = 0

    def anonymize(self, image_bgr: np.ndarray, landmarks) -> np.ndarray:
        height, width = image_bgr.shape[:2]
        regions: list[Region] = []

        pose_region = head_region_from_landmarks(landmarks, width, height)
        if pose_region is not None:
            self._last_region = pose_region
            self._missing_frames = 0
            regions.append(pose_region)
        else:
            self._missing_frames += 1
            if self._last_region is not None and self._missing_frames <= self.hold_frames:
                regions.append(_grown(self._last_region, HELD_REGION_GROWTH))

        if self._detector is not None:
            regions.extend(region_from_box(box) for box in self._detector.detect(image_bgr))

        if not regions:
            return pixelate_frame(image_bgr)
        return pixelate_regions(image_bgr, regions)

    def close(self) -> None:
        if self._detector is not None:
            self._detector.close()
