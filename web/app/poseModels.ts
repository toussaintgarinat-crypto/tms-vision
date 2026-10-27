/**
 * Réglages du modèle de pose d'une analyse (sélecteur de la page d'analyse) : le choix du modèle,
 * les options mains / pieds / visage, et les points personnalisés. Logique pure : l'API les reçoit
 * sous forme de champs de formulaire (voir `poseFormFields`) ; le backend refuse toute option
 * invalide (422), la validation d'ici ne sert qu'à prévenir plus tôt.
 */

export type PoseChoice = "mediapipe_pose_33" | "mediapipe_pose_hands" | "rtmpose_wholebody" | "custom_keypoints";

export type CustomPoint = { name: string; x: number; y: number };

export type PoseSettings = {
  choice: PoseChoice;
  hands: boolean;
  feet: boolean;
  face: boolean;
  customEnabled: boolean;
  customPoints: CustomPoint[];
  customReferenceTime: number;
};

export const MAX_CUSTOM_POINTS = 10;
export const WHOLEBODY_MODEL_ID = "rtmpose_wholebody_133";
export const WHOLEBODY_INSTALL_HINT = "pip install -r requirements-wholebody.txt";

export const POSE_CHOICES: { value: PoseChoice; label: string; description: string }[] = [
  {
    value: "mediapipe_pose_33",
    label: "MediaPipe Pose 33",
    description: "33 points, rapide et léger : score RULA et analyse ergonomique globale (par défaut).",
  },
  {
    value: "mediapipe_pose_hands",
    label: "MediaPipe Pose + Hands",
    description: "Ajoute 21 points par main : préhensions, flexion des doigts, gestes répétitifs.",
  },
  {
    value: "rtmpose_wholebody",
    label: "RTMPose / DWPose Whole-body",
    description: "Jusqu'à 133 points (corps, pieds, mains, visage). Plus lent, en 2D : sans avatar 3D.",
  },
  {
    value: "custom_keypoints",
    label: "Custom keypoints",
    description: "Points que vous placez sur un outil, une caisse, une zone... et qui sont suivis dans la vidéo.",
  },
];

export const DEFAULT_POSE_SETTINGS: PoseSettings = {
  choice: "mediapipe_pose_33",
  hands: false,
  feet: false,
  face: false,
  customEnabled: false,
  customPoints: [],
  customReferenceTime: 0,
};

/** Réglages obtenus en choisissant un modèle : chaque choix règle les options qu'il implique. */
export function applyChoice(settings: PoseSettings, choice: PoseChoice): PoseSettings {
  const wholebody = choice === "rtmpose_wholebody";
  return {
    ...settings,
    choice,
    hands: choice === "mediapipe_pose_hands" || wholebody ? true : choice === "custom_keypoints" ? settings.hands : false,
    feet: wholebody ? true : false,
    face: false,
    customEnabled: choice === "custom_keypoints" ? true : wholebody ? settings.customEnabled : false,
  };
}

export function isWholebody(settings: PoseSettings): boolean {
  return settings.choice === "rtmpose_wholebody";
}

export function expectedKeypointCount(settings: PoseSettings): number {
  const custom = settings.customEnabled ? settings.customPoints.length : 0;
  if (isWholebody(settings)) {
    return 17 + (settings.hands ? 42 : 0) + (settings.feet ? 6 : 0) + (settings.face ? 68 : 0) + custom;
  }
  return 33 + (settings.hands ? 42 : 0) + custom;
}

/** Message d'erreur à afficher avant l'envoi, ou `null` si les réglages sont valides. */
export function validatePoseSettings(settings: PoseSettings): string | null {
  if (settings.customEnabled && settings.customPoints.length === 0) {
    return "Placez au moins un point personnalisé sur l'image, ou décochez cette option.";
  }
  if (settings.customPoints.length > MAX_CUSTOM_POINTS) {
    return `Au plus ${MAX_CUSTOM_POINTS} points personnalisés.`;
  }
  return null;
}

/** Champs de formulaire de POST /analyses et /uploads/{id}/complete. */
export function poseFormFields(settings: PoseSettings): Record<string, string> {
  const wholebody = isWholebody(settings);
  const fields: Record<string, string> = {
    pose_model: wholebody ? WHOLEBODY_MODEL_ID : "mediapipe_pose_33",
    enable_wholebody: String(wholebody),
    enable_hands: String(settings.hands),
    enable_feet: String(wholebody && settings.feet),
    enable_face: String(wholebody && settings.face),
    custom_points: String(settings.customEnabled),
  };
  if (settings.customEnabled) {
    fields.custom_points_json = JSON.stringify({
      reference_time_seconds: settings.customReferenceTime,
      points: settings.customPoints.map(({ name, x, y }) => ({ name, x, y })),
    });
  }
  return fields;
}

/**
 * Position d'un clic dans une image affichée -> coordonnées normalisées (0 à 1) de l'image,
 * ou `null` hors de l'image.
 */
export function clickToNormalized(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
): { x: number; y: number } | null {
  if (rect.width <= 0 || rect.height <= 0) return null;
  const x = (clientX - rect.left) / rect.width;
  const y = (clientY - rect.top) / rect.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  return { x: Number(x.toFixed(4)), y: Number(y.toFixed(4)) };
}

export function defaultPointName(points: CustomPoint[]): string {
  const taken = new Set(points.map((p) => p.name.trim().toLowerCase()));
  for (let n = points.length + 1; n <= MAX_CUSTOM_POINTS + points.length + 1; n++) {
    const candidate = `point ${n}`;
    if (!taken.has(candidate)) return candidate;
  }
  return `point ${points.length + 1}`;
}

// Couleurs des groupes de points sur la vidéo annotée (mêmes teintes que GROUP_COLORS, overlay.py).
export const GROUP_LEGEND: { group: string; label: string; color: string }[] = [
  { group: "body", label: "Corps", color: "#ffffff" },
  { group: "hands", label: "Mains", color: "#ffa500" },
  { group: "feet", label: "Pieds", color: "#00c8ff" },
  { group: "face", label: "Visage", color: "#ff78c8" },
  { group: "custom", label: "Points personnalisés", color: "#e6e600" },
];

export type PoseModelInfo = {
  id: string;
  label: string;
  keypoint_count: number;
  installed: boolean;
  primary: boolean;
  default: boolean;
};

export type StoredPoseOptions = {
  pose_model?: string;
  enable_hands?: boolean;
  enable_wholebody?: boolean;
  enable_feet?: boolean;
  enable_face?: boolean;
  custom_points?: boolean;
};

/** Groupes de points présents d'après les options d'une analyse (pour la légende des couleurs). */
export function groupsForOptions(options: StoredPoseOptions | null | undefined): string[] {
  const groups = ["body"];
  if (options?.enable_hands) groups.push("hands");
  if (options?.enable_wholebody || options?.pose_model === WHOLEBODY_MODEL_ID) {
    if (options?.enable_feet) groups.push("feet");
    if (options?.enable_face) groups.push("face");
  }
  if (options?.custom_points) groups.push("custom");
  return groups;
}

export function poseModelLabel(modelId: string | null | undefined): string {
  if (modelId === WHOLEBODY_MODEL_ID) return "RTMPose Whole-body";
  return "MediaPipe Pose 33";
}
