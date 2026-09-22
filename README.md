# Plateforme de Vision par Ordinateur pour la Prévention des TMS et l'Ergonomie au Travail

## 1. Synthèse Exécutive

Le projet vise à associer la Vision par Ordinateur (Computer Vision) et l'expertise biomécanique d'un ostéopathe pour créer une solution globale d'analyse ergonomique, de prévention des Troubles Musculo-Squelettiques (TMS) et d'optimisation de la gestuelle au travail.

L'objectif est d'abandonner les formations théoriques génériques au profit d'un diagnostic sur-mesure hyper-personnalisé :

1. Filmer le salarié pendant un cycle de travail court (30 secondes à 3 minutes).
2. Analyser automatiquement les contraintes articulaires et les répétitions à risque à l'aide d'IA Open Source.
3. Prescrire des programmes de correction gestuelle et des micro-pauses guidées par des capsules vidéo d'étirements adaptées.

## 2. Analyse Métier & Cas d'Usage

### A. Analyse du poste & Diagnostic (1 à 3 minutes de vidéo)

Il n'est pas nécessaire d'enregistrer des heures de rush. Une séquence représentative d'un cycle métier suffit pour extraire les données fondamentales.

- **Logistique & Manutention** : Port de charges, flexions du tronc, torsions, répétitivité.
- **Industrie & Assemblage** : Postures statiques, bras en élévation, travail au-dessus des épaules.
- **Tertiaire / Bureau** : Position de la tête/cervicales, flexion des poignets, hauteur du buste.

### B. Parcours Utilisateur & Boucle Amélioration

```
┌────────────────────────┐      ┌──────────────────────────┐      ┌──────────────────────────┐
│ 1. Capture Vidéo       │ ───> │ 2. Moteur IA             │ ───> │ 3. Bilan Ostéopathique   │
│ Smartphone / Caméra    │      │ Pose Estimation & Angles │      │ Diagnostic & Score RULA  │
└────────────────────────┘      └──────────────────────────┘      └──────────────────────────┘
                                                                               │
                                                                               ▼
┌────────────────────────┐      ┌──────────────────────────┐      ┌──────────────────────────┐
│ 6. Suivi RH / HSE      │ <─── │ 5. Application Salarié   │ <─── │ 4. Prescriptions         │
│ Tableau de bord global │      │ Micro-pauses & Capsules  │      │ Exercices & Étirements   │
└────────────────────────┘      └──────────────────────────┘      └──────────────────────────┘
```

## 3. Architecture Technique & Choix des Technologies

