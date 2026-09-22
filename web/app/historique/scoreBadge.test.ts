import { describe, expect, it } from "vitest";

import { scoreBadgeColor, scoreBadgeTextColor } from "./scoreBadge";

describe("scoreBadgeColor", () => {
  it.each([
    [0, "#4CAF50"],
    [1, "#4CAF50"],
    [2, "#4CAF50"],
    [3, "#EBD23C"],
    [4, "#EBD23C"],
    [5, "#EB9628"],
    [6, "#EB9628"],
    [7, "#D23232"],
    [8, "#D23232"],
  ])("maps score %i to %s", (score, expected) => {
    expect(scoreBadgeColor(score)).toBe(expected);
  });
});

describe("scoreBadgeTextColor", () => {
  it.each([
    [0, "#1F2937"],
    [1, "#1F2937"],
    [2, "#1F2937"],
    [3, "#1F2937"],
    [4, "#1F2937"],
    [5, "#1F2937"],
    [6, "#1F2937"],
    [7, "#FFFFFF"],
    [8, "#FFFFFF"],
  ])("maps score %i to text color %s", (score, expected) => {
    expect(scoreBadgeTextColor(score)).toBe(expected);
  });
});
