# Mains et pieds mesurés par vidéo (Tranche 5)

## Contexte

La Tranche 4 a donné à l'avatar 24 os et des muscles de la tête aux pieds, mais l'analyse par vidéo ne
mesurait que quatre zones (cou, tronc, bras, avant-bras). Les mains, les doigts, les poignets et les
pieds restaient gris. Cette tranche ajoute **deux zones mesurées : `hand` (poignet + doigts) et
`foot` (cheville)**, de bout en bout : mesure, niveaux, stockage, récurrence, programme
d'étirements, couleur de l'avatar.

## Décisions

- **Hors RULA.** RULA ne note que le poignet. Les notes main et pied (1 à 3) n'entrent pas dans les
  tables A/B/C : le score RULA final, le recalcul au poids (`rescore.py`) et la détection
  d'effort musculaire sont inchangés. Elles ne servent qu'aux niveaux par segment.
- **Main = le pire du poignet et des doigts.** Poignet : `classify_wrist` de RULA (flexion en image
  2D, comme avant). Doigts : MediaPipe Hands (`hand_estimation.py`), flexion moyenne des quatre doigts
  longs à l'articulation médiane, calculée avec le rapport largeur/hauteur de l'image. La main
  retenue est celle dont le poignet est le plus proche du poignet de Pose (15 % de la diagonale au
  plus) ; sinon, pas de mesure des doigts et la main ne repose que sur le poignet.
- **Pied = cheville en 3D.** Angle entre la jambe (cheville → genou) et le pied (talon → orteils)
  moins 90°, sur les points « monde » de MediaPipe Pose. Pas en 2D : sur une vraie vidéo (peintre,
  1280×720), l'angle 2D donnait environ 58° constants (pied « élevé » dans 227 images sur 227), contre
  environ 10° en 3D pour un pied à plat. `None` si genou, cheville, talon ou orteils ne sont pas
  visibles : le niveau est alors absent (jamais de couleur pour une donnée non mesurée).
- **Seuils réglables et non calibrés** (`extremity_thresholds.json`, `"calibrated": false`) :
  flexion des doigts `[70, 100]°`, cheville `[10, 20]°`, notes 1/2/3 ; coupures de niveau
  `[1, 2, 3]` : note 1 acceptable, 2 investigation recommandée, 3 « changement bientôt » (niveau
  élevé, celui qui déclenche une recommandation). Ces valeurs sont des points de départ à valider avec
  l'ostéopathe, pas une norme.
- **Pourquoi une échelle propre et pas `action_level`.** `action_level` ne passe en niveau élevé qu'à
  partir d'une note de 5 ; le poignet RULA plafonne à 4 et ne pourrait donc jamais déclencher de
  recommandation (même limite que `lower_arm`, voir `capsules.py`). Les notes main/pied sont sur 3.
- **Récurrence** : la main suit `wrist_flexion_deg`, le pied `ankle_flexion_deg` (seuils par zone
  dans `recurrence_thresholds.json`, 10°/15° par défaut comme les autres zones).
- **Programme** : `hand` et `foot` rejoignent `ZONE_PRIORITY` (en dernier, à charge égale) ; les
  exercices `wrist-flexor-stretch`, `finger-extension-stretch` (main) et `ankle-mobility` (pied)
  existent déjà. `calf-stretch` (mollet, `lower_leg`) n'est pas recommandé : le mollet n'est pas
  mesuré.
- **Stockage** : colonnes `ankle_flexion_deg`, `finger_curl_deg`, `hand_segment_action_level`,
  `foot_segment_action_level`. Les bases créées avant cette tranche sont complétées au premier accès
  (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) : leurs anciennes images gardent NULL, donc ni main
  ni pied pour les analyses anciennes.
- **Avatar** : la main et le pied du côté analysé se colorent par leur niveau ; l'autre côté reste
  gris, comme pour les bras.

## Mesures sur une vraie vidéo (peintre, 227 images, côté droit)

- Pied : cheville médiane 9° (de -2° à 18°) ; 123 images « acceptable », 104 « investigation
  recommandée », aucune élevée : plausible pour quelqu'un debout.
- Main : poignet médian 14° (jusqu'à 59°), doigts détectés dans 34 images sur 227 (médiane 80° : main
  qui tient un rouleau) ; 15 images acceptables, 95 « recommandée », 117 « changement bientôt ».
  Plausible pour les bras levés et la prise d'un outil, mais **non validé** : la flexion du poignet en
  2D est bruitée et la prise en main compte comme une posture à risque tant que les seuils ne sont
  pas calibrés. Un essai du poignet en 3D n'était pas meilleur (médiane 20 à 30°) et n'a pas été
  retenu.
- Surcoût de MediaPipe Hands : non mesuré à part (l'analyse complète de cette vidéo prend environ 12 s
  pour 227 images, face blur désactivé).

## Limites connues

- Les doigts ne sont mesurés que quand MediaPipe Hands trouve une main proche du poignet de Pose :
  main petite, de dos, floue ou cachée = pas de mesure des doigts (le poignet seul prend le relais).
- La flexion du poignet reste une flexion en 2D, donc dépendante de l'angle de prise de vue
  (limite déjà connue de RULA dans ce projet).
- Le pied suppose que Pose voit le talon et les orteils ; un poste assis, pieds sous le bureau, ne
  donne souvent aucune mesure.
- La déviation radiale/ulnaire du poignet, la position de chaque doigt, l'appui (pied à plat ou sur la
  pointe) et la charge sur le pied ne sont pas mesurés.
- Les seuils ne sont pas calibrés.
- Les rapports et les mesures de récurrence affichent maintenant six zones.

## Tests

`tests/test_extremities.py` (cheville, doigts, notes, niveaux, seuils invalides),
`tests/test_pipeline.py` (main et pied de bout en bout avec points fictifs),
`tests/test_storage.py` (migration d'une ancienne base), `tests/test_program.py` (programme main/pied),
`web/app/muscleSegments.test.ts` (routage de la main vers le segment `hand`).
