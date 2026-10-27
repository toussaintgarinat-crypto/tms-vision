"""Options de modèle de pose d'une analyse (sélecteur de l'interface, paramètres de l'API)."""
import json
from dataclasses import asdict, dataclass, replace

from tms_vision.pose_models.base import ModelUnavailableError, PoseModelError
from tms_vision.pose_models.custom_keypoints import CustomSpec
from tms_vision.pose_models.registry import DEFAULT_MODEL, available_models
from tms_vision.pose_models.rtmpose_wholebody import MODEL_ID as WHOLEBODY_MODEL, keypoint_count

@dataclass(frozen=True)
class PoseOptions:
    pose_model: str = DEFAULT_MODEL
    enable_hands: bool = False
    enable_wholebody: bool = False
    enable_feet: bool = False
    enable_face: bool = False
    custom_points: bool = False
    # Points à suivre (voir custom_keypoints.CustomSpec.to_dict) : requis avec `custom_points`.
    custom_spec: dict | None = None

    @property
    def uses_wholebody(self) -> bool:
        return self.enable_wholebody or self.pose_model == WHOLEBODY_MODEL

    @property
    def keypoint_count(self) -> int:
        """Points par personne : 33 (Pose) + 42 (deux mains) ; en whole-body, le corps (17) plus
        les groupes demandés (mains 42, pieds 6, visage 68)."""
        if self.uses_wholebody:
            base = keypoint_count(self.enable_hands, self.enable_feet, self.enable_face)
            return base + (len(self.custom_spec["points"]) if self.custom_spec else 0)
        base = 33 + (42 if self.enable_hands else 0)
        return base + (len(self.custom_spec["points"]) if self.custom_spec else 0)

    @property
    def is_default(self) -> bool:
        return self == PoseOptions()

    def validate(self) -> "PoseOptions":
        """Lève `PoseModelError` (modèle inconnu) ou `ModelUnavailableError` (non installé ou
        pas encore disponible). Renvoie les options normalisées (whole-body : modèle et drapeau
        cohérents) ; à utiliser à la place de l'objet d'origine."""
        # `enable_wholebody` et `pose_model=rtmpose_wholebody_133` désignent le même modèle.
        options = self
        if self.uses_wholebody:
            options = replace(self, pose_model=WHOLEBODY_MODEL, enable_wholebody=True)
        known = {m["id"]: m for m in available_models()}
        if self.pose_model not in known:
            raise PoseModelError(
                f"Modèle de pose inconnu : {self.pose_model!r} (disponibles : {', '.join(known)})"
            )
        if not known[self.pose_model]["primary"]:
            raise PoseModelError(
                f"{self.pose_model!r} est un modèle complémentaire : activez-le avec une option "
                "(enable_hands), ce n'est pas un modèle principal."
            )
        if options.custom_points:
            if not options.custom_spec:
                raise PoseModelError("Points personnalisés : placez au moins un point (custom_points_json).")
            options = replace(options, custom_spec=CustomSpec.from_dict(options.custom_spec).to_dict())
        elif options.custom_spec:
            raise PoseModelError("Des points personnalisés sont fournis mais custom_points n'est pas activé.")
        if (options.enable_feet or options.enable_face) and not options.enable_wholebody:
            raise PoseModelError(
                "Les options pieds et visage nécessitent le modèle whole-body (enable_wholebody)."
            )
        if not known[options.pose_model]["installed"]:
            hint = (" (pip install -r requirements-wholebody.txt)" if options.uses_wholebody else "")
            raise ModelUnavailableError(f"Le modèle {options.pose_model!r} n'est pas installé{hint}.")
        return options

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str | None) -> "PoseOptions":
        if not text:
            return cls()
        data = json.loads(text)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
