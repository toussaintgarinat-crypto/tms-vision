# Avatar 3D de posture — Tranche 4 : coloration par segment anatomique (sous-scores RULA)

**Date** : 2026-09-21
**Statut** : Approuvé (design), implémentation à planifier

## Contexte

La Tranche 3 a livré de vrais muscles Z-Anatomy (54 objets, skinnés sur les 9 os du squelette
articulé de la Tranche 2) mais avec une **teinte uniforme** : tous les matériaux importés prennent
la couleur du `action_level` global (le score RULA final combiné), sans distinction entre segments
anatomiques. Cette tranche remplace cette teinte uniforme par une coloration **par segment** :
chaque groupe musculaire (cou, tronc, bras, avant-bras) prend la couleur de son propre sous-score
RULA, déjà calculé par le moteur de scoring mais jusqu'ici jeté avant d'atteindre le frontend.

**Recherche faite avant ce document** (voir aussi la note de numérotation de
`docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-design.md`, qui identifiait déjà cette
tranche comme "Tranche 4 future") :

- **`RulaScore`** (`src/tms_vision/rula/scoring.py:104-120`) porte déjà, calculé à chaque frame où
  une pose est détectée, un sous-score entier par segment : `neck` (1-6), `trunk` (1-6), `upper_arm`
  (1-6), `lower_arm` (1-3), en plus de `wrist` (1-4), `wrist_twist`, `legs` (constante fixe `1`,
  jamais mesurée — `LEGS_SCORE`, `scoring.py:9`) et du `final_score`/`action_level` combinés déjà
  exposés. Ces sous-scores existent en mémoire dans `pipeline.py:135-138` mais sont **jetés** :
  `Pose3DFrameRecord` (`pose3d_export.py:13-19`) et `pipeline.py:157` ne propagent que
  `score.action_level`.
