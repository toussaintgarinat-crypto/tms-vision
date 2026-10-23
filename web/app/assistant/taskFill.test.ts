import { describe, expect, it } from "vitest";

import {
  EMPTY_TASK_FORM,
  applyTaskFields,
  fromCyclesPerMinute,
  taskFormToCurrentValues,
} from "./taskFill";

describe("applyTaskFields", () => {
  it("fills an empty form from a spoken description", () => {
    const { state, filled } = applyTaskFields(EMPTY_TASK_FORM, {
      name: "Peindre un plafond",
      zones: ["upper_arm", "neck"],
      time_slots: [{ start: "08:00", end: "12:00" }],
      zone_cycles_per_minute: { upper_arm: 20 },
      load_kg: 2.5,
      breaks: "Aucune pause",
      workstation: "Peinture en hauteur sur échafaudage",
    });
    expect(state.name).toBe("Peindre un plafond");
    expect(state.zones).toEqual(["upper_arm", "neck"]);
    expect(state.useSlots).toBe(true);
    expect(state.slots).toEqual([{ start: "08:00", end: "12:00" }]);
    expect(state.frequencies).toEqual({ upper_arm: "20" });
    expect(state.unit).toBe("minute");
    expect(state.loadKg).toBe("2.5");
    expect(state.breaks).toBe("Aucune pause");
    expect(state.workstation).toBe("Autre");
    expect(state.workstationOther).toBe("Peinture en hauteur sur échafaudage");
    expect(filled).toEqual(expect.arrayContaining(["name", "zones", "slots", "frequencies", "loadKg"]));
  });

  it("never overwrites what the user already typed, and reports it", () => {
    const current = { ...EMPTY_TASK_FORM, name: "Saisie", loadKg: "5" };
    const { state, filled, kept } = applyTaskFields(current, { name: "Autre nom", load_kg: 9 });
    expect(state.name).toBe("Saisie");
    expect(state.loadKg).toBe("5");
    expect(filled).toEqual([]);
    expect(kept).toEqual(expect.arrayContaining(["name", "loadKg"]));
  });

  it("overwrites when the user asks for a correction", () => {
    const current = { ...EMPTY_TASK_FORM, name: "Saisie", zones: ["hand" as const] };
    const { state } = applyTaskFields(current, { name: "Tri", zones: ["foot"] }, true);
    expect(state.name).toBe("Tri");
    expect(state.zones).toEqual(["foot"]);
  });

  it("adds zones instead of replacing them by default", () => {
    const current = { ...EMPTY_TASK_FORM, zones: ["hand" as const] };
    expect(applyTaskFields(current, { zones: ["neck"] }).state.zones).toEqual(["hand", "neck"]);
  });

  it("uses a plain duration when there are no time slots", () => {
    const { state } = applyTaskFields(EMPTY_TASK_FORM, { activity_hours: 3.5 });
    expect(state.useSlots).toBe(false);
    expect(state.hours).toBe("3.5");
  });

  it("keeps the unit already chosen when frequencies were typed", () => {
    const current = {
      ...EMPTY_TASK_FORM,
      zones: ["hand" as const, "neck" as const],
      unit: "hour" as const,
      frequencies: { hand: "120" },
    };
    const { state } = applyTaskFields(current, { zone_cycles_per_minute: { hand: 5, neck: 2 } });
    expect(state.unit).toBe("hour");
    expect(state.frequencies).toEqual({ hand: "120", neck: "120" });
  });

  it("ticks the zone of a frequency so it is not silently dropped", () => {
    const { state } = applyTaskFields(EMPTY_TASK_FORM, { zone_cycles_per_minute: { hand: 10 } });
    expect(state.zones).toEqual(["hand"]);
  });

  it("does not mutate the previous state", () => {
    const before = structuredClone(EMPTY_TASK_FORM);
    applyTaskFields(EMPTY_TASK_FORM, { zones: ["neck"], zone_cycles_per_minute: { neck: 3 } });
    expect(EMPTY_TASK_FORM).toEqual(before);
  });
});

describe("fromCyclesPerMinute", () => {
  it("converts to the displayed unit", () => {
    expect(fromCyclesPerMinute(2, "minute", null)).toBe(2);
    expect(fromCyclesPerMinute(2, "hour", null)).toBe(120);
    expect(fromCyclesPerMinute(2, "day", 5)).toBe(600);
    expect(fromCyclesPerMinute(2, "day", null)).toBeNull();
  });
});

describe("taskFormToCurrentValues", () => {
  it("sends only what is filled, with the duration derived from slots", () => {
    expect(taskFormToCurrentValues(EMPTY_TASK_FORM)).toEqual({});
    const state = {
      ...EMPTY_TASK_FORM,
      name: " Saisie ",
      zones: ["hand" as const],
      useSlots: true,
      slots: [{ start: "09:00", end: "11:30" }],
    };
    expect(taskFormToCurrentValues(state)).toEqual({
      name: "Saisie",
      zones: ["hand"],
      time_slots: [{ start: "09:00", end: "11:30" }],
      activity_hours: 2.5,
    });
  });
});