L'architecture repose à 100 % sur des briques Open Source, permettant une indépendance totale vis-à-vis des abonnements SaaS (comme Roboflow ou les API multimodales payantes) et garantissant la protection des données salariales.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONT-END / CAPTURE                           │
│       Caméra Smartphone / Tablette / Flux RTSP (Vidéo MP4/MOV)          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PIPELINE DE TRAITEMENT (PYTHON)                    │
│  1. Anonymisation : Détection & Floutage de visage (OpenCV / MediaPipe) │
│  2. Pose Estimation : MediaPipe Pose / MMPose (Squelette 33 keypoints)  │
│  3. Moteur Calculateur : Calcul vectoriel d'angles articulaires         │
│  4. Modèle Ergonomique : Implémentation des règles RULA / REBA          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          REST API & DASHBOARD                           │
│  Backend FastAPI (Python) + Database SQLite/PostgreSQL                  │
│  Interface Web : React / Next.js (Visualisation & Recommandations)       │
└─────────────────────────────────────────────────────────────────────────┘
```

## 4. Benchmark des Technologies : Open Source vs Propriétaire

| Brique Fonctionnelle | Solution Propriétaire (ex: Post LinkedIn) | Alternative Open Source Recommandée | Licence OS | Coût Unitaire |
|---|---|---|---|---|
| Gestion / Annotation | Roboflow (SaaS) | CVAT / Label Studio | Apache 2.0 | 0 € |
| Auto-Labeling | API Astra 6 / GPT-Vision | Florence-2 / Qwen2-VL | Apache 2.0 | 0 € |
| Détection / Posture | RF-DETR | MediaPipe Pose / MMPose | Apache 2.0 | 0 € |
| Analyse & Visuel | Python + OpenCV | Python + OpenCV + SciPy | BSD | 0 € |
| Stockage & Serveur | Cloud Propriétaire AWS/GCP | Auto-hébergement (On-Premise / Proxmox) | N/A | Variable (Matériel) |

## 5. Spécifications du Moteur Ergonomique (RULA / REBA)

Le script Python lit les coordonnées (x, y, z) générées par le modèle de Pose Estimation pour calculer les angles biomécaniques réels frame par frame :

- **Angle Cervical** : Flexion/Extension de la tête par rapport à la verticale du buste.
- **Angle Épaule-Coude** : Élévation du bras par rapport à l'axe du corps (seuil critique à 45°).
- **Angle Lombaire** : Flexion du dos lors du ramassage ou du travail sur poste.

### Matrice de Scoring (Exemple RULA)

- **Vert (Score 1-2)** : Posture acceptable, aucun risque immédiat.
- **Jaune (Score 3-4)** : Investigation nécessaire, modifications à prévoir.
- **Orange (Score 5-6)** : Modification du poste à court terme.
- **Rouge (Score 7+)** : Risque élevé de TMS, intervention immédiate requise.

## 6. La Brique "Micro-Pauses & Capsules Vidéo"

Cette brique constitue l'outil de remédiation quotidienne de l'application.

### Médiathèque de l'Ostéopathe

- Bibliothèque de 30 à 45 vidéos courtes (30 à 60 secondes).
- Exercices catégorisés par zone anatomique (Rachis cervical, Lombaires, Épaules, Poignets/Mains, Hanches).

### Déclenchement Intelligent

Une fois la vidéo de poste analysée, le système associe les scores d'angles critiques aux capsules d'étirement correspondantes.

### Module Salarié (Web App / Mobile)

- Notification / Rappel de micro-pause.
- Lancement de la capsule vidéo guidée (ex: "3 étirements pour décompresser les cervicales après 2 heures sur écran").
- Optionnel : Vérification en temps réel via la webcam que l'exercice d'étirement est correctement exécuté.

## 7. Conformité RGPD & Sécurité des Données

L'analyse de l'image des salariés en entreprise est fortement encadrée par la CNIL et le RGPD.

- **Anonymisation à la source** : Le visage du salarié est flouté dès la première étape du traitement vidéo via un module OpenCV local, avant toute sauvegarde ou analyse d'angles.
- **Traitement On-Premise / Edge** : L'analyse vidéo s'exécute en local ou sur un serveur interne à l'entreprise. Aucune vidéo brute ne fuite vers des services Cloud tiers.
- **Droits des salariés** : Consentement préalable et droit d'accès au bilan individuel.

## 8. Feuille de Route de Déploiement (Roadmap MVP)

**Pour reprendre le projet plus tard**, les documents de référence sont :
- Ce README (vue d'ensemble produit + usage du PoC, section 9 ; capture web, section 10).
- `docs/superpowers/specs/2026-09-14-poc-pose-rula-design.md` — la spec technique détaillée du PoC (Phase 1).
- `docs/superpowers/plans/2026-09-14-poc-pose-rula-plan.md` — le plan d'implémentation tâche par tâche du PoC (tenu à jour au fil des corrections).
- `docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md` — la spec de la 1ère tranche de la Phase 2 (capture web + API FastAPI).
- `docs/superpowers/plans/2026-09-14-web-capture-fastapi-plan.md` — le plan d'implémentation de cette tranche.
- `docs/superpowers/specs/2026-09-15-web-upload-chunked-design.md` — la spec de la tranche 2 de la Phase 2 (upload de fichier vidéo par chunks).
- `docs/superpowers/plans/2026-09-15-web-upload-chunked-plan.md` — le plan d'implémentation de cette tranche.
- `docs/superpowers/specs/2026-09-16-3d-posture-avatar-design.md` — la spec de la tranche 1 de l'avatar 3D de posture (mannequin 3D piloté par la pose).
- `docs/superpowers/plans/2026-09-16-3d-posture-avatar-plan.md` — le plan d'implémentation de cette tranche.
- `docs/superpowers/specs/2026-09-16-3d-posture-skeleton-rig-design.md` — la spec de la tranche 2 de
  l'avatar 3D de posture (squelette articulé + preuve de skinning).
- `docs/superpowers/plans/2026-09-16-3d-posture-skeleton-rig-plan.md` — le plan d'implémentation de
  cette tranche.
- `docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-design.md` — la spec de la tranche 3 de
  l'avatar 3D de posture (vrais maillages musculaires Z-Anatomy). **Livrée et vérifiée
  manuellement dans un vrai navigateur.** 54 muscles Z-Anatomy (BodyParts3D, licence CC BY-SA 4.0)
  riggés sur le squelette articulé de la Tranche 2 via un pipeline Blender → glTF
  (`tools/blender/export_muscle_rig.py`), exportés dans `web/public/muscle-rig.glb` (~15,7 Mo,
  committé) et chargés par `PostureAvatar3D.tsx` via `useGLTF`. Poids de skinning à deux vitesses
  (voir les blocs « Correction » du 2026-09-20 et 2026-09-21 dans la spec) : Automatic Weights
  (heat-diffusion Blender) n'est utilisé QUE pour les 28 muscles upper_arm/forearm, seul cas
  réellement bi-articulaire (coude) de ce squelette à 9 os ; les 26 muscles tronc/cou/cuisse, qui ne
  traversent aucune seconde articulation représentée, sont rattachés en poids rigide déterministe
  (100 % sur leur unique os connu, jamais via heat-diffusion). Deux défauts de rendu invisibles en
  simple revue de code (matériaux systématiquement blancs quel que soit l'`action_level`) ont été
  détectés et corrigés pendant cette vérification — voir le bloc « Correction (2026-09-20,
  vérification manuelle Task 7) » dans la spec pour le détail. Crédit CC BY-SA affiché sous l'avatar
  dans l'interface et dans `NOTICE.md`.
- `docs/superpowers/plans/2026-09-20-3d-posture-muscle-mesh-implementation.md` — le plan
  d'implémentation de cette tranche.
- `docs/superpowers/specs/2026-09-21-3d-posture-muscle-segment-coloring-design.md` — la spec de la
  tranche 4 de l'avatar 3D de posture (coloration par segment anatomique).
- `docs/superpowers/plans/2026-09-21-3d-posture-muscle-segment-coloring-plan.md` — le plan
  d'implémentation de cette tranche.
- `docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md` — la spec du stockage des
  analyses RULA en DuckDB (persistance dans le temps, migration hors du système de fichiers pour
  le flux API web).
- `docs/superpowers/plans/2026-09-22-duckdb-analysis-storage-plan.md` — le plan d'implémentation
  de cette tranche.
- `docs/superpowers/specs/2026-09-22-capsule-zone-recommendation-design.md` — la spec de la
  recommandation de capsules d'étirement par zone anatomique dégradée.
- `docs/superpowers/plans/2026-09-22-capsule-zone-recommendation-plan.md` — le plan
  d'implémentation de cette tranche.
- `docs/superpowers/specs/2026-09-22-analysis-history-dashboard-design.md` — la spec du dashboard
  d'historique des analyses.
- `docs/superpowers/plans/2026-09-22-analysis-history-dashboard-plan.md` — le plan
  d'implémentation de ce sprint.
- `.superpowers/sdd/progress.md` — le journal complet des cycles (10 tâches + 4 revues pour le PoC ; 3 tâches + revue finale multi-passes pour la tranche capture web ; 5 tâches + revue finale pour l'upload par chunks ; 7 tâches pour la tranche 1 de l'avatar 3D), avec les décisions prises à chaque point d'arbitrage.
- Le code lui-même : `src/tms_vision/` (backend Python, 10 modules dont `pipeline.py`/`api.py`/`pose3d_export.py`, 136 tests dans `tests/`) et `web/` (frontend Next.js, avec `PostureAvatar3D.tsx` pour le rendu 3D).

### ✅ Phase 1 : Prototypage & Validation PoC — TERMINÉE

Pipeline complet et testé : capture (webcam ou fichier vidéo) → MediaPipe Pose → calcul d'angles
articulaires → score RULA officiel (Tables A/B/C, méthode McAtamney & Corlett 1993) → vidéo
annotée + export CSV/JSON. Voir section 9 ci-dessous pour l'utiliser.

**Ce qui a été validé** : les tables RULA (272 valeurs vérifiées chiffre par chiffre contre le
worksheet Cornell), la chaîne angles→score sur posture neutre et non-neutre (tests d'intégration
dédiés), la robustesse aux vues de profil (garde-fous géométriques contre le bruit de mesure sur
paires de landmarks quasi confondues), et la gestion d'erreurs (fichier manquant, webcam
indisponible, interruption Ctrl+C).

**Ce qui reste à valider avant tout usage réel** — c'est le point de reprise naturel si tu veux
juste "finir" la Phase 1 avant de passer à la suite :
1. ✅ **Vérification sur une vraie personne — FAITE (2026-09-16).** Analyse CLI (`--source`) d'une
   vidéo réelle (`moi coupe.mp4`, filmée de profil) : 746/798 frames avec pose détectée par
   MediaPipe (contre 0/40 sur la vidéo synthétique du test précédent). Score RULA max 7, moyenne
   4.6. Vérification visuelle par l'utilisateur du projet : le squelette se superpose correctement
   à la posture filmée.
2. **Calibrage des seuils géométriques sur données réelles.** Les seuils actuels (angle de
   flexion, ratio de séparation latérale pour les indicateurs de torsion/inclinaison, etc.) sont
   dérivés de la méthode RULA officielle et de raisonnements géométriques, mais n'ont pas été
   ajustés sur de vraies séquences MediaPipe (bruit de détection réel, occlusions partielles).
3. **Jambes fixées à "soutenues" (score 1).** Limite assumée du PoC — pas de détection fiable du
   support des jambes en monoculaire. À réévaluer si la Phase 2 ajoute une caméra ou un capteur
   complémentaire.

### Phase 2 : Création des Contenus & Interface (Semaines 4 - 6)

#### ✅ Tranche 1 : Capture web + API FastAPI — TERMINÉE

- **`tms_vision` extrait en librairie réutilisable** : `src/tms_vision/pipeline.py` expose
  `analyze_video()` (capture → pose → angles → score RULA → overlay → export) comme fonction
  appelable, sans dupliquer la logique ; `cli.py` n'est plus qu'un fin wrapper autour d'elle.
- **API FastAPI** (`src/tms_vision/api.py`) : `POST /analyses` reçoit un clip vidéo uploadé +
  paramètres (côté, charge, torsion poignet), lance `analyze_video()` de façon synchrone (pas de
  base de données ni de queue dans cette tranche — résultats sur le système de fichiers, comme en
  Phase 1), renvoie le résumé JSON + les liens vers la vidéo annotée et le CSV, servis dynamiquement
  via `GET /outputs/{filename}`.
- **Interface web** (`web/`, Next.js/TypeScript) : une page enregistre un clip caméra dans le
  navigateur (`getUserMedia`/`MediaRecorder`, plafonné à 640×480/30s pour rester compatible avec le
  pipeline en mémoire), l'envoie à l'API, affiche la vidéo annotée et le score. Voir section 10 pour
  l'utiliser.
- Vidéo annotée encodée en H.264 (`avc1`) — lisible directement dans un `<video>` de navigateur (le
  `mp4v` du PoC ne l'était pas ; corrigé et verrouillé par un test de non-régression pendant la
  revue finale de cette tranche).
- **Ce qui n'est pas dans cette tranche** (voir specs/plan pour le détail) : capture LiDAR/profondeur
  (caméra 2D uniquement), base de données, authentification, déploiement, floutage RGPD des visages
  (reste bloquant avant tout test avec de vrais salariés, voir section 7), calibrage des seuils sur
  données réelles (point 2 ci-dessus, toujours en attente).

#### ✅ Tranche 2 : Upload de fichier vidéo par chunks — TERMINÉE

- **3 nouveaux endpoints** (`src/tms_vision/api.py`) : `POST /uploads` (démarre une session
  d'envoi), `PUT /uploads/{id}/chunks/{index}` (reçoit un morceau) et `POST
  /uploads/{id}/complete` (réassemble les morceaux et lance `analyze_video()`, exactement comme
  `POST /analyses`). L'état de la session vit sur le système de fichiers (pas de dict en mémoire),
  pour survivre à un redémarrage d'uvicorn `--reload` en cours d'upload.
- **Interface web** : bouton « Importer une vidéo » en alternative à la caméra (voir section 10),
  qui envoie le fichier choisi en morceaux de 5 Mo, séquentiellement, avec re-tentative
  automatique par morceau en cas d'échec réseau.
- **Garde-fou mémoire ajouté pendant la revue finale de cette tranche** : `analyze_video()` garde
  toutes les frames décodées en mémoire, ce qui n'est pas un problème pour un clip caméra plafonné
  à 640×480/30s (tranche 1), mais l'aurait été pour une vidéo importée sans cette limite (ex. un
  export de téléphone en 1080p ou 4K, potentiellement plusieurs Go une fois décodée). Une
  estimation rapide (frames × largeur × hauteur) faite avant l'analyse rejette maintenant avec un
  422 explicite toute vidéo dont l'empreinte mémoire estimée dépasse ~2 Gio, sur les deux
  endpoints d'analyse (`/analyses` et `/uploads/{id}/complete`), plutôt que de laisser le serveur
  tenter l'analyse et risquer un OOM.
- **Ce qui n'est pas dans cette tranche** (voir specs/plan pour le détail) : suppression manuelle
  d'une session d'upload en cours (`DELETE /uploads/{id}`), vérification d'intégrité par taille
  totale envoyée par le client — pistes notées pour une itération future, pas nécessaires pour
  cette tranche.

#### ✅ Avatar 3D de posture, Tranche 1 (mannequin piloté par la pose) — TERMINÉE

- **Contexte** : en regardant le rendu 2D existant (traits fins + badge de score), l'utilisateur du
  projet a souhaité un rendu plus incarné, en référence à des outils comme Muscle & Motion et
  Z-Anatomy. Ces deux références s'appuient sur des modèles 3D construits à la main, non pilotés
  par une vraie vidéo — la demande a donc été découpée en tranches séquentielles (voir spec) : cette
  tranche 1 livre un mannequin 3D simple (capsules, pas encore de vrais muscles), les tranches
  futures ajouteront de vrais maillages musculaires (Z-Anatomy) puis leur activation par segment.
- **Backend** (`src/tms_vision/pose_estimation.py`, `pose3d_export.py` nouveau, `pipeline.py`,
  `api.py`) : `PoseEstimator` expose désormais aussi `world_landmarks` (estimation 3D à l'échelle
  métrique déjà fournie par MediaPipe, sans coût de calcul supplémentaire). `analyze_video()` lisse
  cette trajectoire sur toute la séquence (moyenne glissante centrée) et l'exporte dans un nouveau
  fichier `{run_id}_pose3d.json`, aux côtés des exports existants, exposé via `pose3d_url` dans la
  réponse de `/analyses` et `/uploads/{id}/complete`.
- **Interface web** (`web/app/PostureAvatar3D.tsx`, nouveau) : un mannequin 3D (react-three-fiber —
  10 capsules reprenant exactement les segments du squelette 2D, plus une tête) s'affiche à côté de
  la vidéo annotée, animé en synchro avec `video.currentTime` (marche pendant la lecture, en pause,
  et en déplaçant le curseur). Couleur unique par frame reflétant le niveau d'action RULA global
  (la coloration par segment/muscle est prévue pour une tranche future). Caméra orientable à la
  souris (OrbitControls) pour observer la posture sous un angle que la vidéo d'origine ne montrait
  pas. Pose figée sur les frames sans détection plutôt que de disparaître.
- **Vérifié manuellement (2026-09-16)** sur la vraie vidéo `moi coupe.mp4` (voir aussi la
  vérification de la Phase 1 ci-dessus, même vidéo) via un scénario Playwright bout en bout : le
  mannequin s'affiche dans une orientation correcte (ni à l'envers ni en miroir — aucun ajustement
  d'axe n'a été nécessaire), sa couleur suit fidèlement le score RULA affiché sur la vidéo (jaune →
  orange observé en déplaçant le curseur de lecture), sa posture change en synchro avec la vidéo y
  compris hors lecture continue (scrubbing), le zoom et la rotation de la caméra répondent
  correctement à la souris, et le message « Aucune posture détectée sur cette vidéo. » s'affiche
  sans erreur console sur un clip sans personne (`samples/synthetic_smoke_test.mp4`).
- **Ce qui n'est pas dans cette tranche** : vrais maillages musculaires, coloration par segment
  anatomique, mode miroir en direct (caméra → avatar en temps réel) — voir spec pour le détail.

#### ✅ Avatar 3D de posture, Tranche 2 (squelette articulé + preuve de skinning) — TERMINÉE

- **Contexte** : la Tranche 1 positionnait chaque capsule indépendamment (pas de hiérarchie), ce qui
  ne permet aucun skinning. Un vrai skinning de muscles (tranche future) exige un squelette
  articulé — c'est l'unique objet de cette tranche, sans changement visuel majeur attendu (silhouette
  générale similaire à la Tranche 1).
- **`web/app/pose3dSkeleton.ts`** (nouveau, module pur) : construit une hiérarchie de 8 os + racine
  (`THREE.Bone`/`THREE.Skeleton`) à partir des mêmes landmarks 3D que la Tranche 1, et calcule à
  chaque frame la rotation locale de chaque os par rapport à son parent. Roll/torsion de chaque os
  non calculé (limite connue des données MediaPipe, qui ne donnent que des positions).
- **`web/app/testSkinnedGeometry.ts`** (nouveau, module pur) : construit un maillage de test non
  anatomique (cylindres + une sphère pour la tête, poids de peau 100% par os) pour valider le
  mécanisme de skinning avant d'intégrer les vrais muscles.
- **`web/app/PostureAvatar3D.tsx`** : rend désormais un unique `THREE.SkinnedMesh` lié au squelette,
  à la place des 10 capsules indépendantes de la Tranche 1.
- **Première suite de tests automatisée dans `web/`** (Vitest, 11 tests) : hiérarchie du squelette,
  calcul des rotations sur une pose de référence, comportement sur landmarks manquants/os dégénéré
  (y compris le masquage par échelle d'un os jamais détecté, cf. correctif ci-dessous),
  attributs du maillage de test, plus un test d'intégration bout-en-bout
  (`web/app/skinning-integration.test.ts`) qui vérifie que les vertices posés du maillage retombent
  près des segments de landmarks attendus — celui-là même qui aurait détecté le bug de géométrie
  corrigé dans cette même série de correctifs.
- **Vérification manuelle du 2026-09-16 : invalidée.** Elle annonçait un maillage sans distorsion
  aux jointures, alors que les captures d'écran prises pendant cette session
  (`.playwright-mcp/orbit-zoomout2.png`, `orbit-angle-*.png`) montrent des cylindres disjoints
  projetés hors champ. Deux bugs de géométrie étaient en cause (repère local au lieu du repère monde
  de bind pose pour les vertices ; décalage parent-enfant constant au lieu de la longueur du parent),
  corrigés depuis, avec un test d'intégration bout-en-bout qui échoue sur l'ancien code
  (`web/app/skinning-integration.test.ts`).
- **Re-vérifié manuellement (2026-09-17)** sur `moi coupe.mp4`, après correction : le maillage forme
  bien **un corps unique et connexe** (tronc, tête, bras, cuisses attachés aux articulations), aux
  proportions humaines plausibles, il suit la posture en synchro avec la vidéo, reste connexe quand
  on se déplace dans la timeline et sous tous les angles de caméra testés ; aucune erreur en console.
  Contrôle numérique complémentaire sur la frame t=12 s : tronc, cou/tête, bras droit et cuisse
  droite tombent à quelques centimètres des landmarks correspondants.
  **Limite identifiée puis corrigée (2026-09-17)** : sur cette vidéo filmée de profil, MediaPipe ne
  fournit jamais `LEFT_ELBOW` ni `LEFT_KNEE` (visibilité < 0,5, filtrées par
  `pose_estimation.py`) — 0 frame sur 798. Le filtre de visibilité MediaPipe date d'avant cette
  tranche, mais pas le repli qui l'exploitait ici (« landmark manquant → on garde la rotation
  courante », `web/app/pose3dSkeleton.ts`, introduit dans cette tranche, commit `9b7c83d`) : faute de
  distinguer « jamais détecté » de « juste absent cette frame », ce repli laissait le bras gauche et
  la cuisse gauche figés dans leur pose de repos, pointant vers le haut — deux cylindres dépassant
  au-dessus de la tête. C'était une régression **par rapport à la Tranche 1**, qui traitait déjà ce
  même cas de figure en masquant la capsule occultée (`mesh.visible = false`, commentaire citant
  explicitement la « vue de profil » comme cause). **Corrigé** : `applyFrameToSkeleton` distingue
  désormais un os dont le landmark n'a jamais été vu (ni cette frame, ni en cache) — auquel cas son
  échelle est ramenée à quasi zéro (`HIDDEN_SCALE`), ce qui masque visuellement le segment skinné
  sans nécessiter de visibilité par mesh (impossible avec le maillage skinné unique de cette
  tranche) — du cas d'un os simplement dégénéré cette frame (landmarks confondus), qui continue de
  garder sa dernière rotation valide sans être masqué. Même principe que le masquage de capsule de
  la Tranche 1, adapté au maillage skinné unique. Revérifié manuellement sur `moi coupe.mp4`,
  captures d'écran à l'appui (`.playwright-mcp/occlusion-fix-*.png`) : le bras gauche et la
  cuisse gauche sont désormais invisibles au lieu de traverser la tête, sur toute la timeline
  scrutée et sous tous les angles de caméra testés — observation directe, solide. Les segments
  avec données valides (tronc, cou, bras droit) ont eux aussi été vus animer correctement en
  direct ; la cuisse droite n'a en revanche pas pu être isolée visuellement dans cette pose
  accroupie précise (hanche-genou quasi vertical, en partie masqué par le tronc sous cet angle) —
  sa continuité repose sur la logique du code (seuls les os sans landmark passent par
  `HIDDEN_SCALE` ; `RIGHT_HIP`/`RIGHT_KNEE` sont présents sur toutes les frames de ce clip, donc
  `R_thigh` ne prend jamais cette branche, et sa rotation se propage indépendamment de celle de
  ses os frères) et sur la suite de tests unitaires, pas sur une confirmation visuelle isolée.
- Pas de mannequin fantôme avant la première détection (confirmé par lecture de code —
  `visible={false}` en prop JSX synchrone — la vidéo de test n'ayant aucun segment sans détection
  pour l'observer en direct) ; fallback "aucune posture détectée" toujours correct sur
  `synthetic_smoke_test.mp4`.
- **Ce qui n'est pas dans cette tranche** : vrais maillages musculaires Z-Anatomy, recherche sur leur
  riggabilité réelle — livré depuis dans la Tranche 3 (voir section suivante).

#### ✅ Avatar 3D de posture, Tranche 3 (vrais maillages musculaires Z-Anatomy) — TERMINÉE

- **Contexte** : la Tranche 2 skinnait un maillage de test non anatomique (cylindres) sur le
  squelette articulé, pour prouver que le mécanisme de skinning fonctionnait. Cette tranche
  remplace ce maillage de test par de vrais muscles.
- **Pipeline Blender → glTF (hors runtime)** : `tools/blender/rig_spec.py` (table de hiérarchie
  d'os et de sélection des muscles) et `tools/blender/export_muscle_rig.py` (script exécuté
  manuellement via `blender --background --python` contre le fichier source Z-Anatomy
  `Startup.blend`, non commité — voir spec pour le téléchargement) construisent une armature
  identique à celle de `pose3dSkeleton.ts`, y rattachent les muscles sélectionnés, puis exportent le
  tout en un seul fichier glTF binaire. **Deux chemins de poids distincts, pas un seul** (voir les
  blocs « Correction » du 2026-09-20 et 2026-09-21 dans la spec) : **Automatic Weights** (diffusion
  de chaleur native de Blender) n'est utilisé QUE pour les 28 muscles upper_arm/forearm, le seul cas
  réellement bi-articulaire (coude) de ce squelette à 9 os ; les 26 muscles tronc/cou/cuisse, qui ne
  traversent aucune seconde articulation représentée dans ce squelette, sont rattachés en **poids
  rigide déterministe** (100 % sur leur unique os connu par table, jamais via heat-diffusion).
  **54 muscles** (pas 55 — un objet source cassé exclu, voir la spec) sont ainsi livrés dans
  `web/public/muscle-rig.glb` (~15,7 Mo, committé), déjà validé indépendamment par parsing direct
  du JSON glTF (squelette 9 os, 54 muscles, présence d'un skin par maillage).
  **Précision (2026-09-20, après la revue finale de branche complète décrite dans la spec)** :
  cette première passe ne décodait que la structure JSON du glTF (présence des skins), pas les
  poids binaires eux-mêmes (`JOINTS_0`/`WEIGHTS_0`) — elle ne pouvait donc pas détecter que les 20
  muscles de membre gauche étaient en réalité skinnés sur les os droits. C'est un décodage binaire
  direct ultérieur, indépendant, qui a trouvé ce bug et permis de le corriger (trois passes de
  correctifs côté pipeline Blender, détaillées dans la spec).
  **Précision (2026-09-21, généralisation du poids rigide déterministe à la cuisse)** : la même
  revue finale de branche a ensuite mesuré une bavure de poids secondaire sur 10 des 12 muscles de
  cuisse (2 étaient déjà exacts : Short head of biceps femoris côtés gauche et droit), incluant
  contamination croisée vers l'os de la cuisse opposée et d'autres os, pas seulement vers
  `L_forearm`/`R_forearm` (jusqu'à 36 % sur ~5 % des sommets de `Vastus lateralis muscle.l`) —
  même cause racine que le tronc/cou (pas de bi-articulation à préserver pour `L_thigh`/`R_thigh`
  dans ce squelette à 9 os), en plus léger (dominante déjà correcte partout, contrairement au
  tronc/cou où elle était parfois fausse). Le même traitement poids-rigide a été étendu à la cuisse
  (décision produit explicite) ; `muscle-rig.glb` est désormais revérifié sommet par sommet :
  binding correct sur les 28 muscles upper_arm/forearm et pondération rigide exacte (100,000 %,
  0 sommet en écart) sur les 26 muscles tronc/cou/cuisse.
- **`web/app/PostureAvatar3D.tsx`** charge désormais ce fichier via `useGLTF` (`@react-three/drei`)
  à la place du maillage de test de la Tranche 2 ; `pose3dSkeleton.ts` et `applyFrameToSkeleton`
  n'ont pas changé (bénéfice architectural de la Tranche 2 : le calcul de pose est découplé du
  maillage qui l'affiche).
- **Attribution CC BY-SA** : les muscles sont dérivés de BodyParts3D via Z-Anatomy (licence
  CC BY-SA 4.0). Crédit affiché sous le canvas 3D dans l'interface et détaillé dans `NOTICE.md`.
- **Vérifié manuellement (2026-09-20)** — première vérification visuelle réelle de tout le travail
  « muscles » (Tâches 1 à 6 de cette tranche n'avaient été validées que par revue de code statique
  et parsing du glb, jamais en faisant réellement tourner l'avatar dans un navigateur). Sur
  `moi coupe.mp4`, via le flux d'import de fichier : les muscles suivent la posture en synchro avec
  la vidéo à plusieurs points de la timeline, sans distorsion aberrante aux jointures ; le bras
  gauche et la cuisse gauche (jamais détectés sur cette vidéo de profil, `LEFT_ELBOW`/`LEFT_KNEE`)
  restent invisibles tout du long au lieu de rester figés — le correctif `HIDDEN_SCALE` de la
  Tranche 2 fonctionne toujours avec les vrais muscles ; aucune erreur ni avertissement de projet en
  console (seuls des avertissements bénins hors-projet : dépréciation interne `THREE.Clock`,
  polices préchargées non utilisées). Comme en Tranche 2, l'absence de mannequin fantôme avant la
  première détection n'a pu être confirmée que par lecture de code (`visible={false}` en prop JSX
  synchrone) : cette vidéo de test détecte une pose dès la frame 0, donc ce cas n'est jamais observé
  en direct.
  **Précision (2026-09-20, après la découverte ultérieure du bug de binding gauche/droite —
  voir plus haut)** : cette observation (bras/cuisse gauches invisibles) était correcte et
  démontrait bien que le mécanisme de masquage `HIDDEN_SCALE` fonctionnait avec les vrais muscles —
  mais elle ne démontrait **pas**, comme la formulation d'origine pouvait le laisser penser, que le
  binding squelettique du côté gauche lui-même était correct. Le `.glb` utilisé pour cette
  vérification avait en réalité ses 20 muscles de membre gauche skinnés sur les os droits (bug
  trouvé ensuite par décodage binaire direct, voir la spec) ; comme ces muscles étaient
  systématiquement ramenés à une échelle quasi nulle avant d'être vus, le bug restait invisible à
  l'écran quel que soit l'état du binding sous-jacent. Revérifié en direct après le correctif de
  binding et les deux passes de correction de la pondération tronc/cou (voir plus haut) : le bras
  droit suit correctement une pose très différente du repos sans que le bras gauche masqué ne
  reflète cette rotation (bones gauches figés à l'identité, échelle nulle) — mais cette observation
  porte sur `THREE.Bone` (quaternion/échelle), la couche de calcul de pose pilotée par
  `applyFrameToSkeleton` (`pose3dSkeleton.ts`), entièrement indépendante de la couche de binding
  maillage↔os (`skinIndex`/`WEIGHTS_0`) où vivait le bug. Un binding mesh encore inversé aurait
  produit exactement la même observation à l'écran, puisque ces quaternions ne renseignent en rien
  quel sommet est skinné à quel os : elle confirme donc seulement que la couche de calcul de pose
  suit le côté gauche/droite indépendamment, pas que le binding lui-même est correct. La correction
  du binding gauche/droite au niveau maillage est établie par le décodage binaire direct de
  `JOINTS_0`/`WEIGHTS_0` sur le `.glb` exporté, refait indépendamment à plusieurs reprises tout au
  long de la chaîne de correctifs (voir plus haut et la spec).
- **Deux défauts de rendu trouvés et corrigés pendant cette vérification**, invisibles en simple
  revue de code : la couleur d'`action_level` ne s'affichait en réalité jamais (muscles toujours
  gris/blancs). Cause 1 : les matériaux exportés par Blender portent un `emissiveFactor` blanc à
  pleine intensité qui sature le rendu indépendamment de `material.color` — neutralisé sur les
  clones. Cause 2 : l'affectation `mesh.material = clone` se faisait comme effet de bord dans un
  `useMemo` (impur), ce que React 18 Strict Mode (actif par défaut en `next dev`) rejoue deux fois
  et désynchronisait le mesh réellement affiché de la boucle de coloration — déplacé dans un
  `useEffect` idempotent, scène GLTF clonée par montage (`SkeletonUtils.clone`) plutôt que mutée en
  partagé. Détail complet dans le bloc « Correction (2026-09-20, vérification manuelle Task 7) » de
  la spec. Revérifié après correctif : la couleur change bien (jaune → orange → rouge observés sur
  ce clip) uniformément sur l'ensemble des muscles au fil de la lecture.
- **Ce qui n'est pas dans cette tranche** : musculature complète (~600 muscles), coloration par
  muscle individuel selon les sous-scores RULA (coloration par segment anatomique livrée en
  Tranche 4, voir section suivante — la coloration par muscle individuel, plus fine, reste non
  planifiée), correction du roll/torsion des os, correction du risque de cascade d'échelle sur une
  hanche jamais détectée (voir spec) — `testSkinnedGeometry.ts` conservé tel quel (décision de
  suppression explicitement hors périmètre).

#### ✅ Avatar 3D de posture, Tranche 4 (coloration par segment anatomique) — TERMINÉE

- **Contexte** : la Tranche 3 appliquait une teinte uniforme (`action_level` global) à tous les
  muscles importés. Cette tranche colore chaque segment indépendamment à partir des sous-scores
  RULA déjà calculés par `compute_rula_score()` mais jusqu'ici jetés avant d'atteindre le frontend.
- **Backend** : `Pose3DFrameRecord` (`pose3d_export.py`) gagne un champ additif
  `segment_action_levels` (cou/tronc/bras/avant-bras, réutilisant `action_level()` telle quelle sur
  chaque sous-score) ; `side` (le côté analysé) est ajouté à la réponse JSON de `POST /analyses`,
  pas à `pose3d.json`.
- **`web/app/muscleSegments.ts`** (nouveau, module pur) : résout le segment RULA de chaque muscle
  importé par son os dominant (somme des poids de peau `skinIndex`/`skinWeight`), via une table de 9
  entrées (une par os) plutôt qu'une duplication des ~30 noms de muscles Z-Anatomy.
- **`PostureAvatar3D.tsx`** : chaque muscle est coloré par son propre segment (cou, tronc, bras,
  avant-bras) ; le bras/avant-bras du côté NON analysé reste en gris fixe en permanence (aucune
  donnée mesurée pour ce côté) ; **les cuisses aussi restent en gris fixe en permanence** (`legs`
  est une constante jamais mesurée depuis la vidéo) — comportement corrigé après la livraison
  initiale de cette tranche (elles suivaient d'abord la teinte `action_level` globale, qui pouvait
  afficher rouge alors qu'aucun des 4 vrais segments ne le peut structurellement ; voir le bloc
  « Correction (2026-09-21, revue finale de branche complète) » de la spec pour le détail).
- **Vérifié manuellement (2026-09-21)**, avec Playwright piloté dans un vrai navigateur, deux
  serveurs réels (`uvicorn` + `next dev`) : côté **droit** sur `moi coupe.mp4` — vérification
  confirmée par lecture directe du graphe de scène Three.js (hook `__THREE_DEVTOOLS__` officiel,
  sans modifier le code de l'application) plutôt que par simple capture d'écran, la caméra par défaut
  de l'avatar rendant les segments trop petits à l'œil pour une lecture couleur fiable : sur les 106
  `SkinnedMesh` du rig, exactement les 28 correspondant aux muscles bras/avant-bras du côté gauche
  (convention de nommage Z-Anatomy à suffixe `001`/`001_1`) restent figés en gris (`#9e9e9e`) à 4
  instants de la vidéo pris à intervalles réguliers, pendant que les 78 autres (cou, tronc, cuisses,
  bras/avant-bras droit) affichent des couleurs qui varient dans le temps (vert/jaune/orange
  observés) ; aucune erreur console sur toute la session (en particulier aucune levée par
  `resolveMeshBoneKey`/`resolveMeshRouting`).
  **Chiffres tels qu'observés à cette date** — le correctif du 2026-09-21 (cuisses en gris fixe, voir
  ci-dessus) a changé la répartition depuis : d'après le décompte par os de
  `muscleRigInvariants.test.ts` (`L_thigh`: 12, `R_thigh`: 12), la répartition réelle actuelle est
  52 `SkinnedMesh` en gris fixe (28 bras/avant-bras gauche + 24 cuisses des deux côtés) et 54 dont la
  couleur varie (cou, tronc, bras/avant-bras droit) — recalculée à partir du code et du test de
  garde-fou, pas revérifiée par une nouvelle session Playwright.
  **Précision (côté "gauche")** : `moi coupe.mp4` est une vidéo de profil qui ne montre que le côté
  droit de la personne — la Tranche 3 documentait déjà que `LEFT_ELBOW`/`LEFT_KNEE` n'y sont jamais
  détectés (voir bloc Tranche 3 ci-dessus). Avec `côté="gauche"`, `compute_joint_angles()`
  (`angles.py`, inchangé par cette tranche) exige les landmarks `LEFT_SHOULDER`/`LEFT_ELBOW`/
  `LEFT_WRIST`/`LEFT_EAR`/`LEFT_INDEX`, filtrés sous le seuil `min_visibility=0.5`
  (`pose_estimation.py`) sur la totalité des 798 frames de cette vidéo — confirmé en comparant les
  deux `pose3d.json` : `action_level`/`segment_action_levels` présents sur 746/798 frames côté
  droit, sur 0/798 côté gauche, alors que les landmarks généraux (squelette 3D) restent détectés sur
  795/798 frames dans les deux cas. Conséquence attendue, pas un bug de coloration : faute de
  sous-scores RULA, l'avatar entier (y compris cou/tronc/cuisses, qui ne dépendent pourtant d'aucun
  côté) reste en gris neutre du début à la fin — comportement de repli correct étant donné l'absence
  de données, identique à ce qu'aurait produit la teinte globale unique de la Tranche 3 dans les
  mêmes conditions. Le comportement miroir (bras/avant-bras droit gris, gauche coloré) n'a donc pas
  pu être confirmé visuellement sur cet unique enregistrement disponible ; il est garanti par
  construction du code — `sideOfBone()`/`resolveMeshRouting()` (`muscleSegments.ts`) sont purement
  géométriques (dominance de poids de peau) et ignorent totalement la valeur de `side`, qui n'entre
  en jeu qu'au moment de la comparaison `routing.side !== side` dans `PostureAvatar3D.tsx`,
  strictement symétrique entre "left" et "right" — et par les tests unitaires existants de
  `muscleSegments.test.ts`. Aucune erreur console sur cette session non plus.
  Fallback "aucune posture détectée" toujours correct sur `synthetic_smoke_test.mp4` (40 frames, 0
  détection, aucune erreur console).
