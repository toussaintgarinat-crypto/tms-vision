export type CapsuleVideoInfo = {
  video_url: string;
  video_available?: boolean;
};

// Adresse de la vidéo générée d'une capsule, ou null tant qu'elle n'existe pas (le
// fichier est produit par `python -m tms_vision.capsule_build`).
export function capsuleVideoSrc(capsule: CapsuleVideoInfo, apiUrl: string): string | null {
  return capsule.video_available ? `${apiUrl}${capsule.video_url}` : null;
}

// Clés de traduction (voir i18n/messages) : l'écran traduit, ce module ne porte plus de texte.
export const DRAFT_BADGE_KEY = "program.badge.draft";

// Exercice repris d'une fiche de l'ostéopathe : on l'affiche à la place du badge « Brouillon » pour
// ne pas le mélanger avec les exercices pas encore relus.
export const FICHE_BADGE_KEY = "exercise.badge.fiche";

export const NO_PROGRAM_KEY = "program.none";
