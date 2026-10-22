export type FrequencyUnit = "minute" | "hour" | "day";

export const FREQUENCY_UNIT_LABELS: Record<FrequencyUnit, string> = {
  minute: "par minute",
  hour: "par heure",
  day: "par jour",
};

export type TimeSlot = { start: string; end: string };

/** Répétitions saisies -> cycles par minute (valeur canonique côté serveur).
 *  Par jour : divisé par la durée de la tâche dans la journée, en heures. */
export function toCyclesPerMinute(
  value: number,
  unit: FrequencyUnit,
  activityHours: number | null,
): number | null {
  if (!Number.isFinite(value) || value < 0) return null;
  if (unit === "minute") return value;
  if (unit === "hour") return value / 60;
  if (activityHours === null || activityHours <= 0) return null;
  return value / (activityHours * 60);
}

function clockToMinutes(clock: string): number | null {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(clock);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

/** Total des plages en heures ; null si une plage est incomplète, inversée
 *  ou chevauche une autre (même règle que le serveur). */
export function slotsTotalHours(slots: TimeSlot[]): number | null {
  const parsed: [number, number][] = [];
  for (const slot of slots) {
    const start = clockToMinutes(slot.start);
    const end = clockToMinutes(slot.end);
    if (start === null || end === null || end <= start) return null;
    parsed.push([start, end]);
  }
  parsed.sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < parsed.length; i += 1) {
    if (parsed[i][0] < parsed[i - 1][1]) return null;
  }
  return parsed.reduce((total, [start, end]) => total + (end - start), 0) / 60;
}

export function formatSlots(slots: TimeSlot[]): string {
  return slots.map((slot) => `${slot.start}–${slot.end}`).join(", ");
}

export const SOURCE_LABELS = {
  measured: "Mesuré",
  practitioner: "Saisi par le praticien",
  patient: "Déclaré par le patient",
} as const;
export type Source = keyof typeof SOURCE_LABELS;
