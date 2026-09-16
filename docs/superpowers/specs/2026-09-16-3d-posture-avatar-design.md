# Phase 2 (nouvelle sous-piste) — Avatar 3D de posture, Tranche 1 : mannequin piloté par la pose

**Date** : 2026-09-16
**Statut** : Approuvé

## Contexte

Le 2026-09-16, une première vidéo réelle (`moi coupe.mp4`, filmée de profil) a été analysée avec
le pipeline CLI (voir mise à jour de la section 8 du README) : 746/798 frames avec pose détectée,
score RULA max 7, moyenne 4.6, squelette vérifié visuellement correct par l'utilisateur du projet.
Ça valide le point de vérification qui restait ouvert depuis la Phase 1.

En regardant le rendu actuel (`src/tms_vision/overlay.py`) — des traits blancs fins de 2px reliant
les articulations — l'utilisateur du projet a exprimé le souhait d'un rendu plus incarné,
inspiré d'outils comme Muscle & Motion (modèles 3D animés à la main montrant les muscles se
contracter/s'allonger pendant un mouvement) et Z-Anatomy (atlas 3D open-source des structures
anatomiques, dont les muscles, basé sur le jeu de données BodyParts3D).

Recherche faite pendant le brainstorming : ces deux références sont des modèles 3D construits par
des équipes d'illustrateurs/animateurs, **non pilotés par une vidéo réelle** — Muscle & Motion
anime une bibliothèque d'exercices pré-fabriqués, Z-Anatomy est un atlas statique/interactif. Ce
que demande l'utilisateur du projet est un pont entre ces deux mondes : un modèle 3D avec de vrais
muscles, piloté par la posture extraite de sa propre vidéo. C'est un sous-projet à part entière,
découpé en tranches séquentielles comme le reste de la Phase 2 :

1. **Tranche 1 (ce document)** — mannequin 3D simple (capsules, pas encore de muscles) piloté par
   la pose extraite de la vidéo, rejoué en synchro dans le navigateur.
2. **Tranche 2 (future)** — intégration de vrais maillages musculaires (dérivés de Z-Anatomy,
   licence CC BY-SA — attribution à prévoir) riggés sur le squelette 3D de la tranche 1.
3. **Tranche 3 (future)** — activation/coloration des muscles par segment anatomique, à partir des
   sous-scores RULA déjà calculés par frame (`neck`, `trunk`, `upper_arm`, `lower_arm`, `wrist`
   dans l'export CSV existant).

Ce document ne couvre que la Tranche 1. Les tranches 2 et 3 seront brainstormées séparément une
fois celle-ci livrée et validée sur une vraie vidéo.

## Décisions de cadrage

- **Rejoué après analyse, pas un mode miroir en direct.** Deux options étaient possibles : (a)
  calculer les données 3D côté serveur pendant l'analyse existante et les rejouer en synchro avec
  la vidéo une fois l'analyse terminée, ou (b) un avatar en temps réel piloté par MediaPipe tournant
  dans le navigateur (WebAssembly) pendant la capture caméra, avant tout envoi à l'API.
  **Choix : (a).** Raisons : une estimation de pose hors-ligne peut utiliser un modèle plus
  précis et un lissage temporel sur toute la séquence (y compris les frames futures), alors qu'un
  flux temps réel doit rester léger et causal (donc plus bruité) ; et surtout, l'avatar anime
  exactement les mêmes données que celles qui ont produit le score RULA affiché — une seule
  estimation de pose, pas de divergence possible entre ce que montre l'avatar et ce que dit le
  score. Le mode miroir en direct reste une extension future possible (le renderer 3D construit ici
  sera réutilisable, seule la source de données changerait) mais n'est pas dans le scope de cette
  tranche.
- **Rendu dans le navigateur (Three.js), pas côté serveur.** L'alternative (rendu 3D headless en
  Python, vidéo de sortie comme aujourd'hui) est rejetée : l'écosystème 3D web (react-three-fiber)
  est nettement plus mature pour ce type de rendu que le rendu headless Python (Blender/bpy ou
  OpenGL direct), et permet une caméra orientable par l'utilisateur (voir plus bas) sans complexité
  supplémentaire côté serveur.
- **Caméra orientable (OrbitControls), pas fixe.** C'est l'intérêt principal d'avoir un vrai modèle
  3D plutôt qu'une vidéo 2D : pouvoir observer la posture sous un angle que la caméra d'origine ne
  montrait pas (ex. de face si la vidéo a été filmée de profil).
- **Rig = mêmes segments que le squelette 2D actuel, pas plus.** `overlay.py::_SKELETON_CONNECTIONS`
  (cou-tronc, épaules, bras/avant-bras gauche et droit, hanches, hanches-genoux) devient des
  capsules 3D + une sphère pour la tête. Pas de mains/doigts, pas de jambes sous le genou — cohérent
  avec la limite déjà assumée en Phase 1 ("jambes fixées à soutenues").
- **Couleur uniforme par frame, pas encore par segment.** L'avatar entier prend la couleur du
  niveau d'action RULA global de la frame courante (même palette que le badge déjà affiché sur la
  vidéo annotée, `overlay.py::_COLOR_BY_LEVEL`). La coloration par segment individuel (cou vs bras
  vs tronc) est reportée à la Tranche 3, où elle rejoint naturellement la logique d'activation
  musculaire — les deux sujets sont liés et n'ont pas besoin d'être résolus deux fois.
