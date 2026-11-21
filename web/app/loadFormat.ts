import type { MessageRef, TFunction } from "./i18n/translate";

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

// `tag` : étiquette BCP 47 de la langue (« fr-FR »), pour la virgule ou le point décimal.
function formatKg(value: number, tag: string): string {
  return value.toLocaleString(tag, { maximumFractionDigits: 1 });
}

export function formatLoad(load: LoadInfo, t: TFunction, tag: string): string {
  if (load.kind === "none") return t("load.kind.none");
  if (load.kind === "exact") return t("load.kg", { value: formatKg(load.kg ?? 0, tag) });
  const low = load.kg_min ?? 0;
  const high = load.kg_max ?? 0;
  return low === high
    ? t("load.kg", { value: formatKg(high, tag) })
    : t("load.kgRange", { low: formatKg(low, tag), high: formatKg(high, tag) });
}

// Poids qui a servi aux valeurs stockées : le cas défavorable (borne haute).
export function effectiveKg(load: LoadInfo): number {
  if (load.kind === "none") return 0;
  if (load.kind === "exact") return load.kg ?? 0;
  return load.kg_max ?? 0;
}

export function formatScoreRange(maxScore: number, load: LoadInfo, t: TFunction): string {
  const range = load.score_range;
  if (range && range.low.max_score !== range.high.max_score) {
    return t("load.scoreRange", { low: range.low.max_score, high: range.high.max_score });
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
): { ok: true; request: LoadRequest } | { ok: false; error: MessageRef } {
  if (kind === "none") return { ok: true, request: { kind: "none" } };

  if (kind === "exact") {
    const kg = parseKg(kgText);
    if (kg === null) return { ok: false, error: { key: "load.error.needWeight" } };
    if (kg < 0) return { ok: false, error: { key: "load.error.negative" } };
    if (kg > MAX_LOAD_KG) return { ok: false, error: { key: "load.error.tooHeavy", vars: { max: MAX_LOAD_KG } } };
    return { ok: true, request: { kind: "exact", kg } };
  }

  const low = parseKg(minText);
  const high = parseKg(maxText);
  if (low === null || high === null) {
    return { ok: false, error: { key: "load.error.needBounds" } };
  }
  if (low < 0 || high < 0) return { ok: false, error: { key: "load.error.boundsNegative" } };
  if (low > MAX_LOAD_KG || high > MAX_LOAD_KG) {
    return { ok: false, error: { key: "load.error.boundTooHeavy", vars: { max: MAX_LOAD_KG } } };
  }
  if (low > high) {
    return { ok: false, error: { key: "load.error.inverted" } };
  }
  return { ok: true, request: { kind: "range", kg_min: low, kg_max: high } };
}
