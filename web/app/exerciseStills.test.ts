import { describe, expect, it } from "vitest";

import { Exercise } from "./exercisePose";
import { stillSteps } from "./exerciseStills";

function exercise(overrides: Partial<Exercise>): Exercise {
  return {
    id: "x", zone: "neck", title: "T", description: "D", status: "draft", source: "human",
    validated_by: null, validated_on: null, view: "front", target_segments: ["neck"],
    poses: { neutral: {}, right: {}, left: {} },
    keyframes: [{ t: 0, pose: "neutral" }, { t: 10, pose: "right" }],
    instructions: [{ t: 0, text: "Départ" }],
    duration_seconds: 20,
    ...overrides,
  };
}

describe("stillSteps", () => {
  it("gives one step per distinct pose, at the instant the pose is reached", () => {
    const steps = stillSteps(
      exercise({
        keyframes: [
          { t: 0, pose: "neutral" },
          { t: 5, pose: "right" },
          { t: 15, pose: "right" },
          { t: 20, pose: "neutral" },
          { t: 25, pose: "left" },
          { t: 35, pose: "left" },
          { t: 40, pose: "neutral" },
        ],
        instructions: [
          { t: 0, text: "Dos droit" },
          { t: 5, text: "À droite" },
          { t: 20, text: "Au centre" },
          { t: 25, text: "À gauche" },
        ],
        duration_seconds: 45,
      }),
    );
    expect(steps.map((step) => step.t)).toEqual([0, 5, 25]);
    expect(steps.map((step) => step.text)).toEqual(["Dos droit", "À droite", "À gauche"]);
  });

  it("does not repeat a pose that comes back, even many times", () => {
    const keyframes = [{ t: 0, pose: "neutral" }];
    for (let i = 0; i < 6; i++) {
      keyframes.push({ t: 5 + i * 8, pose: "a" }, { t: 9 + i * 8, pose: "b" });
    }
    const steps = stillSteps(
      exercise({ poses: { neutral: {}, a: {}, b: {} }, keyframes, duration_seconds: 60 }),
    );
    expect(steps).toHaveLength(3);
  });

  it("falls back to an empty text when no instruction has started", () => {
    const steps = stillSteps(exercise({ instructions: [{ t: 50, text: "Tard" }] }));
    expect(steps.every((step) => step.text === "")).toBe(true);
  });

  it("is capped so a carousel stays readable", () => {
    const names = Array.from({ length: 12 }, (_, i) => `p${i}`);
    const poses = Object.fromEntries(names.map((name) => [name, {}]));
    const keyframes = names.map((pose, i) => ({ t: i * 3, pose }));
    expect(stillSteps(exercise({ poses, keyframes, duration_seconds: 50 }))).toHaveLength(8);
  });
});
