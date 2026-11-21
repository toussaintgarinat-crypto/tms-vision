/** Mise en forme du panneau « modèle de pose » d'une analyse. Fonctions pures. */

import type { TFunction } from "./i18n/translate";

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

export function formatPercent(ratio: number | null | undefined, t: TFunction): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "—";
  return t("format.percent", { value: Math.round(ratio * 100) });
}

export function formatDegrees(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value)}°`;
}

// `tag` : étiquette BCP 47 de la langue, pour la virgule ou le point décimal.
export function formatDecimal(value: number, tag: string, digits = 1): string {
  return value.toLocaleString(tag, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatSeconds(value: number, tag: string): string {
  return `${formatDecimal(value, tag)} s`;
}

/** `custom_cle_a_molette` -> `cle a molette` (nom affiché, sans préfixe ni tirets bas). */
export function customDisplayName(key: string): string {
  return key.replace(/^custom_/, "").replace(/_/g, " ");
}

export function handSideLabel(side: string, t: TFunction): string {
  return side === "left" ? t("hand.left") : side === "right" ? t("hand.right") : side;
}

/** Libellé qualitatif de la confiance moyenne (0-1) : l'échelle dépend du modèle, donc prudente. */
export function confidenceLabel(confidence: number | null | undefined, t: TFunction): string {
  if (confidence === null || confidence === undefined) return t("confidence.none");
  if (confidence >= 0.8) return t("confidence.high");
  if (confidence >= 0.6) return t("confidence.fair");
  return t("confidence.low");
}

/** Cadence de préhension : « 12 / min », ou « — » quand la vidéo est trop courte pour la calculer. */
export function formatRate(perMinute: number | null | undefined, tag: string): string {
  return perMinute === null || perMinute === undefined ? "—" : `${formatDecimal(perMinute, tag)} / min`;
}