- **Aucune distinction gauche/droite n'existe dans le scoring.** Le pipeline analyse un seul côté
  par vidéo (`side: Literal["left", "right"]`, choisi par l'utilisateur, `api.py:132`) —
  `compute_joint_angles(landmarks, side, ...)` (`angles.py:86`) ne calcule qu'un seul
  `upper_arm`/`lower_arm`/`wrist` par frame, pas un par côté. Il n'existe donc pas de donnée pour le
  bras/avant-bras du côté non analysé.
- **`action_level()`** (`scoring.py:94-101`) est une fonction pure `int -> str` à seuils fixes
  (`<=2` acceptable, `<=4` investigation_recommandee, `<=6` investigation_et_changement_bientot,
  `>=7` changement_immediat), déjà découplée du calcul du score final — directement réutilisable
  telle quelle sur n'importe quel sous-score entier, sans modification.
- **`wrist`/`legs` n'ont pas de muscle correspondant dans le rig actuel** : le squelette s'arrête à
  `forearm` (pas d'os poignet), et `L_thigh`/`R_thigh` existent comme os mais leur unique source de
  score (`legs`) est une constante jamais mesurée depuis la vidéo.
- **Chaque `SkinnedMesh` importé de `muscle-rig.glb` porte un skinning déjà résolu** (`skinIndex`/
  `skinWeight`, voir Tranche 3) dont l'os dominant est déterminable par sommation des poids — sans
  avoir besoin de dupliquer la table de ~30 noms de muscles Z-Anatomy (`rig_spec.py:60-120`) côté
  TypeScript.

## Décisions de cadrage

- **Un seul côté coloré par segment ; l'autre reste gris fixe.** Comme le pipeline n'analyse qu'un
  seul côté, seuls les muscles du bras/avant-bras du côté effectivement analysé (`side`) sont
  colorés par leur sous-score. Les muscles du bras/avant-bras du côté non analysé gardent en
  permanence la teinte neutre grise déjà utilisée aujourd'hui avant toute détection (`DEFAULT_COLOR`,
  `#9E9E9E`) — jamais la couleur globale, jamais une fausse donnée pour un côté qui n'a jamais été
  mesuré. Le cou et le tronc (os uniques, sans variante gauche/droite) ne sont pas concernés par
  cette règle.
- **Les cuisses gardent le comportement de la Tranche 3, inchangé.** `legs` étant une constante
  jamais mesurée, colorer `L_thigh`/`R_thigh` par ce score afficherait toujours la même couleur
  "acceptable" indépendamment de la vraie posture — trompeur. Les muscles de cuisse continuent donc
  de suivre la teinte uniforme du `action_level` global, exactement comme tous les muscles le
  faisaient avant cette tranche.

  > **Correction (2026-09-21, revue finale de branche complète)** : une revue portant sur
  > l'ensemble de la branche (pas seulement tâche par tâche) a relevé une interaction entre deux
  > décisions individuellement approuvées ailleurs dans ce document, invisible tant que chacune
  > n'était examinée qu'isolément. D'une part, les seuils de couleur des 4 vrais segments RULA
  > (`neck`/`trunk`/`upper_arm`/`lower_arm`) sont structurellement plafonnés — sous-score brut max
  > 6 (`neck`/`trunk`/`upper_arm`) ou 3 (`lower_arm`), et `action_level()` ne retourne
  > `changement_immediat` (rouge) qu'à partir de 7 — donc **aucun des 4 segments réels ne peut
  > jamais afficher rouge**, quelle que soit la sévérité de la posture (voir la puce "Seuils de
  > couleur réutilisés tels quels" ci-dessus, déjà actée). D'autre part, la puce ci-dessus
  > maintenait les cuisses sur la teinte du `action_level` GLOBAL, qui lui n'est pas plafonné de la
  > même façon et peut légitimement atteindre rouge. Conséquence mesurée sur la vidéo de référence
  > du projet (`moi coupe.mp4`, 798 frames) : sur les 36 frames où le score global affiché était
  > rouge (`changement_immediat`), les 4 segments réels affichaient tous jaune/orange ce même
  > instant (jamais rouge, par construction) — **rouge n'apparaissait donc jamais que sur les
  > cuisses**, le seul segment du corps sans aucun signal réellement mesuré depuis la vidéo (`legs`
  > est `LEGS_SCORE`, une constante codée en dur, `scoring.py:9` — jamais dérivée de la pose
  > détectée). Visuellement, l'avatar pouvait ainsi passer au rouge sur les cuisses en réponse à une
  > mauvaise posture du cou/tronc/bras, en laissant croire à tort à un signal de jambe.
  >
  > **Décision produit explicite de l'humain** (posée pendant cette revue, tranchée directement,
  > pas rouverte au débat) : les cuisses n'affichent plus la couleur du `action_level` global du
  > tout. Elles passent à une teinte neutre fixe — `DEFAULT_COLOR` (`#9E9E9E`), la même déjà
  > utilisée pour le bras/avant-bras du côté non analysé — en toutes circonstances, y compris
  > quand une posture est détectée. C'est un changement de comportement assumé par rapport à la
  > version originale de cette tranche décrite ci-dessus (qui suivait encore `action_level`), motivé
  > par le même principe déjà appliqué au bras/avant-bras du côté non analysé un peu plus haut dans
  > cette liste : ne jamais afficher une couleur dérivée d'une donnée qui n'a pas réellement été
  > mesurée pour la partie du corps concernée. `Pose3DFrame.action_level` reste dans le type
  > TypeScript et dans `pose3d.json` (il décrit fidèlement ce que le backend sérialise toujours) ;
  > seul `PostureAvatar3D.tsx` cesse de le lire pour la coloration des cuisses — plus aucun code de
  > ce composant ne le consulte après ce correctif.
- **Seuils de couleur réutilisés tels quels, pas de normalisation proportionnelle.** Chaque
  sous-score brut est passé directement à `action_level()` (mêmes seuils absolus `<=2`/`<=4`/`<=6`
  que pour le score final). Conséquence assumée : `lower_arm` (échelle 1-3) ne peut jamais afficher
  orange/rouge, et `neck`/`trunk`/`upper_arm` (échelle 1-6) ne peuvent jamais afficher rouge (`7+`
  inatteignable). C'est cohérent avec le barème RULA officiel, où ces segments pèsent structurellement
  moins que le score combiné — préféré à une normalisation proportionnelle qui ferait dériver la
  couleur affichée de la sévérité clinique réelle.
- **`side` exposé via la réponse d'analyse, pas via `pose3d.json`.** `pose3d.json` reste un tableau
  de frames (aucun changement de forme, pas de wrapper) : chaque frame gagne seulement un nouveau
  champ additif `segment_action_levels`. `side` est ajouté à la réponse JSON existante de
  `POST /analyses` / `POST /uploads/.../complete` (`_analyze_and_build_response`, `api.py`), où il
  est déjà disponible en paramètre — pas relu depuis l'état local du formulaire côté frontend
  (`page.tsx`), pour éviter qu'un changement du sélecteur "côté" après affichage d'un résultat ne
  désynchronise l'avatar affiché du côté réellement analysé pour ce résultat-là.
- **Pas de nouvelle table de noms de muscles côté TypeScript.** Le mapping muscle → segment RULA se
  fait par l'os dominant du skinning déjà présent dans le `.glb` (voir Approche), pas par une
  duplication de la liste de ~30 noms d'objets Z-Anatomy de `rig_spec.py`. Seule une table de 9
  entrées (une par `BoneKey`) est nécessaire côté frontend.
- **`wrist`, `wrist_twist`, `muscle_use_score`, `force_load_score` non exposés.** Aucun muscle du rig
  actuel ne leur correspond (pas d'os poignet ; ce sont des modificateurs scalaires, pas des scores
  anatomiques). Hors périmètre de cette tranche.

### Liste des segments retenus

| Segment RULA | Échelle | Os concerné(s) | Muscles Tranche 3 concernés |
|---|---|---|---|
| `neck` | 1-6 | `neck` | Trapezius (3 parties), Sternocleidomastoid |
| `trunk` | 1-6 | `spine` | Erector spinae, Rectus abdominis, External abdominal oblique, Latissimus dorsi |
| `upper_arm` | 1-6 | `L_upper_arm` / `R_upper_arm` | Deltoid (3 parties), Biceps brachii (2 chefs), Triceps brachii (3 chefs) |
| `lower_arm` | 1-3 | `L_forearm` / `R_forearm` | Brachioradialis, Flexor/Extensor carpi ulnaris, Extensor digitorum |
| *(aucun — teinte globale)* | — | `L_thigh` / `R_thigh` | Quadriceps femoris, Biceps femoris |

## Approche

```
Backend (Python) — additif, pas de rupture de forme
──────────────────────────────────────────────────────────────
scoring.py            : INCHANGÉ (action_level() déjà réutilisable telle quelle)
pipeline.py            : calcule segment_action_levels à partir du RulaScore déjà
                          en mémoire (ligne ~155), juste à côté de action_level existant
pose3d_export.py       : Pose3DFrameRecord + write_pose3d_json gagnent un champ
                          additif `segment_action_levels: dict[str, str] | None`
api.py                 : _analyze_and_build_response ajoute "side": side à la
                          réponse JSON existante (déjà en paramètre de la fonction)
                    │
                    ▼
        pose3d.json (frames enrichies) + réponse POST /analyses (side)

Frontend (Next.js) — résolution par bone dominant, pas par nom de muscle
──────────────────────────────────────────────────────────────────────────
page.tsx                : stocke `side` depuis la réponse d'analyse, le passe
                           en prop à PostureAvatar3D avec le résultat affiché
PostureAvatar3D.tsx      : pour chaque SkinnedMesh, résout son bone dominant
                           (somme skinWeight par skinIndex, argmax) puis son
                           segment via une table statique BoneKey -> segment ;
                           colore chaque mesh par segment_action_levels[segment]
                           (ou action_level global si segment == null, ou gris
                           fixe si bone du côté non analysé)
```

## Détail — Backend

- `pipeline.py` (juste après le calcul de `score`, ligne ~137) : construit
  `segment_action_levels = None if score is None else {"neck": action_level(score.neck), "trunk":
  action_level(score.trunk), "upper_arm": action_level(score.upper_arm), "lower_arm":
  action_level(score.lower_arm)}`, passé au `Pose3DFrameRecord` construit juste après.
- `pose3d_export.py` : `Pose3DFrameRecord` gagne le champ `segment_action_levels: dict[str, str] |
  None`. `write_pose3d_json` sérialise ce champ tel quel (`dict` JSON-compatible nativement, pas de
  transformation nécessaire).
- `api.py` : `_analyze_and_build_response` retourne `"side": side` en plus des champs existants
  (`annotated_video_url`, `csv_url`, `pose3d_url`).

## Détail — Frontend

- `page.tsx` : le type de réponse d'analyse (actuellement avec `pose3d_url: string`, ligne ~27)
  gagne `side: "left" | "right"`. La valeur est lue depuis `result.side` (la réponse stockée), pas
  depuis l'état local `side` du formulaire, puis passée en prop à `<PostureAvatar3D side={result.side}
  .../>`.
- `PostureAvatar3D.tsx` :
  - Nouveau type `Pose3DFrame.segment_action_levels: Record<string, string> | null`.
  - Nouvelle table statique (9 entrées, une par `BoneKey`) : `spine -> "trunk"`, `neck -> "neck"`,
    `L_upper_arm`/`R_upper_arm -> "upper_arm"`, `L_forearm`/`R_forearm -> "lower_arm"`,
    `L_thigh`/`R_thigh -> null`, `root -> null`.
  - Résolution du bone dominant par `SkinnedMesh`, calculée une fois par mesh dans un `useMemo`
    (dépend de `skinnedMeshes`, ne change jamais au runtime — le skinning est figé après chargement
    du `.glb`) : pour chaque vertex, accumuler `skinWeight[i]` dans un total par `skinIndex[i]`
    (4 slots par vertex), puis prendre l'os dont le total accumulé est le plus élevé sur l'ensemble
    du mesh.
  - Pour un bone dont le nom commence par `L_`/`R_`, en déduire le côté (`"left"`/`"right"`) ;
    `spine`/`neck` n'ont pas de côté.
  - Boucle `useFrame` : remplace le `lastKnownColorRef` unique actuel par une petite structure avec
    une entrée par segment (`neck`, `trunk`, `upper_arm`, `lower_arm`) plus l'entrée globale déjà
    existante (pour les cuisses), chacune mise à jour indépendamment depuis
    `frame.segment_action_levels`/`frame.action_level` quand disponible, sinon conservant sa dernière
    valeur connue (même principe de repli que le code actuel). Pour chaque matériau cloné : si le
    mesh correspondant a un segment `null` → couleur globale (cuisses, comportement Tranche 3
    inchangé) ; sinon si son côté ne correspond pas à `side` → gris fixe (`DEFAULT_COLOR`) ; sinon →
    couleur de son segment.

## Tests

- **Backend** : étendre `tests/test_pose3d_export.py` pour couvrir `segment_action_levels` (présent
  quand `action_level` l'est, `None` sinon). Pas de nouveau test pour `action_level()` elle-même
  (fonction déjà testée, réutilisée sans modification).
- **Frontend** : nouveau test unitaire pur pour la fonction de résolution "bone dominant par mesh"
  (entrées `skinIndex`/`skinWeight` synthétiques, pas besoin de charger le vrai `.glb`) et pour la
  table `BoneKey -> segment`. Les tests existants de `pose3dSkeleton.test.ts` ne sont pas affectés
  (module non modifié).
- **Vérification manuelle obligatoire** (comme les tranches précédentes) : rejouer `moi coupe.mp4`,
  confirmer que chaque segment (cou, tronc, bras du côté analysé, avant-bras du côté analysé) se
  colore indépendamment au fil de la lecture, que le bras/avant-bras du côté non analysé reste gris
  en permanence, et que les cuisses suivent toujours la teinte globale comme en Tranche 3 (voir la
  correction du 2026-09-21 ci-dessus : les cuisses passent finalement en gris fixe, comme le
  bras/avant-bras non analysé — ce critère d'acceptation n'a pas été mis à jour rétroactivement,
  ne pas l'appliquer littéralement).

## Hors périmètre (cette tranche)

- Analyse simultanée des deux côtés (gauche + droit) — changement du pipeline RULA lui-même, hors
  périmètre.
- Coloration des cuisses par un vrai signal mesuré (dépend d'un score `legs` réellement calculé
  depuis la vidéo, qui n'existe pas aujourd'hui).
- Segments `wrist`/`wrist_twist` — pas d'os poignet dans le rig actuel.
- Seuils de couleur proportionnels par segment (option écartée, voir Décisions de cadrage).
- Musculature complète (~600 muscles) — hors périmètre depuis la Tranche 3.
- Correction du roll/torsion des os, cascade d'échelle sur hanche jamais détectée — limites connues
  depuis la Tranche 2, non résolues ici.
