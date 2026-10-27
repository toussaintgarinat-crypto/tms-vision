"""Options de modèle de pose d'une analyse (sélecteur de l'interface, paramètres de l'API)."""
import json
from dataclasses import asdict, dataclass

from tms_vision.pose_models.base import ModelUnavailableError, PoseModelError
from tms_vision.pose_models.registry import DEFAULT_MODEL, available_models

# Fonctions prévues mais pas encore branchées dans le pipeline : refusées explicitement plutôt
# qu'ignorées en silence (une analyse ne doit jamais prétendre avoir mesuré ce qu'elle n'a pas mesuré).
# Retirer une entrée au fur et à mesure des étapes (whole-body : étape 5, custom : étape 6).
NOT_YET_AVAILABLE = {
    "enable_wholebody": "le modèle whole-body",
    "custom_points": "les points personnalisés",
}


@dataclass(frozen=True)
class PoseOptions:
    pose_model: str = DEFAULT_MODEL
    enable_hands: bool = False
    enable_wholebody: bool = False
    enable_feet: bool = False
    enable_face: bool = False
    custom_points: bool = False

    @property
    def keypoint_count(self) -> int:
        """Points par personne : 33 (Pose) + 42 (deux mains) quand les mains sont activées."""
        return 33 + (42 if self.enable_hands else 0)

    @property
    def is_default(self) -> bool:
        return self == PoseOptions()

    def validate(self) -> "PoseOptions":
        """Lève `PoseModelError` (modèle inconnu) ou `ModelUnavailableError` (non installé ou
        pas encore disponible). Renvoie l'objet pour pouvoir chaîner."""
        known = {m["id"]: m for m in available_models()}
        if self.pose_model not in known:
            raise PoseModelError(
                f"Modèle de pose inconnu : {self.pose_model!r} (disponibles : {', '.join(known)})"
            )
        for option, what in NOT_YET_AVAILABLE.items():
            if getattr(self, option):
                raise ModelUnavailableError(f"{what[0].upper()}{what[1:]} n'est pas encore disponible.")
        if (self.enable_feet or self.enable_face) and not self.enable_wholebody:
            raise PoseModelError(
                "Les options pieds et visage nécessitent le modèle whole-body (enable_wholebody)."
            )
        if not known[self.pose_model]["installed"]:
            raise ModelUnavailableError(f"Le modèle {self.pose_model!r} n'est pas installé.")
        return self

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str | None) -> "PoseOptions":
        if not text:
            return cls()
        data = json.loads(text)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
