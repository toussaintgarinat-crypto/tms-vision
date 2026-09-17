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
- `.superpowers/sdd/progress.md` — le journal complet des cycles (10 tâches + 4 revues pour le PoC ; 3 tâches + revue finale multi-passes pour la tranche capture web ; 5 tâches + revue finale pour l'upload par chunks ; 7 tâches pour la tranche 1 de l'avatar 3D), avec les décisions prises à chaque point d'arbitrage.
- Le code lui-même : `src/tms_vision/` (backend Python, 10 modules dont `pipeline.py`/`api.py`/`pose3d_export.py`, 96 tests dans `tests/`) et `web/` (frontend Next.js, avec `PostureAvatar3D.tsx` pour le rendu 3D).

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
- **Première suite de tests automatisée dans `web/`** (Vitest, 6 tests) : hiérarchie du squelette,
  calcul des rotations sur une pose de référence, comportement sur landmarks manquants/os dégénéré,
  attributs du maillage de test.
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
  **Limite restante, connue et non corrigée** : sur cette vidéo filmée de profil, MediaPipe ne
  fournit jamais `LEFT_ELBOW` ni `LEFT_KNEE` (visibilité < 0,5, filtrées par
  `pose_estimation.py`) — 0 frame sur 798. Le bras gauche et la cuisse gauche restent donc figés
  dans leur pose de repos, pointant vers le haut : deux cylindres dépassent au-dessus de la tête.
  Comportement préexistant du repli « landmark manquant → on garde la rotation courante », pas un
  effet de la correction de géométrie, mais visuellement non humain. À traiter dans une tranche
  ultérieure (masquer les os sans donnée, ou les dériver du côté visible).
- Pas de mannequin fantôme avant la première détection (confirmé par lecture de code —
  `visible={false}` en prop JSX synchrone — la vidéo de test n'ayant aucun segment sans détection
  pour l'observer en direct) ; fallback "aucune posture détectée" toujours correct sur
  `synthetic_smoke_test.mp4`.
- **Ce qui n'est pas dans cette tranche** : vrais maillages musculaires Z-Anatomy, recherche sur leur
  riggabilité réelle — Tranche 3 (voir spec
  `docs/superpowers/specs/2026-09-16-3d-posture-skeleton-rig-design.md`).

#### Reste à faire pour la suite de la Phase 2

- Base de données (SQLite pour commencer, migration PostgreSQL si besoin) pour stocker les analyses
  dans le temps, au lieu du système de fichiers actuel.
- Module de floutage automatique des visages (OpenCV, en amont de l'analyse posturale) — non
  implémenté, c'est le principal manque de conformité RGPD à combler avant tout test avec de vrais
  salariés (voir section 7).
- Tournage de la bibliothèque de micro-pauses vidéo par l'ostéopathe (30-45 vidéos courtes).
- Avatar 3D de posture, Tranche 3 (voir la section « Hors périmètre » de la spec
  `docs/superpowers/specs/2026-09-16-3d-posture-skeleton-rig-design.md` — la numérotation des
  tranches a été renumérotée à partir de cette tranche-là, le travail « muscles » y est décrit) :
  vrais maillages musculaires (Z-Anatomy, CC BY-SA) riggés sur le squelette articulé de la
  Tranche 2, puis coloration/activation des muscles par segment à partir des sous-scores RULA déjà
  calculés.
- Déclenchement intelligent : associer les scores RULA par zone anatomique (déjà disponibles dans
  l'export : `neck`, `trunk`, `upper_arm`, `lower_arm`, `wrist`) aux capsules d'étirement.

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
