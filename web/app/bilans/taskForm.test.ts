import { describe, expect, it } from "vitest";

import { translator } from "../i18n/catalog";
import { FIELD_LABEL_KEYS, EMPTY_TASK_FORM } from "../assistant/taskFill";
import { ZONES, zoneKey } from "./types";
import {
  BREAK_OPTIONS,
  FREQUENCY_UNITS,
  WORKSTATION_OPTIONS,
  choiceLabel,
  choiceValue,
  frequencyUnitKey,
  sourceKey,
  formatSlots,
  formatZoneCycles,
  slotsTotalHours,
  toCyclesPerMinute,
} from "./taskForm";

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

describe("formatZoneCycles", () => {
  const fr = translator("fr");
  const en = translator("en");

  it("lists zones in body order with their own frequency", () => {
    expect(formatZoneCycles({ lower_arm: 20, neck: 6 }, fr)).toBe("Cou : 6/min · Avant-bras / coude : 20/min");
    expect(formatZoneCycles({ lower_arm: 20, neck: 6 }, en, "en-GB")).toBe("Neck: 6/min · Forearm / elbow: 20/min");
  });

  it("uses the decimal separator of the language", () => {
    expect(formatZoneCycles({ neck: 1.5 }, fr, "fr-FR")).toBe("Cou : 1,5/min");
    expect(formatZoneCycles({ neck: 1.5 }, en, "en-GB")).toBe("Neck: 1.5/min");
  });

  it("says when nothing is filled in", () => {
    expect(formatZoneCycles({}, fr)).toBe("répétitions non renseignées");
    expect(formatZoneCycles({}, en)).toBe("repetitions not provided");
  });
});

describe("translated labels", () => {
  const en = translator("en");
  const known = (key: string) => en(key) !== key;

  it("exist for zones, units, sources and form fields", () => {
    expect(ZONES.filter((zone) => !known(zoneKey(zone)))).toEqual([]);
    expect(FREQUENCY_UNITS.filter((unit) => !known(frequencyUnitKey(unit)))).toEqual([]);
    for (const source of ["measured", "practitioner", "patient"] as const) expect(known(sourceKey(source))).toBe(true);
    expect(Object.values(FIELD_LABEL_KEYS).filter((key) => !known(key))).toEqual([]);
    expect(Object.keys(EMPTY_TASK_FORM)).toEqual(Object.keys(FIELD_LABEL_KEYS));
  });

  it("choiceLabel translates listed choices, keeps the stored French value, and leaves free text alone", () => {
    expect(choiceLabel(en, "workstation", "Conduite")).toBe("Driving");
    expect(choiceLabel(translator("fr"), "workstation", "Conduite")).toBe("Conduite");
    expect(choiceLabel(en, "breaks", "Rotation de poste")).toBe("Job rotation");
    expect(choiceLabel(en, "breaks", "Chariot élévateur")).toBe("Chariot élévateur");
  });

  it("has a translation for every listed workstation and break", () => {
    for (const [kind, list] of [["workstation", WORKSTATION_OPTIONS], ["breaks", BREAK_OPTIONS]] as const) {
      list.forEach((_, index) => expect(known(`bilans.${kind}.${index}`)).toBe(true));
    }
  });
});

describe("choiceValue", () => {
  it("returns the listed choice, the free text for Autre, or null", () => {
    expect(choiceValue("Conduite", "")).toBe("Conduite");
    expect(choiceValue("Autre", "  Chariot élévateur ")).toBe("Chariot élévateur");
    expect(choiceValue("Autre", " ")).toBeNull();
    expect(choiceValue("", "x")).toBeNull();
  });
});
