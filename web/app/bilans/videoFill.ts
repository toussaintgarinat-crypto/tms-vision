import { AssistantTaskFields } from "../assistant/taskFill";
import { BilanReportAnalysis, ZONES, Zone } from "./types";

/**
 * Valeurs de la fiche d'activité déduites de la mesure d'une vidéo du bilan, pour pré-remplir le
 * formulaire quand on choisit « Compléter une vidéo du bilan ».
 *
 * - zones : celles où la vidéo mesure du temps en posture à risque ;
 * - répétitions : les cycles par minute mesurés de ces zones ;
 * - durée d'un cycle : celle de la zone qui répète le plus ;
 * - tenue statique : la plus longue de ces zones ;
 * - durée : les heures indiquées pour la vidéo dans le bilan.
 * Une valeur que la mesure ne donne pas est simplement absente.
 */
export function videoTaskFields(
  analysis: BilanReportAnalysis,
  activityHours: number,
): AssistantTaskFields {
  const measured = analysis.recurrence.zones;
  const zones = ZONES.filter((zone) => measured[zone].elevated_seconds > 0);

  const perMinute: Partial<Record<Zone, number>> = {};
  for (const zone of zones) {
    const cycles = measured[zone].cycles_per_minute;
    if (cycles !== null && cycles > 0) perMinute[zone] = cycles;
  }

  let dominant: Zone | null = null;
  for (const zone of zones) {
    const { cycles_per_minute: cycles, mean_cycle_seconds: seconds } = measured[zone];
    if (cycles === null || seconds === null) continue;
    if (dominant === null || cycles > (measured[dominant].cycles_per_minute ?? 0)) dominant = zone;
  }
  const longestStatic = Math.max(0, ...zones.map((zone) => measured[zone].longest_static_seconds));

  const fields: AssistantTaskFields = { zones, activity_hours: activityHours };
  if (Object.keys(perMinute).length > 0) fields.zone_cycles_per_minute = perMinute;
  if (dominant !== null) fields.cycle_seconds = measured[dominant].mean_cycle_seconds as number;
  if (longestStatic > 0) fields.static_seconds = longestStatic;
  return fields;
}