- **Ce qui n'est pas dans cette tranche** : analyse simultanée des deux côtés, coloration des
  cuisses par un vrai signal mesuré, segments `wrist`/`wrist_twist` (pas d'os poignet dans le rig) —
  voir la spec `docs/superpowers/specs/2026-09-21-3d-posture-muscle-segment-coloring-design.md`.

#### ✅ Stockage des analyses en DuckDB — TERMINÉE

- **Contexte** : depuis la Tranche 1, chaque analyse écrivait 4 fichiers isolés dans `outputs/`
  (vidéo annotée, CSV, résumé JSON, landmarks 3D), sans aucun moyen de lister ou d'interroger les
  analyses passées. Cette tranche migre ce stockage vers DuckDB, avec un historique interrogeable
  — préalable nécessaire à la recommandation de capsules par zone (tranche suivante).
- **`src/tms_vision/storage.py`** (nouveau) : deux tables DuckDB (`data/tms_vision.duckdb`,
  non committé) — `analyses` (métadonnées, résumé agrégé, blobs vidéo/pose3D) et
  `analysis_frames` (une ligne par frame, scores RULA et zones d'action par segment
  interrogeables en SQL).
- **`src/tms_vision/pipeline.py`** : `analyze_video()` devient pur (retourne bytes/dicts en
  mémoire), n'écrit plus aucun fichier durable.
- **`src/tms_vision/api.py`** : `POST /analyses` et `POST /uploads/{id}/complete` acceptent
  désormais `worker_label`/`poste_label` (tags texte libres, pas d'authentification) et persistent
  en DuckDB. `GET /outputs/{filename}` est remplacé par `GET /analyses`, `GET /analyses/{id}`,
  `GET /analyses/{id}/video`, `GET /analyses/{id}/pose3d`, `GET /analyses/{id}/frames.csv`,
  `GET /analyses/{id}/recommendation` (tranche suivante, voir ci-dessous).
- **`src/tms_vision/cli.py`** (workflow Phase 1 local) : continue d'écrire vidéo/CSV/JSON dans
  `--output-dir` comme avant — seule la CLI écrit encore sur le système de fichiers, l'API web
  persiste exclusivement en DuckDB.
- **Ce qui n'est pas dans cette tranche** : UI d'historique/dashboard consommant `GET /analyses`,
  migration des runs déjà présents dans `outputs/`, authentification. Aucun mécanisme de
  suppression/purge des analyses : cette tranche rend possible, pour la première fois, le
  stockage durable d'un nom de salarié (`worker_label`, texte libre) associé à sa vidéo annotée
  — sans floutage des visages (toujours pas implémenté, voir section 7) ni endpoint de
  suppression ni politique de rétention. À traiter avant tout test avec de vrais salariés.
  (Le support des requêtes `Range` pour le streaming vidéo, lui, est couvert : voir
  `GET /analyses/{id}/video` plus haut.)

#### ✅ Recommandation de capsules par zone — TERMINÉE

- **Contexte** : le README (§6) décrivait depuis le début une médiathèque de capsules vidéo
  d'étirement déclenchée automatiquement après une analyse, sans que rien de tout cela n'existe
  dans le code. Ce sprint construit la première version : catalogue placeholder, calcul de la
  zone RULA la plus dégradée, endpoint et affichage frontend — en s'appuyant sur les
  `segment_action_level` par zone déjà persistés par le sprint DuckDB précédent.
- **`src/tms_vision/capsules.py`** (nouveau, module pur sans dépendance DuckDB) : un catalogue
  statique `CAPSULES` (contenu factice, une entrée par zone mesurée) et
  `compute_worst_zone(frames)`, qui calcule pour chaque zone le temps cumulé passé dans les
  niveaux d'action élevés (`investigation_et_changement_bientot`, `changement_immediat`) — même
  principe de calcul de durée que `ResultsExporter.summary()` (`export.py`), appliqué par zone
  plutôt qu'au global. Égalité stricte entre zones → ordre de priorité fixe (`trunk > neck >
  upper_arm > lower_arm`, les lombaires étant le risque TMS le plus sérieux). Aucune zone
  dégradée → pas de recommandation forcée (`None`).
- **4 zones seulement** : `neck`, `trunk`, `upper_arm`, `lower_arm` — les seules réellement
  mesurées par le pipeline. Les zones "poignets/mains" et "hanches" du README §6 en sont
  volontairement absentes : `wrist` n'a pas d'équivalent musculaire dans le rig 3D et `legs` est
  une constante jamais dérivée de la vidéo (`LEGS_SCORE`, limite déjà documentée à la Tranche 4 de
  l'avatar 3D ci-dessus) — les inclure aurait obligé à prévoir des zones qui ne pourraient jamais
  être recommandées.
- **`storage.get_frame_segments(analysis_id)`** (nouveau) lit `analysis_frames` (frame_index,
  timestamp, les 4 colonnes segment), triée par frame_index ; `None` sur id inconnu. Aucune
  logique de zone n'y vit — `storage.py` reste une couche de persistance pure.
- **`GET /analyses/{id}/recommendation`** (nouveau, `api.py`) : 404 sur id inconnu (même pattern
  que les autres routes `/analyses/{id}/...`), sinon `{"zone": ..., "capsule": {...} | null}`.
- **Frontend** (`web/app/page.tsx`) : un petit bloc "Recommandation" sous le résumé d'une analyse
  tout juste terminée — libellé français de la zone, titre et description de la capsule. Rien ne
  s'affiche si `zone` est `null`. L'état est gardé sous la forme `{ analysisId, data }` plutôt
  qu'un simple `Recommendation | null` : le rendu vérifie explicitement que `analysisId` correspond
  à l'analyse actuellement affichée avant de montrer quoi que ce soit, ce qui évite d'afficher la
  recommandation d'une analyse précédente sans avoir besoin de réinitialiser l'état de façon
  synchrone dans l'effet (motif retenu en revue finale de branche pour satisfaire la règle ESLint
  `react-hooks/set-state-in-effect`).
- **Limitation connue, documentée et acceptée pour ce sprint** : la zone `lower_arm` ne peut en
  pratique jamais être recommandée. Son sous-score RULA brut est plafonné à 3
  (`classify_lower_arm`, `rula/scoring.py`), alors que `ELEVATED_LEVELS` réutilise les bandes du
  niveau d'action global, qui ne s'activent qu'à partir de 5 — `lower_arm` ne peut donc jamais
  cumuler de temps "dégradé", et son entrée de catalogue (« Étirement de l'avant-bras et du
  coude ») ne pourra jamais être renvoyée par `compute_worst_zone`. Même racine que la limitation
  déjà documentée pour `changement_immediat` sur `neck`/`trunk`/`upper_arm` (plafond de sous-score
  6 contre seuil 7, voir la Tranche 4 de l'avatar 3D ci-dessus et le commit `989df73`) — décision
  prise en revue finale de branche de documenter plutôt que de redéfinir des seuils par segment ce
  sprint (voir le bloc « Correction (revue finale de branche) » de la spec).
- **Ce qui n'est pas dans ce sprint** : vraies vidéos de capsules (contenu placeholder
  uniquement), édition du catalogue (pas d'admin UI ni de CMS), UI d'historique montrant les
  recommandations passées, mode temps réel (vérification webcam de l'exécution de l'étirement),
  recommandation de plusieurs capsules par zone.

#### ✅ Dashboard d'historique des analyses — TERMINÉE

- **Contexte** : la tranche DuckDB avait exposé `GET /analyses` (filtres
  worker_label/poste_label/since/until) et `GET /analyses/{id}` sans jamais construire l'UI qui
  les consomme -- explicitement noté hors périmètre à l'époque, puis reconfirmé hors périmètre
  par le sprint capsules suivant. Ce sprint construit cette UI, sans aucun changement backend :
  les deux endpoints existants couvraient déjà tout le besoin.
- **`web/app/AnalysisResult.tsx`** (nouveau) : le bloc "Résultat" (vidéo annotée, avatar 3D,
  résumé RULA, lien CSV, recommandation de capsule), jusqu'ici câblé en dur dans `page.tsx` pour
  une analyse tout juste terminée, en est extrait en composant partagé -- réutilisé à la fois par
  la page d'accueil et par la nouvelle page de détail d'historique.
- **`web/app/historique/page.tsx`** (nouveau) : liste des analyses passées, triée par date
  décroissante (tri déjà fait côté backend), avec les 4 filtres déjà supportés par l'API
  (salarié, poste -- tous deux en correspondance exacte, pas de recherche par sous-chaîne --
  depuis/jusqu'à), un badge de score max coloré selon les mêmes seuils RULA que le reste de
  l'interface (`action_level()`), et un lien vers le détail de chaque analyse. Pas de
  pagination (dataset réduit à l'échelle d'un pilote mono-entreprise).
- **`web/app/historique/[id]/page.tsx`** (nouveau) : détail complet d'une analyse passée --
  exactement le même rendu que le résultat d'une analyse fraîche (`AnalysisResult`), les URLs
  vidéo/CSV/pose3D étant reconstruites à partir du seul `analysis_id` (même convention de chemin
  que `POST /analyses`). 404 propre sur un id inconnu.
- **Vérifié manuellement (2026-09-22)**, avec Playwright piloté dans un vrai navigateur, deux
  serveurs réels (`uvicorn` + `next dev`) : liste et filtres (y compris intersection de plusieurs
  filtres actifs), navigation liste → détail → retour, id inconnu → message d'erreur propre,
  aucune régression sur la page d'accueil (résultat d'une analyse fraîche identique à avant ce
  sprint). Les valeurs affichées par `/historique` ont été recoupées indépendamment contre une
  lecture directe de `storage.list_analyses()` sur la base réelle.
- **Ce qui n'est pas dans ce sprint** : pagination, tri/colonnes personnalisables, suppression
  d'une analyse depuis le dashboard (le gap RGPD rétention/suppression reste entier, voir §7),
  export groupé multi-analyses (Phase 3), champs salarié/poste sur le formulaire d'analyse de la
  page d'accueil (existent côté API depuis la tranche DuckDB, jamais exposés côté formulaire --
  limite pré-existante, pas introduite par ce sprint, qui explique pourquoi les analyses de
  vérification de ce sprint ont `worker_label`/`poste_label` à "—").

#### Reste à faire pour la suite de la Phase 2

- Module de floutage automatique des visages (OpenCV, en amont de l'analyse posturale) — non
  implémenté, c'est le principal manque de conformité RGPD à combler avant tout test avec de vrais
  salariés (voir section 7).
- Tournage de la bibliothèque de micro-pauses vidéo par l'ostéopathe (30-45 vidéos courtes) — la
  recommandation de capsules par zone (ci-dessus) est prête côté logique et interface, mais tout
  son contenu vidéo reste factice tant que ce tournage n'a pas eu lieu.

### Phase 3 : Tiers Test & Pilote Entreprise (Semaines 7 - 10)

- Déploiement d'un projet pilote dans une entreprise partenaire ou un atelier.
- Ajustement des seuils de scoring ergonomiques avec l'ostéopathe, sur la base des données
  collectées en conditions réelles (les colonnes `posture_score_a`/`posture_score_b` du CSV,
  ajoutées pendant la revue finale du PoC, permettent déjà ce diagnostic fin sans ré-implémenter
  quoi que ce soit).
- Génération des premiers rapports d'audit pour la direction HSE/RH, à partir du résumé JSON déjà
  produit par frame (score max, score moyen, temps passé par niveau de risque) agrégé sur
  plusieurs salariés/postes.

## 9. Lancer le PoC (Phase 1)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pytest                                    # suite de tests

PYTHONPATH=src venv/bin/python -m tms_vision.cli \
  --source chemin/vers/video.mp4 \
  --side right \
  --load-kg 2.5 \
  --wrist-twist normal \
  --output-dir outputs
```

`--source` accepte aussi `webcam` pour filmer en direct depuis une caméra branchée sur la
machine :

```bash
PYTHONPATH=src venv/bin/python -m tms_vision.cli --source webcam --side right --load-kg 0 --output-dir outputs
```

(interrompre avec Ctrl+C — la capture est actuellement lue en mémoire avant traitement, donc
mieux vaut limiter la prise à quelques dizaines de secondes ou enregistrer un fichier au
préalable si l'analyse doit couvrir un poste sur une durée plus longue).

**Conseil de prise de vue** : filmer la personne de profil pour des angles de flexion/extension
fiables (cou, tronc, bras).

Résultats dans `outputs/` : une vidéo annotée (squelette + badge de score RULA coloré), un CSV
détaillé par frame, et un résumé JSON (score max, score moyen, temps passé par niveau de risque).

**Note de vérification (Task 10)** : la suite de tests (64 tests) a été rejouée intégralement
avec succès. Le pipeline CLI complet a ensuite été exercé de bout en bout dans un environnement
sandboxé sans accès webcam physique, à l'aide d'une vidéo synthétique générée par OpenCV (un
cercle et un rectangle en mouvement sur fond uni, 40 frames à 10 fps) — cette vidéo ne contient
aucune silhouette humaine, donc MediaPipe n'y détecte aucune pose, ce qui est le comportement
attendu. Ce test a confirmé que les trois fichiers de sortie (vidéo annotée, CSV, JSON) sont
bien créés et correctement formés, avec une ligne par frame (`detected=False` sur les 40 lignes,
colonnes d'angles/scores vides) et un résumé JSON à `max_score: 0`, `average_score: 0`,
`time_by_action_level: {}` — conforme à la convention "aucune frame détectée" de la Task 8.
**Ce test ne remplace pas une vérification avec une vraie webcam ou une vidéo d'une personne
réelle** : avant de s'appuyer sur ce PoC pour une évaluation ergonomique réelle, l'utilisateur du
projet doit relancer la commande `--source webcam` (ou une vidéo filmant une personne) et
vérifier visuellement le squelette superposé et la cohérence des scores RULA obtenus.

## 10. Lancer la capture web (Phase 2)

Deux serveurs à démarrer en parallèle, dans deux terminaux séparés.

**Terminal 1 — API FastAPI :**

```bash
PYTHONPATH=src venv/bin/uvicorn tms_vision.api:app --reload --port 8000
```

**Terminal 2 — frontend Next.js** (première fois : `cd web && npm install`) :

```bash
cd web && npm run dev
```

Ouvrir `http://localhost:3000`, autoriser l'accès caméra, se filmer **de profil** (même conseil
qu'en section 9), enregistrer quelques secondes (30s max, plafond imposé côté navigateur), remplir
le formulaire (côté, charge, torsion poignet) et cliquer « Analyser ». Le résultat (vidéo annotée,
score RULA, lien CSV) s'affiche directement dans la page une fois l'analyse terminée.

`NEXT_PUBLIC_API_URL` (par défaut `http://localhost:8000`) permet de pointer le frontend vers une
API à une autre adresse si besoin — pas de fichier `.env` requis pour l'usage local par défaut.

### Importer une vidéo (au lieu de la caméra)

Bouton « Importer une vidéo » : sélectionner un fichier vidéo déjà enregistré (ex. un export de
téléphone) plutôt que de filmer en direct. Contrairement à la capture caméra, ce flux n'a **pas**
la limite 640×480/30s imposée côté navigateur — c'est justement pour ça qu'il existe. Le fichier
est envoyé à l'API en morceaux de 5 Mo, séquentiellement, avec re-tentative automatique par
morceau en cas d'échec réseau. « Changer de vidéo » permet de choisir un autre fichier sans
recharger la page.

Pour compenser l'absence du plafond côté navigateur, la même limite mémoire côté serveur que
celle décrite section 8 (tranche 2) s'applique : une vidéo dont la résolution et/ou la durée
dépassent l'estimation de ~2 Gio est rejetée avec un message d'erreur clair plutôt que d'être
acceptée et de risquer de saturer la mémoire du serveur.

### Consulter l'historique des analyses

Le lien « Historique » en haut de la page d'accueil ouvre `/historique` : liste de toutes les
analyses déjà enregistrées, filtrable par salarié, poste et période (depuis/jusqu'à). Cliquer sur
« Voir » ouvre le détail complet d'une analyse passée (`/historique/{id}`), avec le même rendu
(vidéo annotée, avatar 3D, résumé, recommandation) que juste après l'avoir produite.

### Tester depuis un iPhone (ou tout autre appareil hors du Mac)

Se contenter de rejoindre l'IP locale du Mac en WiFi ne suffit pas : `getUserMedia` (accès
caméra) exige un contexte sécurisé (`https://` ou `localhost` exactement), et une IP locale
(`192.168.x.x`) en `http://` ne l'est pas. La solution la plus simple est un tunnel HTTPS
(`cloudflared`, déjà installé, aucun compte requis) :

**Terminal 1 — tunnel vers l'API :**
```bash
cloudflared tunnel --url http://localhost:8000
```
Note l'URL affichée (ex. `https://xxxx-api.trycloudflare.com`) → **URL_API**

**Terminal 2 — tunnel vers le frontend :**
```bash
cloudflared tunnel --url http://localhost:3000
```
Note l'URL affichée → **URL_WEB**

**Terminal 3 — API, en autorisant l'origine du tunnel web :**
```bash
ALLOWED_ORIGINS=URL_WEB PYTHONPATH=src venv/bin/uvicorn tms_vision.api:app --port 8000
```

**Terminal 4 — frontend, en pointant vers le tunnel API :**
```bash
cd web && NEXT_PUBLIC_API_URL=URL_API npm run dev
```

Ouvrir **URL_WEB** depuis Safari sur l'iPhone (n'importe quel réseau, pas besoin d'être sur le
même WiFi que le Mac puisque le tunnel est public). Les URL `trycloudflare.com` sont éphémères et
changent à chaque lancement — relancer les 4 terminaux avec les nouvelles URL à chaque session de
test.
