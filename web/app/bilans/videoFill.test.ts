import { describe, expect, it } from "vitest";

import { applyTaskFields } from "../assistant/taskFill";
import { EMPTY_TASK_FORM } from "../assistant/taskFill";
import { AnalysisRecurrence, BilanReportAnalysis, ZONES, ZoneRecurrence } from "./types";
import { videoTaskFields } from "./videoFill";

function zone(overrides: Partial<ZoneRecurrence> = {}): ZoneRecurrence {
  return {
    cycles: 0, cycles_per_minute: null, mean_cycle_seconds: null, longest_static_seconds: 0,
    elevated_seconds: 0, assessment: null, ...overrides,
  };
}

function analysis(zones: Partial<Record<(typeof ZONES)[number], ZoneRecurrence>>): BilanReportAnalysis {
  const all = Object.fromEntries(ZONES.map((name) => [name, zones[name] ?? zone()]));
  const recurrence = { sample_seconds: 40, thresholds_calibrated: false, zones: all } as AnalysisRecurrence;
  return {
    analysis_id: "a-1", source: "measured", declared: [], activity_hours: 7, representative: true,
    included: true, sample_seconds: 40, warnings: [], recurrence,
  };
}

// Mesures de l'enregistrement d'écran du praticien (tâche « fileur », vidéo de 40 s).
const FILEUR = analysis({
  neck: zone({ cycles: 11, cycles_per_minute: 16.6, mean_cycle_seconds: 3, longest_static_seconds: 15, elevated_seconds: 1 }),
  trunk: zone({ cycles: 2, cycles_per_minute: 3, mean_cycle_seconds: 18, longest_static_seconds: 19 }),
  upper_arm: zone({ cycles: 20, cycles_per_minute: 31, mean_cycle_seconds: 2, longest_static_seconds: 15, elevated_seconds: 2 }),
  lower_arm: zone({ cycles: 44, cycles_per_minute: 66.5, mean_cycle_seconds: 1, longest_static_seconds: 2 }),
  hand: zone({ cycles: 48, cycles_per_minute: 73.3, mean_cycle_seconds: 1, longest_static_seconds: 16, elevated_seconds: 40 }),
  foot: zone({ cycles: 20, cycles_per_minute: 31, mean_cycle_seconds: 2, longest_static_seconds: 15, elevated_seconds: 5 }),
});

describe("videoTaskFields", () => {
  it("ticks the zones with time in risky posture and fills their measured repetitions", () => {
    const fields = videoTaskFields(FILEUR, 7);

    expect(fields.zones).toEqual(["neck", "upper_arm", "hand", "foot"]);
    expect(fields.zone_cycles_per_minute).toEqual({ neck: 16.6, upper_arm: 31, hand: 73.3, foot: 31 });
    expect(fields.activity_hours).toBe(7);
  });

  it("takes the cycle duration of the zone that repeats most and the longest static hold", () => {
    const fields = videoTaskFields(FILEUR, 7);

    expect(fields.cycle_seconds).toBe(1); // la main : 73,3 cycles par minute, 1 s chacun
    expect(fields.static_seconds).toBe(16);
  });

  it("leaves out what the measure does not give", () => {
    const fields = videoTaskFields(analysis({ trunk: zone({ elevated_seconds: 3 }) }), 4);

    expect(fields.zones).toEqual(["trunk"]);
    expect(fields).not.toHaveProperty("zone_cycles_per_minute");
    expect(fields).not.toHaveProperty("cycle_seconds");
    expect(fields).not.toHaveProperty("static_seconds");
  });

  it("proposes no zone when nothing is in risky posture, so the practitioner chooses", () => {
    expect(videoTaskFields(analysis({}), 7).zones).toEqual([]);
  });

  it("fills an empty form through applyTaskFields, with the zones ticked and the unit per minute", () => {
    const result = applyTaskFields(EMPTY_TASK_FORM, videoTaskFields(FILEUR, 7));

    expect(result.state.zones).toEqual(["neck", "upper_arm", "hand", "foot"]);
    expect(result.state.frequencies).toEqual({ neck: "16.6", upper_arm: "31", hand: "73.3", foot: "31" });
    expect(result.state.unit).toBe("minute");
    expect(result.state.hours).toBe("7");
    expect(result.state.cycleSeconds).toBe("1");
    expect(result.state.staticSeconds).toBe("16");
  });
});
