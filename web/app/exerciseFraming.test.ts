import { describe, expect, it } from "vitest";
import { cameraPosition, framingFor } from "./exerciseFraming";

describe("framingFor", () => {
  it("cadre le corps entier par défaut et pour les grandes régions", () => {
    for (const regions of [["trunk"], ["upper_arm"], ["thigh", "hip"], ["lower_leg"], ["shoulder"]]) {
      const framing = framingFor({ target_segments: regions as never });
      expect(framing.distance, regions.join()).toBeGreaterThan(3.5);
      expect(framing.target.y).toBeCloseTo(1.0, 6);
    }
  });

  it("zoome sur la tête, la main ou le pied quand ils sont seuls ciblés", () => {
    const head = framingFor({ target_segments: ["neck", "head"] });
    const hands = framingFor({ target_segments: ["hand"] });
    const feet = framingFor({ target_segments: ["foot"] });

    expect(head.target.y).toBeGreaterThan(1.3);
    expect(hands.target.y).toBeCloseTo(1.2, 6);
    expect(feet.target.y).toBeLessThan(0.9);
    for (const framing of [head, hands, feet]) expect(framing.distance).toBeLessThanOrEqual(3);
  });

  it("revient au corps entier dès qu'une grande région est ciblée avec une petite", () => {
    expect(framingFor({ target_segments: ["hand", "trunk"] }).distance).toBeGreaterThan(3.5);
    expect(framingFor({ target_segments: ["hand", "lower_arm"] }).distance).toBeLessThan(3);
  });
});

describe("cameraPosition", () => {
  const framing = framingFor({ target_segments: ["trunk"] });

  it("place la caméra devant, à droite du sujet ou en trois quarts, à la distance du cadrage", () => {
    const front = cameraPosition("front", framing);
    expect(front.z).toBeCloseTo(framing.distance, 6);
    expect(front.y).toBeCloseTo(framing.target.y, 6);

    const side = cameraPosition("side", framing);
    expect(side.x).toBeCloseTo(-framing.distance, 6);

    const three = cameraPosition("three_quarter", framing);
    expect(three.x).toBeLessThan(0);
    expect(three.z).toBeGreaterThan(0);
  });
});
