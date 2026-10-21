import { describe, expect, it } from "vitest";

import { formatCycles, formatHours, formatSampleDuration } from "./recurrenceFormat";

const normalizeSpaces = (text: string) => text.replace(/\s/g, " ");

describe("formatHours", () => {
  it("formats whole hours", () => {
    expect(formatHours(5)).toBe("5 h");
  });

  it("formats hours and minutes with two-digit minutes", () => {
    expect(formatHours(4.25)).toBe("4 h 15");
    expect(formatHours(1.05)).toBe("1 h 03");
  });

  it("formats less than an hour in minutes", () => {
    expect(formatHours(0.5)).toBe("30 min");
  });

  it("formats zero", () => {
    expect(formatHours(0)).toBe("0 min");
  });

  it("rolls 59.6 minutes over to the next hour", () => {
    expect(formatHours(1.9933)).toBe("2 h");
  });
});

describe("formatCycles", () => {
  it("rounds to a whole number with a French thousands separator", () => {
    expect(normalizeSpaces(formatCycles(1980.4))).toBe("1 980");
    expect(formatCycles(0)).toBe("0");
  });
});

describe("formatSampleDuration", () => {
  it("uses seconds under a minute", () => {
    expect(formatSampleDuration(20)).toBe("20 s");
  });

  it("uses minutes with at most one decimal and a French comma", () => {
    expect(formatSampleDuration(180)).toBe("3 min");
    expect(formatSampleDuration(150)).toBe("2,5 min");
  });
});