- **Pose figée pendant les frames non détectées.** L'avatar garde la dernière pose connue plutôt
  que de disparaître ou clignoter, à revalider visuellement une fois testé sur une vraie vidéo avec
  des trous de détection.
- **MediaPipe fournit déjà l'estimation 3D — pas de reconstruction à construire.** `PoseEstimator`
  n'extrait aujourd'hui que `results.pose_landmarks` (2D, coordonnées image). MediaPipe expose aussi
  `results.pose_world_landmarks` : une estimation 3D à l'échelle métrique, produite par le même
  modèle, sans coût de calcul supplémentaire notable. C'est une estimation monoculaire (donc
  imparfaite), mais elle évite un sous-projet de reconstruction 3D dédié.

## Approche

```
Backend (Python, hors-ligne, pendant analyze_video existant)
──────────────────────────────────────────────────────────
PoseEstimator.process()
  └─→ pose_landmarks (2D, existant)         → angles → score RULA → vidéo annotée (inchangé)
  └─→ pose_world_landmarks (3D, NOUVEAU)    → lissage temporel → {run_id}_pose3d.json

Résumé JSON (existant, étendu)
  {..., "pose3d_json": "{run_id}_pose3d.json"}
  → servi comme les autres exports via GET /outputs/{filename} (inchangé)

Frontend (Next.js, après réception du résumé JSON)
───────────────────────────────────────────────────
fetch(pose3d_json) → track de poses 3D en mémoire (tableau indexé par frame)
  │
  ├─ <video> existant (vidéo annotée) ── currentTime ──┐
  │                                                      ▼
  └─ <Canvas> react-three-fiber ──────────── frame le plus proche appliqué au rig
        (capsules + sphère, couleur = action_level de la frame, OrbitControls)
```

## Structure du projet (ajouts sur l'existant)

```
TMS vision/
├── src/tms_vision/
│   ├── pose_estimation.py          # MODIFIÉ — PoseResult gagne world_landmarks
│   ├── pose3d_export.py            # NOUVEAU — lissage temporel + écriture {run_id}_pose3d.json
│   └── pipeline.py                 # MODIFIÉ — appelle pose3d_export après la boucle d'analyse,
│                                    #   ajoute pose3d_path à AnalysisResult, expose son nom dans
│                                    #   le résumé JSON (via export.py)
├── tests/
│   ├── test_pose_estimation.py     # MODIFIÉ — vérifie world_landmarks peuplé
│   └── test_pose3d_export.py       # NOUVEAU — forme du JSON, lissage, frames non détectées
└── web/
    ├── package.json                 # MODIFIÉ — + three, @react-three/fiber, @react-three/drei
    └── app/
        ├── PostureAvatar3D.tsx      # NOUVEAU — scène Three.js, rig, synchro currentTime
        └── page.tsx                 # MODIFIÉ — affiche <PostureAvatar3D> à côté de la vidéo
```

## Détail — Backend

**`pose_estimation.py`** : `Landmark` reste inchangé (x, y, z, visibility). `PoseResult` gagne
`world_landmarks: dict[str, Landmark] | None`, peuplé depuis `results.pose_world_landmarks` de la
même façon que `landmarks` l'est depuis `results.pose_landmarks` (même filtre `min_visibility`,
même nommage par `PoseLandmark.name`). Vérifié sur l'API MediaPipe installée (`landmark_pb2.Landmark`
expose `x, y, z, visibility, presence`) : chaque entrée de `pose_world_landmarks` porte son propre
champ `visibility`, comme son équivalent 2D — pas besoin de réutiliser celui du landmark 2D.

**`pose3d_export.py`** (nouveau) :
- `smooth_world_landmarks(frames: list[dict[str, Landmark] | None], window: int = 5) -> list[...]`
  — moyenne glissante centrée sur `window` frames (ignorant les `None`) pour chaque coordonnée
  x/y/z de chaque landmark nommé. Une frame sans détection reste `None` en sortie (pas d'invention
  de pose là où il n'y en a pas — c'est au frontend de décider de garder la dernière pose connue,
  voir plus bas).
