# Avatar 3D de posture — Tranche 2 : squelette articulé + preuve de skinning

**Date** : 2026-09-16
**Statut** : Approuvé

## Contexte

La Tranche 1 (`docs/superpowers/specs/2026-09-16-3d-posture-avatar-design.md`) a livré un mannequin
3D piloté par la pose : 10 capsules + une tête, chacune positionnée **indépendamment** à chaque
frame à partir d'une paire de landmarks 3D (`pose3d.json`, déjà lissé côté backend). Ce document est
"Ready to merge" et vérifié sur une vraie vidéo (voir `.superpowers/sdd/progress.md`).

L'utilisateur du projet souhaite maintenant un avatar avec de vrais muscles (inspiration Muscle &
Motion / Z-Anatomy), avec un vrai skinning articulé aux jointures (pas un simple rattachement rigide
par segment). Recherche faite pendant le brainstorming :

- **Z-Anatomy n'a pas encore d'assets exportés** côté projet : il faudra les sourcer depuis le
  projet Z-Anatomy (Blender, CC BY-SA, dérivé de BodyParts3D) — chantier de sourcing/export en plus
  du code, prévu pour la tranche suivante.
- **Objectif retenu : musculature complète** (~600 muscles Z-Anatomy), pas un sous-ensemble.
- **Un vrai skinning articulé est demandé explicitement** (muscles qui suivent une vraie
  hiérarchie squelettique aux jointures, par opposition à un rattachement rigide par segment). Ça
  ne peut pas se brancher sur le rig de la Tranche 1, qui n'a **aucune hiérarchie** : chaque capsule
  est positionnée en absolu, sans relation parent-enfant, donc rien à quoi "skinner" un maillage.
  Un vrai skinning (`THREE.SkinnedMesh` + `THREE.Skeleton`) exige une hiérarchie d'os avec des
  matrices de bind et des rotations locales — une fondation différente, pas une extension du rig
  existant.
- **Inconnue non résolue** : on ne sait pas si les assets Z-Anatomy sont déjà riggés/skinnés pour
  l'animation (c'est un atlas 3D pensé pour une caméra orbitale autour d'une pose figée, pas
  nécessairement pour être animé). Si non, le weight-painting manuel de ~600 muscles serait un
  chantier de plusieurs semaines, hors de portée d'un cycle d'implémentation normal. **Cette
  question est explicitement reportée au démarrage de la tranche suivante** (recherche avant tout
  code), pas résolue ici.

Face à ce risque, le travail a été découpé en deux tranches séquentielles :

1. **Tranche 2 (ce document)** — construire un vrai squelette articulé (hiérarchie d'os,
   rotations locales dérivées des landmarks 3D existants) et prouver que le mécanisme de skinning
   fonctionne, avec un maillage de test simple (pas anatomique). **Pas de changement visuel majeur
   attendu** — le rendu restera proche des capsules de la Tranche 1. La justification de cette
   tranche est entièrement dans ce qu'elle prépare, pas dans un gain visible immédiat (explicitement
   accepté par l'utilisateur du projet pendant le brainstorming).
2. **Tranche 3 (future, à brainstormer séparément)** — recherche sur la riggabilité réelle de
   Z-Anatomy, sourcing/export des maillages musculaires, puis skinning des vrais muscles sur le
   squelette construit ici. C'est cette tranche qui doit livrer le changement visuel attendu par
   l'utilisateur du projet ("je veux qu'on l'améliore dès le prochain sprint").

Ce document ne couvre que la Tranche 2.

## Décisions de cadrage

- **Squelette articulé (hiérarchie parent-enfant), pas des segments indépendants.** C'est le
  changement central de cette tranche : remplacer le positionnement absolu de chaque capsule par une
  vraie chaîne d'os (`THREE.Bone`) où chaque os est exprimé en rotation locale relative à son parent.
  C'est la fondation obligatoire pour tout skinning futur.
- **Même géométrie corporelle que la Tranche 1 (8 os + racine), pas plus.** Reprend exactement les
  10 paires de landmarks déjà utilisées par `overlay.py::_SKELETON_CONNECTIONS` /
  `PostureAvatar3D.tsx::SKELETON_CONNECTIONS`, réorganisées en hiérarchie (voir Approche). Pas de
  nouveaux points de tracking, pas de mains/doigts/jambes sous le genou (mêmes limites assumées
  depuis la Phase 1).
