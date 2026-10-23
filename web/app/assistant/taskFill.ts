import {
  BREAK_OPTIONS,
  FrequencyUnit,
  OTHER_OPTION,
  TimeSlot,
  WORKSTATION_OPTIONS,
} from "../bilans/taskForm";
import { Zone } from "../bilans/types";

/** Champs que l'assistant peut proposer (réponse de POST /assistant/extract). */
export type AssistantTaskFields = {
  name?: string;
  zones?: Zone[];
  time_slots?: TimeSlot[];
  activity_hours?: number;
  zone_cycles_per_minute?: Partial<Record<Zone, number>>;
  cycle_seconds?: number;
  static_seconds?: number;
  load_kg?: number;
  days_per_week?: number;
  workstation?: string;
  breaks?: string;
  notes?: string;
};

/** État du formulaire de fiche d'activité (TaskSection), tel que l'utilisateur le voit. */
export type TaskFormState = {
  name: string;
  zones: Zone[];
  useSlots: boolean;
  slots: TimeSlot[];
  hours: string;
  frequencies: Partial<Record<Zone, string>>;
  unit: FrequencyUnit;
  cycleSeconds: string;
  staticSeconds: string;
  loadKg: string;
  daysPerWeek: string;
  notes: string;
  workstation: string;
  workstationOther: string;
  breaks: string;
  breaksOther: string;
};

export const EMPTY_TASK_FORM: TaskFormState = {
  name: "",
  zones: [],
  useSlots: false,
  slots: [{ start: "", end: "" }],
  hours: "",
  frequencies: {},
  unit: "minute",
  cycleSeconds: "",
  staticSeconds: "",
  loadKg: "",
  daysPerWeek: "",
  notes: "",
  workstation: "",
  workstationOther: "",
  breaks: "",
  breaksOther: "",
};

/** Clés du formulaire que l'assistant a remplies (pour le surlignage « IA »). */
export type FilledKey = keyof TaskFormState;

export const FIELD_LABELS: Record<FilledKey, string> = {
  name: "nom",
  zones: "zones",
  useSlots: "horaires",
  slots: "horaires",
  hours: "durée",
  frequencies: "répétitions",
  unit: "unité",
  cycleSeconds: "durée d'un cycle",
  staticSeconds: "tenue statique",
  loadKg: "charge",
  daysPerWeek: "jours par semaine",
  notes: "notes",
  workstation: "poste de travail",
  workstationOther: "poste de travail",
  breaks: "pauses",
  breaksOther: "pauses",
};

export type ApplyResult = {
  state: TaskFormState;
  filled: FilledKey[];
  /** Champs déjà saisis par l'utilisateur et laissés intacts. */
  kept: FilledKey[];
};

function formatNumber(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

/** Cycles par minute -> valeur affichée dans l'unité choisie ; null si « par jour » sans durée. */
export function fromCyclesPerMinute(
  perMinute: number,
  unit: FrequencyUnit,
  activityHours: number | null,
): number | null {
  if (unit === "minute") return perMinute;
  if (unit === "hour") return perMinute * 60;
  if (activityHours === null || activityHours <= 0) return null;
  return perMinute * activityHours * 60;
}

function isEmptySlots(slots: TimeSlot[]): boolean {
  return slots.every((slot) => slot.start === "" && slot.end === "");
}

function choiceAndOther(
  value: string,
  options: readonly string[],
): { choice: string; other: string } {
  return options.includes(value)
    ? { choice: value, other: "" }
    : { choice: OTHER_OPTION, other: value };
}

function slotsHours(slots: TimeSlot[]): number {
  const toMinutes = (clock: string) => Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3, 5));
  return slots.reduce((total, slot) => total + (toMinutes(slot.end) - toMinutes(slot.start)), 0) / 60;
}

/**
 * Applique les champs proposés par l'assistant. Par défaut, une valeur déjà saisie par
 * l'utilisateur n'est jamais écrasée (sauf les zones, qui s'ajoutent) ; `overwrite` permet à
 * l'utilisateur de dire « corrige » explicitement.
 */
