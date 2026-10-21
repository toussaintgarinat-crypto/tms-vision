export type LoadKind = "none" | "exact" | "range";

export type ScoreSummary = { max_score: number; average_score: number };

export type LoadInfo = {
  kind: LoadKind;
  kg: number | null;
  kg_min: number | null;
  kg_max: number | null;
  // Poids utilisé pour le badge « RULA n » incrusté dans la vidéo annotée.
  original_load_kg: number;
  score_range: { low: ScoreSummary; high: ScoreSummary } | null;
};

export type LoadRequest = {
  kind: LoadKind;
  kg?: number;
  kg_min?: number;
  kg_max?: number;
};

// Même plafond que tms_vision/load.py::MAX_LOAD_KG.
export const MAX_LOAD_KG = 500;

function formatKg(value: number): string {
  return value.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
}

export function formatLoad(load: LoadInfo): string {
  if (load.kind === "none") return "Aucun poids";
  if (load.kind === "exact") return `${formatKg(load.kg ?? 0)} kg`;
  const low = load.kg_min ?? 0;
  const high = load.kg_max ?? 0;
  return low === high ? `${formatKg(high)} kg` : `${formatKg(low)} à ${formatKg(high)} kg`;
}

// Poids qui a servi aux valeurs stockées : le cas défavorable (borne haute).
export function effectiveKg(load: LoadInfo): number {
  if (load.kind === "none") return 0;
  if (load.kind === "exact") return load.kg ?? 0;
  return load.kg_max ?? 0;
}

export function formatScoreRange(maxScore: number, load: LoadInfo): string {
  const range = load.score_range;
  if (range && range.low.max_score !== range.high.max_score) {
    return `${range.low.max_score} à ${range.high.max_score} selon la charge`;
  }
  return String(maxScore);
}

export function isVideoBadgeStale(load: LoadInfo): boolean {
  return effectiveKg(load) !== load.original_load_kg;
}

function parseKg(text: string): number | null {
  if (text.trim() === "") return null;
  const value = Number(text.trim().replace(",", "."));
  return Number.isFinite(value) ? value : null;
}

// Mêmes règles que tms_vision/load.py::parse_load, pour un retour immédiat ;
// l'API reste la référence (elle renvoie un 422 lisible en cas de désaccord).
export function buildLoadRequest(
  kind: LoadKind,
  kgText: string,
  minText: string,
  maxText: string,
): { ok: true; request: LoadRequest } | { ok: false; error: string } {
  if (kind === "none") return { ok: true, request: { kind: "none" } };

  if (kind === "exact") {
    const kg = parseKg(kgText);
    if (kg === null) return { ok: false, error: "Saisissez un poids (nombre en kg)." };
    if (kg < 0) return { ok: false, error: "Le poids ne peut pas être négatif." };
    if (kg > MAX_LOAD_KG) return { ok: false, error: `Le poids dépasse ${MAX_LOAD_KG} kg.` };
    return { ok: true, request: { kind: "exact", kg } };
  }

  const low = parseKg(minText);
  const high = parseKg(maxText);
  if (low === null || high === null) {
    return { ok: false, error: "Saisissez les deux bornes de la fourchette." };
  }
  if (low < 0 || high < 0) return { ok: false, error: "Les bornes ne peuvent pas être négatives." };
  if (low > MAX_LOAD_KG || high > MAX_LOAD_KG) {
    return { ok: false, error: `Une borne dépasse ${MAX_LOAD_KG} kg.` };
  }
  if (low > high) {
    return { ok: false, error: "La borne basse ne peut pas dépasser la borne haute." };
  }
  return { ok: true, request: { kind: "range", kg_min: low, kg_max: high } };
}