- `write_pose3d_json(path: str, records: list[FrameRecord3D]) -> None` — écrit un tableau JSON,
  un objet par frame : `{"frame_index": int, "timestamp_seconds": float, "detected": bool,
  "landmarks": {"LEFT_SHOULDER": [x, y, z], ...} | null}`.

**`pipeline.py`** : dans `analyze_video()`, `pose_result` (déjà calculé une fois par frame dans la
boucle existante) porte maintenant aussi `world_landmarks` — aucun calcul MediaPipe supplémentaire.
Après la boucle principale (une fois `per_frame_angles` disponible), on construit la liste des
`world_landmarks` par frame, on la lisse via `smooth_world_landmarks`, on écrit
`{run_id}_pose3d.json` via `write_pose3d_json`. `AnalysisResult` gagne `pose3d_path: Path | None`.

**Résumé JSON** (`export.py::ResultsExporter`) : le champ existant qui liste les fichiers de sortie
gagne une entrée pour `pose3d_json` (nom de fichier, comme les autres). Aucun nouvel endpoint API :
`GET /outputs/{filename}` sert déjà n'importe quel fichier du dossier de sortie.

## Détail — Frontend

**`PostureAvatar3D.tsx`** : reçoit en props l'URL du `pose3d_json` et une référence (`ref`) vers
l'élément `<video>` existant.
- Au montage, `fetch()` le JSON une fois, le garde en mémoire (tableau trié par `frame_index`,
  taille attendue de l'ordre de quelques centaines à ~1000 entrées pour une vidéo de quelques
  dizaines de secondes — pas de streaming nécessaire).
- Boucle `requestAnimationFrame` : lit `video.currentTime`, trouve la frame la plus proche par
  `timestamp_seconds` (recherche binaire sur le tableau trié), applique ses coordonnées aux
  capsules/sphère du rig. Si la frame trouvée a `detected: false`, conserve la dernière pose
  appliquée avec succès plutôt que de vider le rig.
- Rig construit avec les mêmes paires que `overlay.py::_SKELETON_CONNECTIONS`, en capsules
  (`@react-three/drei` `<Capsule>` ou géométrie cylindre+demi-sphères), plus une sphère positionnée
  sur `NOSE` pour la tête. Couleur de toutes les capsules = couleur de l'`action_level` de la frame
  courante (même palette que `_COLOR_BY_LEVEL`, portée côté TypeScript).
- `OrbitControls` de `@react-three/drei` pour la caméra (rotation/zoom souris), caméra initiale
  positionnée pour cadrer l'avatar en entier.
- Si `pose3d_json` ne contient aucune frame avec `detected: true` (vidéo sans pose détectée du
  tout), affiche un message ("Aucune posture détectée sur cette vidéo.") à la place de la scène.

**`page.tsx`** : la section résultat affiche `<video>` (existant) et `<PostureAvatar3D>` côte à
côte (grille deux colonnes en desktop, empilé en mobile — cohérent avec le reste de la page qui est
déjà responsive).

## Tests

- `test_pose_estimation.py` : `world_landmarks` peuplé avec les mêmes noms de landmarks que
  `landmarks`, `None` quand aucune pose n'est détectée.
- `test_pose3d_export.py` :
  - `smooth_world_landmarks` : une séquence constante reste constante (pas de dérive introduite
    par le lissage) ; une frame isolée à `None` au milieu d'une séquence détectée reste `None` en
    sortie ; le lissage réduit effectivement la variance d'une séquence bruitée synthétique.
  - `write_pose3d_json` : fichier bien formé, une entrée par frame, `landmarks: null` pour les
    frames non détectées.
- `pipeline.py` (extension d'un test d'intégration existant) : `analyze_video()` sur la vidéo de
  test synthétique produit bien un `pose3d_path`, et le résumé JSON référence son nom de fichier.
- **Frontend** : pas d'infra de test automatisé dans `web/` à ce jour (cohérent avec les tranches
  précédentes). Vérification manuelle obligatoire avant de considérer la tranche terminée : relancer
  l'analyse sur `moi coupe.mp4` (ou une vidéo équivalente), vérifier visuellement que l'avatar 3D
  suit la posture en synchro avec la lecture vidéo, tester la caméra orientable (rotation/zoom), et
  vérifier le comportement sur au moins une frame non détectée (pose figée, pas de disparition).

## Hors périmètre (cette tranche)

- Vrais maillages musculaires (Z-Anatomy ou autre) — Tranche 2.
- Coloration par segment anatomique / logique d'activation musculaire — Tranche 3.
- Mode miroir en direct (MediaPipe côté navigateur pendant la capture caméra) — extension future
  possible, pas dans cette tranche.
- Mains/doigts, jambes sous le genou.
- Attribution/licence Z-Anatomy (CC BY-SA) — non pertinent tant qu'aucun asset Z-Anatomy n'est
  utilisé (Tranche 1 = capsules géométriques simples, pas d'assets externes).