export function applyTaskFields(
  current: TaskFormState,
  fields: AssistantTaskFields,
  overwrite = false,
): ApplyResult {
  const next: TaskFormState = { ...current, frequencies: { ...current.frequencies } };
  const filled = new Set<FilledKey>();
  const kept = new Set<FilledKey>();

  function setIfFree<K extends FilledKey>(key: K, isFilled: boolean, apply: () => void) {
    if (isFilled && !overwrite) {
      kept.add(key);
      return;
    }
    apply();
    filled.add(key);
  }

  if (fields.name !== undefined) {
    setIfFree("name", current.name.trim() !== "", () => {
      next.name = fields.name as string;
    });
  }

  if (fields.zones !== undefined) {
    const merged = overwrite ? fields.zones : [...new Set([...current.zones, ...fields.zones])];
    if (merged.length !== current.zones.length || merged.some((z, i) => z !== current.zones[i])) {
      next.zones = merged;
      filled.add("zones");
    }
  }

  const durationFilled = current.useSlots ? !isEmptySlots(current.slots) : current.hours.trim() !== "";
  if (fields.time_slots !== undefined && fields.time_slots.length > 0) {
    setIfFree("slots", durationFilled, () => {
      next.useSlots = true;
      next.slots = fields.time_slots as TimeSlot[];
      next.hours = "";
      filled.add("useSlots");
    });
  } else if (fields.activity_hours !== undefined) {
    setIfFree("hours", durationFilled, () => {
      next.useSlots = false;
      next.hours = formatNumber(fields.activity_hours as number);
    });
  }

  if (fields.zone_cycles_per_minute !== undefined) {
    const hasTyped = Object.values(current.frequencies).some((v) => (v ?? "").trim() !== "");
    // Sans fréquence déjà saisie, on repart de « par minute » (la valeur canonique du serveur).
    const unit: FrequencyUnit = hasTyped ? current.unit : "minute";
    const hours = next.useSlots && !isEmptySlots(next.slots)
      ? slotsHours(next.slots)
      : next.hours.trim() !== "" ? Number(next.hours.replace(",", ".")) : null;
    let applied = false;
    for (const [zone, perMinute] of Object.entries(fields.zone_cycles_per_minute) as [Zone, number][]) {
      const typed = (current.frequencies[zone] ?? "").trim() !== "";
      if (typed && !overwrite) {
        kept.add("frequencies");
        continue;
      }
      const shown = fromCyclesPerMinute(perMinute, unit, hours);
      if (shown === null) continue;
      next.frequencies[zone] = formatNumber(shown);
      applied = true;
    }
    if (applied) {
      next.unit = unit;
      filled.add("frequencies");
      if (!next.zones.includes(Object.keys(fields.zone_cycles_per_minute)[0] as Zone)) {
        // Une fréquence sans zone cochée serait ignorée à l'envoi : on coche la zone.
        for (const zone of Object.keys(fields.zone_cycles_per_minute) as Zone[]) {
          if (!next.zones.includes(zone)) next.zones = [...next.zones, zone];
        }
        filled.add("zones");
      }
    }
  }

  const numeric: [keyof AssistantTaskFields, FilledKey][] = [
    ["cycle_seconds", "cycleSeconds"],
    ["static_seconds", "staticSeconds"],
    ["load_kg", "loadKg"],
    ["days_per_week", "daysPerWeek"],
  ];
  for (const [source, target] of numeric) {
    const value = fields[source];
    if (typeof value !== "number") continue;
    setIfFree(target, (current[target] as string).trim() !== "", () => {
      (next[target] as string) = formatNumber(value);
    });
  }

  if (fields.workstation !== undefined) {
    setIfFree("workstation", current.workstation !== "", () => {
      const { choice, other } = choiceAndOther(fields.workstation as string, WORKSTATION_OPTIONS);
      next.workstation = choice;
      next.workstationOther = other;
    });
  }
  if (fields.breaks !== undefined) {
    setIfFree("breaks", current.breaks !== "", () => {
      const { choice, other } = choiceAndOther(fields.breaks as string, BREAK_OPTIONS);
      next.breaks = choice;
      next.breaksOther = other;
    });
  }
  if (fields.notes !== undefined) {
    setIfFree("notes", current.notes.trim() !== "", () => {
      next.notes = fields.notes as string;
    });
  }

  return { state: next, filled: [...filled], kept: [...kept] };
}

/** Valeurs déjà saisies, au format attendu par POST /assistant/extract (`current_values`). */
export function taskFormToCurrentValues(state: TaskFormState): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  if (state.name.trim() !== "") values.name = state.name.trim();
  if (state.zones.length > 0) values.zones = state.zones;
  if (state.useSlots && !isEmptySlots(state.slots)) values.time_slots = state.slots;
  else if (state.hours.trim() !== "") values.activity_hours = Number(state.hours.replace(",", "."));
  if (state.useSlots && !isEmptySlots(state.slots)) {
    const total = slotsHours(state.slots);
    if (Number.isFinite(total) && total > 0) values.activity_hours = total;
  }
  return values;
}
