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

export type BilanReportDeclared = {
  task_id: string;
  name: string;
  source: "practitioner" | "patient";
  zones: Zone[];
  zone_cycles: Partial<Record<Zone, number>>;
  measured_cycles_per_minute: Partial<Record<Zone, number | null>>;
};

export type BilanReportTask = {
  task_id: string;
  name: string;
  source: "practitioner" | "patient";
  zones: Zone[];
  activity_hours: number;
  time_slots: { start: string; end: string }[] | null;
  zone_cycles: Partial<Record<Zone, number>>;
  warnings: string[];
};

export type BilanReportAnalysis = {
  analysis_id: string;
  source: "measured";
  declared: BilanReportDeclared[];
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
  tasks: BilanReportTask[];
  warnings: string[];
};

export type BilanItem = {
  analysis_id: string;
  activity_hours: number;
  representative: boolean;
};

export type BilanTask = {
  id: string;
  name: string;
  zones: Zone[];
  activity_hours: number;
  time_slots: { start: string; end: string }[] | null;
  days_per_week: number | null;
  zone_cycles: Partial<Record<Zone, number>>;
  cycle_seconds: number | null;
  static_seconds: number | null;
  load_kg: number | null;
  analysis_id: string | null;
  source: "practitioner" | "patient";
  notes: string | null;
  workstation: string | null;
  breaks: string | null;
};

export type StoredBilan = {
  id: string;
  created_at: string;
  label: string | null;
  workday_hours: number;
  // Date d'archivage ; null pour un bilan actif.
  archived_at?: string | null;
  // Dossier (par exemple une entreprise) où le bilan est rangé ; null : sans dossier.
  folder_id?: string | null;
  items?: BilanItem[];
  tasks?: BilanTask[];
};

export type BilanFolder = {
  id: string;
  created_at: string;
  name: string;
};