- **Rotations calculées côté client, à partir du `pose3d.json` existant.** Aucun changement backend.
  Le calcul (direction landmarks → rotation locale par os) est un pur problème de rendu, cohérent
  avec la façon dont la Tranche 1 calculait déjà position/orientation des capsules côté client.
- **Roll/torsion de chaque os non résolu — limite documentée, pas un bug.** MediaPipe donne des
  positions de landmarks, pas des rotations : on peut déduire la direction d'un os (swing) mais pas
  sa torsion propre autour de son propre axe (ex. pronation/supination de l'avant-bras, rotation
  interne/externe de l'épaule). Cette tranche fixe le roll à une valeur par défaut (constante) plutôt
  que d'essayer de le déduire — un vrai calcul demanderait un modèle de pose plus riche
  (ex. reconstruction de maillage corporel complet type SMPL), hors de portée. À revalider
  visuellement à l'usage : si l'absence de roll produit des artefacts visuels gênants une fois de
  vrais muscles skinnés (tranche 3), ce sera republié comme limite connue, pas silencieusement.
- **Preuve de skinning avec un maillage de test non anatomique, dans cette tranche.** Décision prise
  explicitement pendant le brainstorming pour ne pas découvrir des problèmes de skinning en pleine
  tranche 3, alourdis par la complexité des vrais assets Z-Anatomy. Le maillage de test est un
  `THREE.SkinnedMesh` grossier (assemblage de cylindres en un seul `BufferGeometry`), avec un poids
  de peau à 100% sur l'os le plus proche par vertex (pas de blending aux jointures — pas le sujet de
  cette tranche). Le but est de valider la mécanique bind pose → matrices d'os → déformation du mesh,
  pas la qualité visuelle du mesh de test lui-même.
- **Couleur uniforme par frame, inchangée depuis la Tranche 1.** La coloration par muscle reste
  reportée à une tranche future (déjà noté ainsi dans la spec Tranche 1).

## Approche

```
Frontend (Next.js), aucun changement backend
──────────────────────────────────────────────────────
pose3d.json (existant, inchangé)
  │
  ▼
pose3dSkeleton.ts (NOUVEAU, module pur)
  ├─ buildSkeleton()                    → construit la hiérarchie THREE.Bone une fois au montage
  │     root (milieu hanches)
  │     ├─ spine (racine → milieu épaules)
  │     │   └─ neck (milieu épaules → NOSE)
  │     ├─ L_upper_arm (LEFT_SHOULDER → LEFT_ELBOW), parent = spine
  │     │   └─ L_forearm (LEFT_ELBOW → LEFT_WRIST)
  │     ├─ R_upper_arm (idem droite)
  │     │   └─ R_forearm
  │     ├─ L_thigh (LEFT_HIP → LEFT_KNEE), parent = root
  │     └─ R_thigh (idem droite)
  │
  └─ applyFrameToSkeleton(skeleton, frame)  → appelé à chaque frame (useFrame)
        pour chaque os : direction monde landmarks → quaternion local relatif au bind pose
        frame.detected === false → conserve la dernière pose appliquée (identique Tranche 1)

PostureAvatar3D.tsx (MODIFIÉ)
  ├─ construit le skeleton au montage (buildSkeleton)
  ├─ construit le SkinnedMesh de test, lié au skeleton (bind())
  ├─ à chaque frame : applyFrameToSkeleton(skeleton, frameLaPlusProche(video.currentTime))
  ├─ couleur uniforme par action_level (inchangé)
  └─ OrbitControls, message "aucune posture détectée" (inchangés)
```

## Structure du projet (ajouts sur l'existant)

```
TMS vision/
└── web/
    └── app/
        ├── pose3dSkeleton.ts        # NOUVEAU — hiérarchie d'os, calcul des rotations par frame
        └── PostureAvatar3D.tsx      # MODIFIÉ — squelette + SkinnedMesh de test au lieu de
                                       #   capsules indépendantes ; logique vidéo/OrbitControls/
                                       #   couleur/fallback inchangée
```

## Détail — `pose3dSkeleton.ts`

