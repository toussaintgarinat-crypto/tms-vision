export type CapsuleVideoInfo = {
  video_url: string;
  video_available?: boolean;
};

// Adresse de la vidéo générée d'une capsule, ou null tant qu'elle n'existe pas (le
// fichier est produit par `python -m tms_vision.capsule_build`).
export function capsuleVideoSrc(capsule: CapsuleVideoInfo, apiUrl: string): string | null {
  return capsule.video_available ? `${apiUrl}${capsule.video_url}` : null;
}

export const DRAFT_BADGE_TEXT = "Brouillon, à valider par l'ostéopathe";

// Exercice repris d'une fiche de l'ostéopathe : on l'affiche à la place du badge « Brouillon » pour
// ne pas le mélanger avec les exercices pas encore relus.
export const FICHE_BADGE_TEXT = "Fiche de Théo MARTIN, ostéopathe";

export const NO_PROGRAM_TEXT =
  "Aucun étirement proposé : sur cet échantillon, aucune zone n'atteint un niveau de posture à " +
  "risque (investigation et changement bientôt, ou plus). Les exercices restent consultables " +
  "dans la bibliothèque.";
