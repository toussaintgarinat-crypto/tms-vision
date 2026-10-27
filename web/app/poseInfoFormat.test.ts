import { describe, expect, it } from "vitest";

import {
  confidenceLabel,
  customDisplayName,
  formatDegrees,
  formatPercent,
  formatRate,
  formatSeconds,
  handSideLabel,
} from "./poseInfoFormat";

describe("poseInfoFormat", () => {
  it("formate les pourcentages et les valeurs absentes", () => {
    expect(formatPercent(0.944)).toBe("94 %");
    expect(formatPercent(0)).toBe("0 %");
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatPercent(Number.NaN)).toBe("—");
  });

  it("formate degrés, secondes et cadences à la française", () => {
    expect(formatDegrees(77.5)).toBe("78°");
    expect(formatDegrees(null)).toBe("—");
    expect(formatSeconds(3.57)).toBe("3,6 s");
    expect(formatRate(20.1)).toBe("20,1 / min");
    expect(formatRate(null)).toBe("—");
  });

  it("nettoie le nom d'un point personnalisé et libelle les mains", () => {
    expect(customDisplayName("custom_cle_a_molette")).toBe("cle a molette");
    expect(customDisplayName("bobine")).toBe("bobine");
    expect(handSideLabel("left")).toBe("Main gauche");
    expect(handSideLabel("right")).toBe("Main droite");
  });

  it("qualifie la confiance sans inventer de valeur quand rien n'est détecté", () => {
    expect(confidenceLabel(0.9)).toBe("élevée");
    expect(confidenceLabel(0.7)).toBe("correcte");
    expect(confidenceLabel(0.3)).toBe("faible");
    expect(confidenceLabel(null)).toBe("aucun point détecté");
  });
});
