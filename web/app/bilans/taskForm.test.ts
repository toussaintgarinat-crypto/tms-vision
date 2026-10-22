import { describe, expect, it } from "vitest";

import { formatSlots, slotsTotalHours, toCyclesPerMinute } from "./taskForm";

describe("toCyclesPerMinute", () => {
  it("keeps per-minute values", () => {
    expect(toCyclesPerMinute(12, "minute", null)).toBe(12);
  });

  it("converts per hour", () => {
    expect(toCyclesPerMinute(120, "hour", null)).toBe(2);
  });

  it("converts per day using the task duration", () => {
    expect(toCyclesPerMinute(600, "day", 5)).toBe(2);
  });

  it("refuses per-day without a duration, and invalid values", () => {
    expect(toCyclesPerMinute(600, "day", null)).toBeNull();
    expect(toCyclesPerMinute(-1, "minute", null)).toBeNull();
    expect(toCyclesPerMinute(Number.NaN, "hour", null)).toBeNull();
  });
});

describe("slotsTotalHours", () => {
  it("sums slots", () => {
    expect(
      slotsTotalHours([
        { start: "08:00", end: "12:00" },
        { start: "13:30", end: "17:00" },
      ]),
    ).toBe(7.5);
  });

  it("rejects incomplete, reversed and overlapping slots", () => {
    expect(slotsTotalHours([{ start: "08:00", end: "" }])).toBeNull();
    expect(slotsTotalHours([{ start: "10:00", end: "09:00" }])).toBeNull();
    expect(
      slotsTotalHours([
        { start: "08:00", end: "10:00" },
        { start: "09:00", end: "11:00" },
      ]),
    ).toBeNull();
  });
});

describe("formatSlots", () => {
  it("joins slots", () => {
    expect(formatSlots([{ start: "08:00", end: "12:00" }, { start: "14:00", end: "15:00" }])).toBe(
      "08:00–12:00, 14:00–15:00",
    );
  });
});
