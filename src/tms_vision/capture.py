"""Source de frames vidéo : fichier ou webcam."""
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np


@dataclass
class Frame:
    index: int
    timestamp_seconds: float
    image: np.ndarray


class FrameSource:
    """Fournit des frames depuis la webcam (source="webcam") ou un fichier vidéo."""

    def __init__(self, source: str):
        if source != "webcam" and not Path(source).exists():
            raise FileNotFoundError(f"Fichier vidéo introuvable : {source}")

        capture_target = 0 if source == "webcam" else source
        self._capture = cv2.VideoCapture(capture_target)
        if not self._capture.isOpened():
            raise RuntimeError(f"Impossible d'ouvrir la source vidéo : {source}")

        self._fps = self._capture.get(cv2.CAP_PROP_FPS) or 30.0

    def fps(self) -> float:
        return self._fps

    def __iter__(self) -> Iterator[Frame]:
        index = 0
        while True:
            ok, image = self._capture.read()
            if not ok:
                break
            timestamp_seconds = index / self._fps
            yield Frame(index=index, timestamp_seconds=timestamp_seconds, image=image)
            index += 1

    def release(self) -> None:
        self._capture.release()
