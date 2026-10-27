"""Indicateurs des points personnalisés : suivi, déplacement, vitesse, et contact avec la main.

Les distances sont exprimées en hauteurs d'image (indépendantes de la résolution, pas en mètres :
la vidéo n'est pas calibrée). « À la main » = à moins de CONTACT_DISTANCE d'un poignet de Pose ; seuil
non calibré. Module pur."""
import math

CONTACT_DISTANCE = 0.06  # hauteurs d'image


class CustomPointsAccumulator:
    def __init__(self, point_names: list[str]) -> None:
        self._names = list(point_names)
        self._frames = 0
        self._tracked = {n: 0 for n in self._names}
        self._path = {n: 0.0 for n in self._names}
        self._max_speed = {n: 0.0 for n in self._names}
        self._contact = {n: 0.0 for n in self._names}
        self._last: dict[str, tuple[float, float, float]] = {}  # nom -> (t, x, y)
        self._last_ts: float | None = None

    def update(
        self, timestamp: float, aspect: float, points: dict[str, tuple[float, float]],
        hands: list[tuple[float, float]],
    ) -> None:
        """`points` : positions normalisées des points suivis cette image ; `hands` : positions
        normalisées des poignets visibles ; `aspect` = largeur / hauteur de l'image."""
        dt = (timestamp - self._last_ts) if self._last_ts is not None else 0.0
        self._frames += 1
        self._last_ts = timestamp
        for name in self._names:
            if name not in points:
                self._last.pop(name, None)  # ne pas relier une position à une autre après un trou
                continue
            x, y = points[name]
            self._tracked[name] += 1
            if name in self._last:
                t0, x0, y0 = self._last[name]
                step = math.hypot((x - x0) * aspect, y - y0)
                self._path[name] += step
                if timestamp > t0:
                    self._max_speed[name] = max(self._max_speed[name], step / (timestamp - t0))
            self._last[name] = (timestamp, x, y)
            if any(math.hypot((x - hx) * aspect, y - hy) <= CONTACT_DISTANCE for hx, hy in hands):
                self._contact[name] += max(dt, 0.0)

    def summary(self) -> dict:
        return {
            name: {
                "tracked_frame_count": self._tracked[name],
                "tracked_ratio": round(self._tracked[name] / self._frames, 3) if self._frames else 0.0,
                "path_length": round(self._path[name], 3),
                "max_speed": round(self._max_speed[name], 3),
                "hand_contact_seconds": round(self._contact[name], 2),
            }
            for name in self._names
        }
