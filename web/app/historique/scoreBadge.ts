// Mêmes seuils que rula/scoring.py::action_level(), même palette que
// PostureAvatar3D.tsx::ACTION_LEVEL_COLORS -- dupliqué ici (4 couleurs figées,
// pas de dépendance ajoutée pour si peu).
export function scoreBadgeColor(maxScore: number): string {
  if (maxScore <= 2) return "#4CAF50";
  if (maxScore <= 4) return "#EBD23C";
  if (maxScore <= 6) return "#EB9628";
  return "#D23232";
}

// La bande jaune (#EBD23C, scores 3-4) n'a pas un contraste suffisant en texte
// blanc (~1.7:1, sous le seuil WCAG AA de 4.5:1) -- texte sombre pour cette
// bande uniquement, les 3 autres restent en blanc.
export function scoreBadgeTextColor(maxScore: number): string {
  return maxScore > 2 && maxScore <= 4 ? "#1F2937" : "#FFFFFF";
}
