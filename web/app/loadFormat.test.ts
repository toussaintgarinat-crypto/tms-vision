import { describe, expect, it } from "vitest";

import {
  LoadInfo,
  buildLoadRequest,
  effectiveKg,
  formatLoad,
  formatScoreRange,
  isVideoBadgeStale,
} from "./loadFormat";

function load(overrides: Partial<LoadInfo> = {}): LoadInfo {
  return {
    kind: "exact",
    kg: 0,
    kg_min: null,
    kg_max: null,
    original_load_kg: 0,
    score_range: null,
    ...overrides,
  };
}

const RANGE = {
  kind: "range" as const,
  kg: null,
  kg_min: 8,
  kg_max: 12,
  score_range: {
    low: { max_score: 4, average_score: 4 },
    high: { max_score: 6, average_score: 6 },
  },
};

describe("formatLoad", () => {
  it("formats each kind", () => {
    expect(formatLoad(load({ kind: "none", kg: null }))).toBe("Aucun poids");
    expect(formatLoad(load({ kg: 12 }))).toBe("12 kg");
    expect(formatLoad(load({ kg: 7.5 }))).toBe("7,5 kg");
    expect(formatLoad(load(RANGE))).toBe("8 à 12 kg");
  });

  it("collapses a degenerate range to a single value", () => {
    expect(formatLoad(load({ kind: "range", kg: null, kg_min: 5, kg_max: 5 }))).toBe("5 kg");
  });
});

describe("effectiveKg", () => {
  it("is 0 without load, the value when exact, the upper bound for a range", () => {
    expect(effectiveKg(load({ kind: "none", kg: null }))).toBe(0);
    expect(effectiveKg(load({ kg: 12 }))).toBe(12);
    expect(effectiveKg(load(RANGE))).toBe(12);
  });
});

describe("formatScoreRange", () => {
  it("shows an interval only when the two bounds give different scores", () => {
    expect(formatScoreRange(6, load(RANGE))).toBe("4 à 6 selon la charge");
  });

  it("shows a single score when both bounds agree or there is no range", () => {
    const sameScores = load({
      ...RANGE,
      score_range: { low: { max_score: 5, average_score: 5 }, high: { max_score: 5, average_score: 5 } },
    });
    expect(formatScoreRange(5, sameScores)).toBe("5");
    expect(formatScoreRange(3, load({ kg: 10 }))).toBe("3");
  });
});

describe("isVideoBadgeStale", () => {
  it("is false while the load equals the one used for the burned-in badge", () => {
    expect(isVideoBadgeStale(load({ kg: 0, original_load_kg: 0 }))).toBe(false);
  });

  it("is true once the effective load differs from the original", () => {
    expect(isVideoBadgeStale(load({ kg: 15, original_load_kg: 0 }))).toBe(true);
    expect(isVideoBadgeStale(load({ ...RANGE, original_load_kg: 12 }))).toBe(false);
    expect(isVideoBadgeStale(load({ ...RANGE, original_load_kg: 0 }))).toBe(true);
  });
});

describe("buildLoadRequest", () => {
  it("builds each request kind", () => {
    expect(buildLoadRequest("none", "", "", "")).toEqual({ ok: true, request: { kind: "none" } });
    expect(buildLoadRequest("exact", "12", "", "")).toEqual({
      ok: true,
      request: { kind: "exact", kg: 12 },
    });
    expect(buildLoadRequest("range", "", "8", "12")).toEqual({
      ok: true,
      request: { kind: "range", kg_min: 8, kg_max: 12 },
    });
  });

  it("accepts a decimal comma and zero", () => {
    expect(buildLoadRequest("exact", "7,5", "", "")).toEqual({
      ok: true,
      request: { kind: "exact", kg: 7.5 },
    });
    expect(buildLoadRequest("exact", "0", "", "")).toEqual({
      ok: true,
      request: { kind: "exact", kg: 0 },
    });
  });

  it("rejects an empty, non numeric, negative or too heavy exact weight", () => {
    for (const text of ["", "  ", "abc", "-1", "501"]) {
      const result = buildLoadRequest("exact", text, "", "");
      expect(result.ok, text).toBe(false);
    }
  });

  it("rejects incomplete, negative, too heavy or inverted ranges", () => {
    const cases: [string, string][] = [["8", ""], ["", "12"], ["-1", "5"], ["1", "501"], ["12", "8"]];
    for (const [low, high] of cases) {
      const result = buildLoadRequest("range", "", low, high);
      expect(result.ok, `${low}-${high}`).toBe(false);
    }
  });

  it("explains an inverted range in French", () => {
    const result = buildLoadRequest("range", "", "12", "8");
    expect(result).toEqual({ ok: false, error: "La borne basse ne peut pas dépasser la borne haute." });
  });

  it("accepts a degenerate range", () => {
    expect(buildLoadRequest("range", "", "5", "5").ok).toBe(true);
  });
});
