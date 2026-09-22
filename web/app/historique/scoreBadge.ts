// Mêmes seuils que rula/scoring.py::action_level(), même palette que
// PostureAvatar3D.tsx::ACTION_LEVEL_COLORS -- dupliqué ici (4 couleurs figées,
// pas de dépendance ajoutée pour si peu).
export function scoreBadgeColor(maxScore: number): string {
  if (maxScore <= 2) return "#4CAF50";
  if (maxScore <= 4) return "#EBD23C";
  if (maxScore <= 6) return "#EB9628";
  return "#D23232";
}

// Contraste mesuré contre blanc pour les 4 couleurs de fond ci-dessus : vert
// #4CAF50 (2.78:1), jaune #EBD23C (1.52:1) et orange #EB9628 (2.35:1) sont
// tous sous le seuil WCAG AA de 4.5:1 -- seul le rouge #D23232 (4.95:1) passe.
// Texte sombre pour les 3 premières bandes (scores 1-6), blanc uniquement
// pour le rouge.
export function scoreBadgeTextColor(maxScore: number): string {
  return maxScore <= 6 ? "#1F2937" : "#FFFFFF";
}
