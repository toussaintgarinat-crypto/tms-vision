import { describe, expect, it } from "vitest";

import { translator } from "./i18n/catalog";
import {
  confidenceLabel,
  customDisplayName,
  formatDegrees,
  formatPercent,
  formatRate,
  formatSeconds,
  handSideLabel,
} from "./poseInfoFormat";

const tFr = translator("fr");
const tEn = translator("en");

describe("poseInfoFormat", () => {
  it("formate les pourcentages et les valeurs absentes", () => {
    expect(formatPercent(0.944, tFr)).toBe("94 %");
    expect(formatPercent(0, tFr)).toBe("0 %");
    expect(formatPercent(null, tFr)).toBe("—");
    expect(formatPercent(undefined, tFr)).toBe("—");
    expect(formatPercent(Number.NaN, tFr)).toBe("—");
  });

  it("formate degrés, secondes et cadences à la française", () => {
    expect(formatDegrees(77.5)).toBe("78°");
    expect(formatDegrees(null)).toBe("—");
    expect(formatSeconds(3.57, "fr-FR")).toBe("3,6 s");
    expect(formatRate(20.1, "fr-FR")).toBe("20,1 / min");
    expect(formatRate(null, "fr-FR")).toBe("—");
  });

  it("suit la langue pour les séparateurs, les pourcentages et les libellés", () => {
    expect(formatSeconds(3.57, "en-GB")).toBe("3.6 s");
    expect(formatRate(20.1, "en-GB")).toBe("20.1 / min");
    expect(formatPercent(0.944, tEn)).toBe("94%");
    expect(handSideLabel("left", tEn)).toBe("Left hand");
    expect(confidenceLabel(0.9, tEn)).toBe("high");
    expect(confidenceLabel(null, tEn)).toBe("no point detected");
  });

  it("nettoie le nom d'un point personnalisé et libelle les mains", () => {
    expect(customDisplayName("custom_cle_a_molette")).toBe("cle a molette");
    expect(customDisplayName("bobine")).toBe("bobine");
    expect(handSideLabel("left", tFr)).toBe("Main gauche");
    expect(handSideLabel("right", tFr)).toBe("Main droite");
  });

  it("qualifie la confiance sans inventer de valeur quand rien n'est détecté", () => {
    expect(confidenceLabel(0.9, tFr)).toBe("élevée");
    expect(confidenceLabel(0.7, tFr)).toBe("correcte");
    expect(confidenceLabel(0.3, tFr)).toBe("faible");
    expect(confidenceLabel(null, tFr)).toBe("aucun point détecté");
  });
});
