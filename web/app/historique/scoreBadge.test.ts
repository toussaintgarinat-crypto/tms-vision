import { describe, expect, it } from "vitest";

import { scoreBadgeColor, scoreBadgeTextColor } from "./scoreBadge";

describe("scoreBadgeColor", () => {
  it.each([
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
    [1, "#FFFFFF"],
    [2, "#FFFFFF"],
    [3, "#1F2937"],
    [4, "#1F2937"],
    [5, "#FFFFFF"],
    [6, "#FFFFFF"],
    [7, "#FFFFFF"],
    [8, "#FFFFFF"],
  ])("maps score %i to text color %s", (score, expected) => {
    expect(scoreBadgeTextColor(score)).toBe(expected);
  });
});
