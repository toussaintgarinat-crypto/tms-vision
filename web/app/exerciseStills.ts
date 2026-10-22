import { Exercise, activeInstruction } from "./exercisePose";

// Étapes d'un carrousel : une image fixe par pose clé distincte de l'exercice, avec la consigne
// en cours à ce moment-là. Le carrousel ne dépend pas du rythme de la vidéo : chacun avance à
// son pas, ou lit tout d'un coup sur papier.
export type StillStep = { t: number; text: string };

export const MAX_STILL_STEPS = 8;

export function stillSteps(exercise: Exercise): StillStep[] {
  const { keyframes } = exercise;
  const steps: StillStep[] = [];
  const seenPoses = new Set<string>();

  let index = 0;
  while (index < keyframes.length) {
    // Suite de poses clés identiques d'affilée (position tenue) : on garde l'instant où la pose est atteinte.
    let end = index;
    while (end + 1 < keyframes.length && keyframes[end + 1].pose === keyframes[index].pose) end++;
    const pose = keyframes[index].pose;
    if (!seenPoses.has(pose)) {
      seenPoses.add(pose);
      const arrival = keyframes[index].t;
      const next = keyframes[end + 1]?.t ?? exercise.duration_seconds;
      // Consigne à mi-chemin de la tenue : celle qui accompagne vraiment cette position.
      const midpoint = arrival + (next - arrival) / 2;
      const instruction = activeInstruction(exercise, Math.max(arrival, midpoint));
      steps.push({ t: arrival, text: instruction?.text ?? "" });
    }
    index = end + 1;
  }
  return steps.slice(0, MAX_STILL_STEPS);
}
