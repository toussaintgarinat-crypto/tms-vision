export const ZONES = ["neck", "trunk", "upper_arm", "lower_arm", "hand", "foot"] as const;
export type Zone = (typeof ZONES)[number];

export const ZONE_LABELS: Record<Zone, string> = {
  neck: "Cou",
  trunk: "Tronc",
  upper_arm: "Épaule / bras",
  lower_arm: "Avant-bras / coude",
  hand: "Main / poignet",
  foot: "Pied / cheville",
};

export type ZoneRecurrence = {
  cycles: number;
  cycles_per_minute: number | null;
  mean_cycle_seconds: number | null;
  longest_static_seconds: number;
  elevated_seconds: number;
  assessment: "repetitive" | "not_repetitive" | null;
};

export type AnalysisRecurrence = {
  sample_seconds: number;
  thresholds_calibrated: boolean;
  zones: Record<Zone, ZoneRecurrence>;
};

export type BilanReportAnalysis = {
  analysis_id: string;
  activity_hours: number;
  representative: boolean;
  included: boolean;
  sample_seconds: number;
  warnings: string[];
  recurrence: AnalysisRecurrence;
};

export type BilanReport = {
  workday_hours: number;
  documented_hours: number;
  undocumented_hours: number;
  thresholds_calibrated: boolean;
  zones: Record<Zone, { projected_cycles: number; projected_elevated_hours: number }>;
  analyses: BilanReportAnalysis[];
  warnings: string[];
};

export type BilanItem = {
  analysis_id: string;
  activity_hours: number;
  representative: boolean;
};

export type StoredBilan = {
  id: string;
  created_at: string;
  label: string | null;
  workday_hours: number;
  items?: BilanItem[];
};
