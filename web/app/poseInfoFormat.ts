/** Mise en forme du panneau « modèle de pose » d'une analyse. Fonctions pures. */

export type DetectionQuality = {
  frames_with_points: number;
  avg_keypoints_per_frame: number;
  avg_confidence: number | null;
};

export type HandSideMetrics = {
  detected_frame_count: number;
  detection_ratio: number;
  finger_curl_mean_deg: number | null;
  finger_curl_max_deg: number | null;
  grasp_count: number;
  grasp_seconds: number;
  grasps_per_minute: number | null;
  repetitive: boolean;
};

export type CustomPointMetrics = {
  tracked_frame_count: number;
  tracked_ratio: number;
  path_length: number;
  max_speed: number;
  hand_contact_seconds: number;
};

export function formatPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "—";
  return `${Math.round(ratio * 100)} %`;
}

export function formatDegrees(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value)}°`;
}

export function formatSeconds(value: number): string {
  return `${value.toFixed(1).replace(".", ",")} s`;
}

/** `custom_cle_a_molette` -> `cle a molette` (nom affiché, sans préfixe ni tirets bas). */
export function customDisplayName(key: string): string {
  return key.replace(/^custom_/, "").replace(/_/g, " ");
}

export function handSideLabel(side: string): string {
  return side === "left" ? "Main gauche" : side === "right" ? "Main droite" : side;
}

/** Libellé qualitatif de la confiance moyenne (0-1) : l'échelle dépend du modèle, donc prudente. */
export function confidenceLabel(confidence: number | null | undefined): string {
  if (confidence === null || confidence === undefined) return "aucun point détecté";
  if (confidence >= 0.8) return "élevée";
  if (confidence >= 0.6) return "correcte";
  return "faible";
}

/** Cadence de préhension : « 12 / min », ou « — » quand la vidéo est trop courte pour la calculer. */
export function formatRate(perMinute: number | null | undefined): string {
  return perMinute === null || perMinute === undefined ? "—" : `${perMinute.toFixed(1).replace(".", ",")} / min`;
}
