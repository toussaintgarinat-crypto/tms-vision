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