- `BONE_DEFINITIONS` : table déclarative `{ name, parentName, fromLandmark, toLandmark }` pour les 8
  os (voir Approche). `root` et `spine`/`neck` sont des cas particuliers (`fromLandmark`/`toLandmark`
  calculés comme milieux de paires de landmarks — `LEFT_HIP`/`RIGHT_HIP` pour la racine,
  `LEFT_SHOULDER`/`RIGHT_SHOULDER` pour l'extrémité de `spine`).
- `buildSkeleton(): THREE.Skeleton` : instancie les `THREE.Bone` selon `BONE_DEFINITIONS`, les
  chaîne en hiérarchie (`bone.add(childBone)`), définit une bind pose de repos (ex. os alignés
  verticalement, longueur par défaut arbitraire — la vraie longueur/direction sera appliquée dès la
  première frame par `applyFrameToSkeleton`). Retourne `{ skeleton, bones }` (map nom → `THREE.Bone`)
  pour que `PostureAvatar3D.tsx` puisse construire le `SkinnedMesh` de test à partir des mêmes
  références d'os.
- `applyFrameToSkeleton(bones, frame, lastKnownLandmarksRef)` : pour chaque os, calcule la direction
  monde `toLandmark - fromLandmark` à partir de `frame.landmarks` (ou `lastKnownLandmarksRef.current`
  si `frame.detected === false`, même garde-fou que la Tranche 1), en déduit le quaternion de
  rotation locale relatif à la direction de repos du parent (remontée de la hiérarchie), applique
  aussi la position de la racine (translation globale du rig). Le roll reste fixé à 0 (voir
  Décisions de cadrage).

## Détail — `PostureAvatar3D.tsx`

- Au montage : `buildSkeleton()` une fois, construit un `THREE.SkinnedMesh` de test à partir d'une
  géométrie procédurale simple (cylindres assemblés couvrant approximativement chaque os), avec
  `skinIndex`/`skinWeight` assignés par proximité (100% sur l'os le plus proche par vertex), lié au
  `THREE.Skeleton` (`mesh.bind(skeleton)`).
- Dans `useFrame` (remplace la boucle actuelle de positionnement des capsules) :
  `applyFrameToSkeleton(bones, frame, lastKnownLandmarksRef)`, puis couleur du matériau du
  `SkinnedMesh` = couleur de l'`action_level` courant (même logique qu'aujourd'hui, un seul matériau
  au lieu d'un par capsule).
- Fallback "aucune posture détectée" et `OrbitControls` : inchangés.

## Tests

- `pose3dSkeleton.ts` (nouveau fichier de test, même limite d'infra que la Tranche 1 côté `web/` —
  pas de suite automatisée existante ; si un framework léger est mis en place à cette occasion,
  limité à ce fichier) :
  - `buildSkeleton()` produit bien 8 os + racine, avec les relations parent-enfant attendues.
  - `applyFrameToSkeleton` sur une frame synthétique de référence (ex. bras gauche tendu à
    l'horizontale, autres os en position neutre) produit la rotation attendue sur `L_upper_arm`
    (calculable à la main, vérifié dans le test).
  - Une frame avec `detected: false` conserve les rotations de la dernière frame détectée (même
    contrat que la Tranche 1, testé au niveau du module).
- **Vérification manuelle obligatoire** (comme les tranches précédentes) : rejouer `moi coupe.mp4`,
  confirmer que le maillage de test suit la posture en synchro avec la vidéo, sans distorsion
  aberrante aux jointures (pas de vertex qui s'envolent au coude/épaule), comparer visuellement à la
  Tranche 1 pour confirmer l'absence de régression de fidélité perçue, et vérifier le comportement
  sur au moins une frame non détectée (pose figée, cohérent avec la Tranche 1).

## Hors périmètre (cette tranche)

- Vrais maillages musculaires Z-Anatomy (sourcing, export, intégration) — Tranche 3.
- Recherche sur la riggabilité réelle des assets Z-Anatomy (armature/poids déjà existants ou non) —
  reportée au démarrage de la Tranche 3, pas traitée ici.
- Roll/torsion des os (pronation, rotation interne de l'épaule) — limite connue des données
  MediaPipe, fixée à une valeur par défaut, non résolue.
- Blending de poids de peau aux jointures — le maillage de test utilise un poids 100% par vertex sur
  l'os le plus proche, suffisant pour valider la mécanique, pas pour un rendu final soigné.
- Coloration par muscle/segment individuel — déjà reportée depuis la Tranche 1 à une tranche future.
- Mode miroir en direct, mains/doigts, jambes sous le genou — mêmes limites qu'en Tranche 1.
