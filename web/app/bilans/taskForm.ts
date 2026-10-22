import { ZONE_LABELS, ZONES, Zone } from "./types";

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

export function formatZoneCycles(zoneCycles: Partial<Record<Zone, number>>): string {
  const parts = ZONES.filter((zone) => zoneCycles[zone] !== undefined).map(
    (zone) =>
      `${ZONE_LABELS[zone]} : ${(zoneCycles[zone] as number).toLocaleString("fr-FR", {
        maximumFractionDigits: 2,
      })}/min`,
  );
  return parts.length > 0 ? parts.join(" · ") : "répétitions non renseignées";
}

export const OTHER_OPTION = "Autre";

// BROUILLON (draft) : listes « 20 % des cas qui font 80 % » à faire valider par
// l'ostéopathe. Informatives : elles n'entrent pas dans la projection.
export const WORKSTATION_OPTIONS = [
  "Assis devant écran",
  "Debout statique (caisse, atelier)",
  "Manutention et port de charges",
  "Bras au-dessus des épaules (peinture, plafond)",
  "Conduite",
  "Geste répétitif en production",
  "Penché (soins, nettoyage)",
  "Marche et déplacements",
] as const;

export const BREAK_OPTIONS = [
  "Aucune pause",
  "Déjeuner seulement",
  "Pauses courtes toutes les 2 h",
  "Micro-pauses fréquentes",
  "Rotation de poste",
] as const;

/** Valeur à envoyer pour une liste à choix + « Autre » : null si rien n'est choisi. */
export function choiceValue(choice: string, otherText: string): string | null {
  if (choice === "") return null;
  if (choice === OTHER_OPTION) return otherText.trim() === "" ? null : otherText.trim();
  return choice;
}
