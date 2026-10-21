# Avatar du corps complet (Tranche 4)

**Date** : 2026-10-22
**Statut** : en cours

## Contexte

L'avatar musculaire (Tranches 1 à 3) a **9 os** : tronc, cou, deux bras, deux avant-bras, deux
cuisses, avec 54 muscles. Les vidéos d'étirement (Tranche 3 de la récurrence) ne peuvent donc pas
montrer un poignet, des doigts, la rotation de la tête, une omoplate, un genou fléchi ni une cheville.
La mesure par vidéo, de son côté, ne regarde pas les mains.

Décision du produit : l'avatar doit couvrir **tout le corps** avant d'aller plus loin sur la
génération des vidéos. Cette tranche couvre l'avatar et le format d'exercice. Elle **ne couvre pas**
la mesure des mains par vidéo (MediaPipe Hands, zones et seuils RULA), prévue en Tranche 5.

## Décisions de cadrage

- **24 os** au lieu de 9 : `root`, `spine`, `neck`, `head`, puis par côté (`L_` / `R_`) `clavicle`,
  `upper_arm`, `forearm`, `hand`, `fingers`, `thumb`, `thigh`, `shin`, `foot`, `toes`. Les quatre
  doigts longs forment un seul os `fingers` ; les orteils un seul os `toes`. Le tronc reste un seul
  os `spine` (pas de séparation lombaire / thoracique à ce stade).
- **Les 9 noms d'os existants sont conservés** : les analyses, l'avatar piloté par la vidéo et les
  exercices existants continuent de fonctionner.
- **Angles relatifs au parent** pour les exercices. Jusqu'ici ils étaient absolus (« pour un
  avant-bras prolongeant un bras, donnez-lui les mêmes angles »), ce qui ne tient pas à 24 os : la
  tête, la main ou le pied doivent suivre leur parent. Un os absent d'une pose reste donc **aligné
  sur son parent**. Les quatre exercices livrés sont migrés (leurs poses ne changent pas visuellement,
  sauf que le cou et la tête suivent désormais le tronc).
- **Un troisième angle, `twist`** (rotation autour de l'axe vertical du modèle au repos, donc
  rotation axiale pour un os vertical : tête, cou, tronc, bras, avant-bras = pronation et supination,
  jambe). Ordre de composition : `twist`, puis `lateral`, puis `flexion`.
- **Muscles de tout le corps** (environ 200 à 250 objets, tous les muscles superficiels et
  profonds des membres, du tronc, de la nuque, plus ceux de la main et du pied). Exclus : visage,
  yeux, langue, larynx, pharynx, oreille, plancher pelvien profond, muscles intercostaux (très lourds
  et sans intérêt pour l'étirement), fascias et tendons modélisés comme muscles.
- **Poids de peau par zone d'articulation, sans Automatic Weights.** Le solveur de Blender échouait
  de façon non déterministe (voir `tools/blender/README.md`). Chaque muscle reçoit une liste d'os
  candidats ; ses sommets sont pondérés par leur position le long de l'axe de l'articulation avec
  un lissage (un biceps passe progressivement de `upper_arm` à `forearm`). Un muscle à un seul os
  reste rigide à 100 %.
- **Poids du fichier** : maillages simplifiés (modificateur Decimate) pour tenir dans **25 Mo**
  environ (le fichier actuel pèse 16 Mo pour 54 muscles).
- **Régions** (cibles d'exercice, colorées en bleu) : `neck`, `head`, `trunk`, `shoulder`,
  `upper_arm`, `lower_arm`, `hand`, `hip`, `thigh`, `lower_leg`, `foot`. Les quatre zones RULA
  existantes (`neck`, `trunk`, `upper_arm`, `lower_arm`) gardent leur sens et leurs couleurs de
  niveau d'action ; les nouvelles régions restent grises dans l'analyse (aucune donnée mesurée,
  donc aucune couleur, même principe que pour les cuisses).
- **Avatar piloté par la vidéo** : les nouveaux os sont orientés avec les points MediaPipe Pose
  disponibles (poignet, pouce, index, auriculaire, talon, bout du pied, oreilles, nez). Les os sans
  point (`fingers`, `toes`) suivent leur parent.

## Hors périmètre

- Mesure des doigts et des poignets par MediaPipe Hands, zones et seuils RULA correspondants
  (Tranche 5).
- Mouvements fins : chaque doigt séparément, vertèbres une à une, mâchoire, expressions.
- Validation médicale des exercices (reste à faire par l'ostéopathe).

## Vérifications

- Tests des invariants du modèle (`muscleRigInvariants.test.ts`) : 24 os présents, aucun muscle sans
  poids, somme des poids = 1, chaque région a au moins un muscle.
- Tests d'angles : repère mesuré sur le vrai modèle (gauche = +x, avant = +z), un test par canal et
  par type d'os.
- Rendu réel d'une vidéo avec Chromium sur les exercices existants et sur de nouveaux exercices
  (poignet, rotation du cou, hanche, cheville).
