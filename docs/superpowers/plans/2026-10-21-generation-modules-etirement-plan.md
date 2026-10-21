# Génération des modules d'étirement — Plan d'implémentation (Tranche 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produire, de bout en bout et sans IA, la vidéo d'un module d'étirement à partir d'un fichier
de définition d'exercice, en réutilisant l'avatar 3D musculaire existant. Les briques IA (voix,
reformulation, proposition d'exercice) sont des fournisseurs optionnels et interchangeables, jamais
câblés en dur.

**Architecture:** Les exercices sont des fichiers JSON versionnés (`exercises/`), validés et chargés
côté Python (`exercises.py`), qui alimente le catalogue de capsules. Le rendu est fait par le
navigateur : une page Next.js (`/render/[id]`) anime l'avatar à partir de poses clés, un script Node
(`web/scripts/render-exercise.mjs`) la pilote image par image avec Playwright et envoie les images à
`ffmpeg`. Un orchestrateur Python (`capsule_build.py`) valide, appelle l'éventuelle voix, lance le
rendu, mixe l'audio et écrit `data/capsules/{id}.mp4`. L'API sert ces fichiers.

**Tech Stack:** Python 3.11, Next.js/TypeScript + three.js (déjà en place), `playwright-core` (nouveau,
devDependency du frontend), `ffmpeg` (outil système), pytest, Vitest.

## Décisions techniques prises (et pourquoi)

- **Rendu dans le navigateur, pas dans Blender.** Il réutilise exactement le même avatar, les mêmes
  maillages et la même coloration par segment que l'interface. Vérifié dans ce conteneur : Chromium
  sans écran fournit WebGL2 (SwiftShader), trois captures successives d'une même scène ont le même
  hash, et `ffmpeg` dispose de `libx264` et `aac`. **Repli** si le Task 1 échoue : Blender en ligne de
  commande (le dépôt a déjà `tools/blender/`).
- **Poses en angles, pas en landmarks.** Un ostéopathe ne saisit pas 33 coordonnées MediaPipe. Une
  pose donne, par os, deux angles à partir de la posture neutre (voir « Format »). Le code les
  convertit en landmarks synthétiques puis appelle `applyFrameToSkeleton`, **le même chemin** que
  l'avatar piloté par la vidéo, donc avec les mêmes conventions.
- **La définition est transmise au navigateur par le script de rendu** (pas par l'API) : la page de
  rendu n'a besoin que du serveur Next.js.
- **Les vidéos générées ne sont pas commitées** : `data/capsules/` est déjà ignoré par `data/`.
- **Limites du squelette, à dire à l'ostéopathe :** 9 os (tronc, cou, deux bras, deux avant-bras,
  deux cuisses). Pas de poignet, de main, de rotation de la tête ni d'omoplate. Le cou n'a qu'une
  direction (pas de rotation sur lui-même). Les exercices écrits ici se limitent donc à ce que ce
  rig sait montrer.

## Format d'un exercice

Fichier `exercises/<id>.json` :

```json
{
  "id": "neck-lateral-stretch",
  "zone": "neck",
  "title": "Étirement latéral du cou",
  "description": "…",
  "status": "draft",
  "source": "human",
  "validated_by": null,
  "validated_on": null,
  "view": "front",
  "target_segments": ["neck"],
  "poses": {
    "neutral": {},
    "tilt_right": { "neck": { "lateral": 30 } }
  },
  "keyframes": [
    { "t": 0, "pose": "neutral" },
    { "t": 8, "pose": "tilt_right" },
    { "t": 28, "pose": "tilt_right" },
    { "t": 36, "pose": "neutral" }
  ],
  "instructions": [
    { "t": 0, "text": "…" },
    { "t": 8, "text": "…" }
  ],
  "duration_seconds": 45
}
```

- **Os** : `spine`, `neck`, `L_upper_arm`, `L_forearm`, `R_upper_arm`, `R_forearm`, `L_thigh`,
  `R_thigh`. Un os absent d'une pose reste à sa direction neutre.
- **Angles** (degrés, absolus par rapport à la verticale, deux plans) : `flexion` positif = l'extrémité
  de l'os va vers l'avant du corps ; `lateral` positif = vers la droite du sujet pour `spine` et `neck`,
  et **écartement du corps** (abduction) pour les os pairés (gauche et droite se lisent de la même
  façon, le code applique le miroir). Neutre = tronc et cou vers le haut, bras et cuisses vers le bas.
  **Ces signes sont à établir empiriquement au Task 3 (rendu d'une pose, vérification visuelle) et
  verrouillés par des tests ; ne pas les déduire des conventions MediaPipe.**
- `view` : `front` | `side` | `three_quarter`. `target_segments` : sous-ensemble de `neck`, `trunk`,
  `upper_arm`, `lower_arm`, mis en évidence en bleu ; le reste est gris neutre.
- `status` : `draft` | `validated`. `validated` exige `validated_by` et `validated_on`.
- `source` : `human` | `ai`. Un exercice `ai` n'existe que dans `exercises/drafts/` et n'entre
  **jamais** au catalogue tant qu'un humain ne l'a pas déplacé, relu et validé.
- Interpolation entre poses clés : linéaire dans l'espace des angles, adoucie (smoothstep).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md`
  (Partie C).
- Aucune IA, aucun appel réseau sortant dans le chemin par défaut. Un fournisseur n'est actif que s'il
  est configuré explicitement (variable d'environnement).
- Deux rendus du même fichier, sur la même machine et les mêmes versions, donnent les mêmes images
  (test de hash au Task 5). L'identité entre machines différentes n'est pas garantie et n'est pas
  promise.
- **Crédit obligatoire dans chaque vidéo** : « Modèle musculaire dérivé de Z-Anatomy (BodyParts3D),
  licence CC BY-SA 4.0 », comme dans l'interface et `NOTICE.md`.
- Le catalogue contient les exercices `validated` et les exercices `draft` de source `human`
  (affichés avec un badge « brouillon »). Jamais un exercice de source `ai`.
- Les exercices que je rédige dans cette tranche sont des **brouillons** (`status: "draft"`,
  `source: "human"`, `validated_by: null`) : ils ne sont pas un contenu clinique validé.
- `capsules.py` reste pur ; la présence d'un fichier vidéo est testée dans la couche API, pas dans le
  catalogue.
- Référence de non-régression : les 22 échecs de `pytest` présents avant tout changement dans ce
  conteneur (`mediapipe` sans `solutions`). Enregistrer la liste avant le Task 1 avec
  `python -m pytest -q 2>&1 | grep FAILED | sed 's/ - .*//' | sort > /tmp/baseline.txt` et vérifier
  qu'elle est identique après chaque tâche.
- Frontend : lire le guide pertinent dans `web/node_modules/next/dist/docs/` avant d'écrire du code
  Next.js (`web/AGENTS.md`) ; `npm test`, `npm run lint`, `npx tsc --noEmit` dans `web/`.

---

### Task 1: Spike — rendu sans écran de l'avatar réel

Porte de décision : tout le reste en dépend.

**Files:**
- Create (jetable, hors dépôt, dans le répertoire temporaire) : script de test Playwright.

- [ ] **Step 1:** Installer `playwright-core` dans `web/` (devDependency, version exacte) et vérifier que
  Chromium sans écran se lance (dans ce conteneur : `/opt/pw-browsers/chromium`, arguments
  `--no-sandbox --use-gl=swiftshader --enable-unsafe-swiftshader`).
- [ ] **Step 2:** Démarrer `npm run dev`, ouvrir une page temporaire qui monte `muscle-rig.glb` dans un
  `Canvas` react-three-fiber à pose neutre (reprendre le chargement et la préparation des matériaux de
  `PostureAvatar3D.tsx::Rig`), capturer trois fois la même image.
- [ ] **Step 3:** Vérifier : (a) l'image n'est pas vide ni blanche (muscles visibles, couleurs
  appliquées, pas de saturation blanche : voir le commentaire sur l'émissif dans `Rig`) ; (b) les trois
  hashes sont identiques ; (c) durée d'une capture, pour estimer le temps de rendu d'une vidéo.
- [ ] **Step 4:** Consigner le résultat (durée par image, hash identiques, capture d'écran) dans la spec,
  Partie C. Si (a) ou (b) échoue : **s'arrêter**, ne pas continuer sur cette architecture, et proposer le
  repli Blender à l'utilisateur.
- [ ] **Step 5:** Commit `docs: consigne la faisabilité du rendu sans écran`.

---

### Task 2: Définitions d'exercices et catalogue

**Files:**
- Create: `src/tms_vision/exercises.py`, `exercises/README.md`, `exercises/neck-lateral-stretch.json`,
  `exercises/trunk-lumbar-mobility.json`, `exercises/shoulder-cross-body-stretch.json`,
  `exercises/forearm-extension-stretch.json`, `exercises/drafts/.gitkeep`
- Modify: `src/tms_vision/capsules.py`, `src/tms_vision/api.py`
- Test: `tests/test_exercises.py`, `tests/test_capsules.py`, `tests/test_api.py`

**Interfaces:**
- Produces : `exercises.load_exercise(path) -> dict` et `exercises.validate_exercise(data) -> None` (lève
  `ValueError` avec un message en français listant le défaut) ; `exercises.load_catalog(directory=None) ->
  list[dict]` (fichiers `exercises/*.json`, triés par `id`, `drafts/` exclu, `source: ai` rejeté) ;
  `exercises.EXERCISES_DIR`.
- `capsules.Capsule` gagne `id: str = ""` et `status: str = "draft"` ; `capsules.CAPSULES` est construit
  depuis `load_catalog()` (plus de liste écrite à la main) ; `video_url` = `/capsules/{id}/video` ;
  `capsule_to_dict` expose `id`, `status`, `video_url`. Le titre et la description des quatre capsules
  actuelles sont conservés dans les quatre exercices initiaux.
- Endpoints : `GET /exercises` (liste, sans `poses` ni `keyframes`), `GET /exercises/{id}` (définition
  complète, 404 sinon).

Règles de validation : `id` en minuscules, chiffres et tirets, égal au nom du fichier ; `zone` parmi les
4 zones ; `status`, `source`, `view` dans leurs valeurs ; `validated` exige `validated_by` et
`validated_on` (date ISO) ; `target_segments` non vide, sous-ensemble des 4 segments ; os connus
seulement ; angles dans `[-180, 180]` ; chaque `keyframes[].pose` existe dans `poses` ; `t` croissants,
premier `t == 0`, dernier `t <= duration_seconds` ; `instructions[].t` croissants dans
`[0, duration_seconds]` ; `duration_seconds` dans `[10, 180]` ; `source: "ai"` interdit hors `drafts/`.

- [ ] **Step 1:** Écrire `tests/test_exercises.py` : un exercice valide ; un test par règle ci-dessus
  (chaque violation → `ValueError` avec le champ nommé) ; `load_catalog` trie par `id`, ignore
  `drafts/`, rejette un `source: "ai"` placé hors de `drafts/` ; les quatre fichiers livrés sont tous
  valides, couvrent les 4 zones, `status == "draft"`, `source == "human"`, `validated_by is None`.
- [ ] **Step 2:** Mettre à jour `tests/test_capsules.py` (le catalogue vient des fichiers, une capsule
  par zone au minimum, `kind == "stretch"`, `video_url` commence par `/capsules/`) sans retirer de
  test existant ; ajouter les tests API de `GET /exercises` et `GET /exercises/{id}`.
- [ ] **Step 3:** Vérifier l'échec, implémenter `exercises.py`, adapter `capsules.py` et `api.py`.
- [ ] **Step 4:** Rédiger les quatre exercices en respectant les limites du squelette (voir plus haut),
  avec des consignes en français, des durées de 30 à 60 s et des poses simples : cou en inclinaison
  latérale ; tronc en flexion avant lente (`view: "side"`) ; épaule en étirement du bras croisé devant
  la poitrine ; avant-bras en extension du coude bras tendu devant. Les marquer `draft`.
- [ ] **Step 5:** Documenter dans `exercises/README.md` le format, les conventions d'angles (à compléter
  au Task 3), le cycle brouillon → validation, et la règle `source: ai`.
- [ ] **Step 6:** `python -m pytest` : mêmes échecs que la référence. Commit
  `feat: catalogue d'exercices en fichiers de définition validés`.

---

### Task 3: Poses en angles et animation par poses clés (TypeScript)

**Files:**
- Create: `web/app/exercisePose.ts`, `web/app/exercisePose.test.ts`

**Interfaces:**
- Produces : `type Exercise` (forme du JSON ci-dessus), `type PoseAngles = Partial<Record<BoneKey,
  {flexion?: number; lateral?: number}>>`, `boneDirections(angles: PoseAngles): Record<BoneKey,
  THREE.Vector3>` (directions monde, repère Three.js y vers le haut), `samplePose(exercise, t):
  PoseAngles` (interpolation entre poses clés, adoucie, bornée à `[0, duration]`),
  `anglesToLandmarks(angles): Pose3DLandmarks` (landmarks synthétiques : positions = origine + direction
  × `BONE_LENGTH`, dans le repère MediaPipe attendu par `applyFrameToSkeleton`, y vers le bas),
  `activeInstruction(exercise, t): {text: string; index: number} | null`.

- [ ] **Step 1: Établir les conventions par l'expérience, pas par déduction.** Écrire un petit test
  d'intégration qui, pour `flexion = +60` sur `spine`, passe `anglesToLandmarks` puis
  `applyFrameToSkeleton` (voir `pose3dSkeleton.test.ts` pour le montage d'un squelette en Node) et
  mesure la direction monde de l'os. Déterminer, en rendant la pose (Task 4) et en la regardant, quel
  signe correspond à « vers l'avant » et à « vers la droite du sujet », puis figer ces choix dans les
  tests. Noter le résultat dans `exercises/README.md`.
- [ ] **Step 2:** Tests : neutre = tronc et cou vers le haut, bras et cuisses vers le bas ;
  `flexion` et `lateral` donnent les directions attendues, y compris le miroir gauche/droite pour
  `lateral` des os pairés ; angle 0 pour un os absent ; `samplePose` : valeur exacte aux poses clés,
  milieu adouci entre deux poses (pas linéaire pur), maintien entre deux poses clés identiques, borné
  avant 0 et après la fin ; `activeInstruction` : aucune avant la première, la dernière après elle ;
  **propriété de bout en bout** : pour plusieurs poses, la direction monde de chaque os après
  `applyFrameToSkeleton` égale `boneDirections` à 1e-6 près.
- [ ] **Step 3:** Vérifier l'échec, implémenter.
- [ ] **Step 4:** `cd web && npm test && npm run lint && npx tsc --noEmit` au vert. Commit
  `feat: convertit des poses en angles en squelette animé`.

---

### Task 4: Page de rendu `/render/[id]`

**Files:**
- Create: `web/app/render/[id]/page.tsx`, `web/app/ExerciseAvatar.tsx`
- Modify (seulement si l'extraction est sans risque) : `web/app/PostureAvatar3D.tsx`

**Contenu :**
- `ExerciseAvatar` : charge `muscle-rig.glb`, prépare scène, matériaux et routage de maillage comme
  `PostureAvatar3D.tsx::Rig` (clone de `gltf.scene`, matériaux clonés, émissif neutralisé, frustum
  culling désactivé). Si ce bloc peut être extrait en une fonction pure partagée **sans changer le
  comportement** (les tests `skinning-integration.test.ts` et `muscleSegments.test.ts` le gardent),
  l'extraire ; sinon le dupliquer avec un commentaire renvoyant à la source. Couleur : segments de
  `target_segments` en bleu (`#1E88E5`), tout le reste en gris neutre (`DEFAULT_COLOR`).
- Cadrage fixe selon `view` ; fond uni ; pas d'`OrbitControls`.
- Surimpression HTML : titre, consigne active (`activeInstruction`), minuteur du temps restant,
  **crédit Z-Anatomy / CC BY-SA 4.0**, mention « Brouillon » si `status == "draft"`.
- Contrat avec le script de rendu : `window.__tmsRender = { load(exercise), ready: Promise<void>,
  duration: number, setTime(t): Promise<void>, stage: HTMLElement }`. `setTime` applique la pose,
  rend **de façon synchrone** (`frameloop="never"` et rendu explicite, ou `invalidate` suivi d'une
  attente d'image) et ne rend jamais en temps réel : aucune dépendance à l'horloge.
- Lire `web/AGENTS.md` et le guide Next.js (route dynamique, composant client) avant de coder.

- [ ] **Step 1:** Implémenter la page et le composant.
- [ ] **Step 2:** Vérification visuelle (navigateur sans écran, capture) de **chaque** exercice livré, à
  trois instants (début, point d'extension maximal, fin). Corriger les poses ou les signes d'angle
  jusqu'à ce que chaque geste soit lisible et anatomiquement plausible. Conserver les captures dans le
  répertoire temporaire et les décrire dans le commit.
- [ ] **Step 3:** `cd web && npm test && npm run lint && npx tsc --noEmit` au vert. Commit
  `feat: ajoute la page de rendu des exercices d'étirement`.

---

### Task 5: Script de rendu et assemblage vidéo

**Files:**
- Create: `web/scripts/render-exercise.mjs`
- Modify: `web/package.json` (script `render:exercise`)
- Test: `tests/test_render_determinism.py` (ignoré si `node`, `ffmpeg` ou Chromium sont absents)

**Comportement :** `node scripts/render-exercise.mjs --definition <fichier.json> --out <fichier.mp4>
[--fps 15] [--size 640] [--base-url http://localhost:3000]`. Lance Chromium sans écran, ouvre
`/render/<id>`, injecte la définition via `window.__tmsRender.load`, boucle sur `t = i / fps`,
capture le `stage` en PNG, envoie les images à `ffmpeg` (`image2pipe`, `libx264`, `yuv420p`, `-movflags
+faststart`), sort avec un code non nul et un message clair si Chromium, `ffmpeg` ou le serveur
Next.js sont introuvables. Chemin de l'exécutable Chromium surchargeable (`CHROMIUM_PATH`).

- [ ] **Step 1:** Implémenter le script.
- [ ] **Step 2:** Test de déterminisme : rendre deux fois le même exercice court, décoder les images
  des deux vidéos (`ffmpeg -f framehash` ou équivalent) et exiger des hashes identiques image par image.
  Test ignoré proprement quand l'environnement ne permet pas le rendu.
- [ ] **Step 3:** Vérifier : durée de la vidéo = `duration_seconds` (à une image près), 15 images par
  seconde par défaut, lisible (`ffprobe`), codec H.264. Consigner le temps de rendu mesuré.
- [ ] **Step 4:** Commit `feat: rend un exercice d'étirement en vidéo, image par image`.

---

### Task 6: Fournisseurs optionnels et voix

**Files:**
- Create: `src/tms_vision/providers.py`
- Test: `tests/test_providers.py`

**Interfaces:**
- Produces : classes abstraites `NarrationProvider.synthesize(text: str, language: str) -> bytes` (WAV),
  `InstructionProvider.rewrite(exercise: dict, language: str) -> list[dict]` (liste de
  `{t, text}`), `ExerciseProvider.propose(zone: str, constraints: dict) -> dict` (définition au format
  ci-dessus) ; `NullNarrationProvider` et consorts (renvoient `None`, ou lèvent
  `ProviderNotConfigured` pour `propose`) ; `providers.get_narration_provider()`,
  `get_instruction_provider()`, `get_exercise_provider()` lisant `TMS_NARRATION_PROVIDER`,
  `TMS_INSTRUCTION_PROVIDER`, `TMS_EXERCISE_PROVIDER` (`none`, `command`, ou `module.chemin:Classe`) ;
  `CommandNarrationProvider` : exécute `TMS_NARRATION_COMMAND` **sans shell** (`shlex.split`), texte sur
  l'entrée standard, WAV sur la sortie standard, délai maximal, erreur claire sur code de retour non nul
  (permet de brancher une voix locale open source sans écrire de code) ;
  `schedule_narration(instructions, durations) -> list[tuple[float, int]]` (instant de départ de chaque
  segment, décalé quand le précédent n'est pas fini : jamais de chevauchement).

- [ ] **Step 1:** Tests : valeur par défaut = aucun fournisseur ; variable `none` ; classe chargée par
  chemin de module ; classe inconnue → erreur nommant la variable ; `CommandNarrationProvider` avec une
  commande de test (`python -c`) qui renvoie des octets connus ; code de retour non nul → erreur ;
  délai dépassé → erreur ; `schedule_narration` (pas de chevauchement, ordre conservé, aucun décalage
  si tout tient) ; **aucun import réseau dans le chemin par défaut** (le module se charge sans
  configuration et sans accès réseau).
- [ ] **Step 2:** Vérifier l'échec, implémenter.
- [ ] **Step 3:** `python -m pytest` : mêmes échecs que la référence. Commit
  `feat: fournisseurs optionnels pour la voix, les consignes et les exercices`.

---

### Task 7: Orchestrateur `capsule_build`

**Files:**
- Create: `src/tms_vision/capsule_build.py`
- Modify: `src/tms_vision/exercises.py` (commande `propose`), `.gitignore` si nécessaire
- Test: `tests/test_capsule_build.py`

**Interfaces / comportement :**
- `python -m tms_vision.capsule_build [--id ID ...] [--all] [--force] [--language fr] [--base-url URL]`
  pour chaque exercice : valide ; ignore si `data/capsules/{id}.mp4` existe avec le même
  `definition_sha256` (sauf `--force`) ; appelle `NarrationProvider` pour chaque consigne si un
  fournisseur est configuré ; lance `node web/scripts/render-exercise.mjs` ; si audio, le place aux
  instants de `schedule_narration` (`ffmpeg`, `adelay` + `amix`) et **prolonge la dernière image** si la
  voix dépasse la vidéo ; écrit `data/capsules/{id}.mp4` et `{id}.json` (`definition_sha256`,
  `rendered_at`, `duration_seconds`, `fps`, `narration` = nom du fournisseur ou `null`) ; code de sortie
  non nul si un exercice échoue, sans arrêter les autres.
- `python -m tms_vision.exercises propose --zone ZONE` : sans fournisseur configuré, échoue avec un
  message clair ; sinon valide la sortie du `ExerciseProvider` avec le même validateur, force
  `source: "ai"` et `status: "draft"`, et l'écrit dans `exercises/drafts/`. **Jamais dans le
  catalogue.**

- [ ] **Step 1:** Tests, avec le rendu Node et `ffmpeg` remplacés par des doubles (`monkeypatch` sur
  `subprocess`) : exercice invalide → échec nommé, rien d'écrit ; sauté quand le hash correspond ;
  refait avec `--force` ou quand la définition change ; métadonnées écrites ; un exercice en échec
  n'empêche pas les suivants ; narration appelée une fois par consigne et seulement si configurée ;
  commande `ffmpeg` d'audio construite à partir de `schedule_narration` ; `propose` sans fournisseur
  échoue, avec un faux fournisseur écrit un brouillon `source: "ai"` dans `drafts/` et rien au
  catalogue, rejette une sortie invalide.
- [ ] **Step 2:** Vérifier l'échec, implémenter.
- [ ] **Step 3:** Exécution réelle de bout en bout : démarrer `npm run dev`, lancer
  `python -m tms_vision.capsule_build --all`, vérifier les quatre `.mp4` avec `ffprobe`, puis une
  exécution avec une `TMS_NARRATION_COMMAND` de test qui produit un WAV (par exemple un bip) pour
  valider le mixage audio. Consigner les durées de rendu.
- [ ] **Step 4:** `python -m pytest` : mêmes échecs que la référence. Commit
  `feat: orchestre la génération des vidéos d'étirement`.

---

### Task 8: Service des vidéos et affichage dans l'interface

**Files:**
- Modify: `src/tms_vision/api.py`, `web/app/ProgramList.tsx`
- Test: `tests/test_api.py`

**Interfaces :**
- `GET /capsules/{id}/video` : sert `data/capsules/{id}.mp4` avec support `Range` (réutiliser
  `_parse_single_byte_range` et la logique de `get_analysis_video`, en extraire une fonction commune
  plutôt que dupliquer) ; 404 si l'`id` n'est pas au catalogue ou si le fichier n'existe pas ; l'`id`
  est validé contre le catalogue (jamais utilisé tel quel dans un chemin : pas de traversée de
  répertoire).
- Les dictionnaires de capsule renvoyés par `/analyses/{id}/recommendation` et
  `/bilans/{id}/program` gagnent `video_available: bool` (fichier présent), calculé dans l'API.
- `ProgramList` : affiche un lecteur `<video controls>` quand `video_available`, un badge « Brouillon,
  à valider par l'ostéopathe » quand `status == "draft"`, et rien d'autre de changé sinon.

- [ ] **Step 1:** Tests : 404 id inconnu ; 404 fichier absent ; 200 avec contenu ; 206 avec `Range` ;
  416 plage invalide ; `id` malveillant (`../x`) → 404 ; `video_available` vrai/faux dans la
  recommandation et dans le programme de bilan.
- [ ] **Step 2:** Vérifier l'échec, implémenter côté API puis côté interface.
- [ ] **Step 3:** `python -m pytest` (mêmes échecs que la référence) et `cd web && npm test && npm run
  lint && npx tsc --noEmit`.
- [ ] **Step 4:** Vérification manuelle dans un navigateur : générer une vidéo, ouvrir un résultat
  d'analyse dont le programme la recommande, vérifier le badge et la lecture. Consigner le résultat.
- [ ] **Step 5:** Commit `feat: sert les vidéos d'étirement et les affiche dans le programme`.

---

### Task 9: Documentation et vérification finale

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md`,
  `NOTICE.md`

- [ ] **Step 1:** README : section « Générer les modules d'étirement » (prérequis : `ffmpeg`, Chromium
  pour Playwright, serveur Next.js lancé ; commandes ; format d'un exercice ; cycle brouillon →
  validation ; fournisseurs et variables d'environnement ; limites du squelette) et liens vers la spec et
  le plan dans la section 8.
- [ ] **Step 2:** Spec : statut « Tranches 1, 2 et 3 livrées » ; remplacer le choix technique du rendu
  « à trancher » par la décision prise et la mesure du Task 1 ; aligner le format d'exercice
  (consignes datées, `status`, `source`, angles).
- [ ] **Step 3:** `NOTICE.md` : préciser que les vidéos générées avec l'avatar sont des œuvres
  dérivées de maillages CC BY-SA 4.0 et portent le crédit.
- [ ] **Step 4:** `python -m pytest` (mêmes échecs que la référence), `cd web && npm test && npm run
  lint && npx tsc --noEmit`.
- [ ] **Step 5:** Commit `docs: documente la génération des modules d'étirement`.

---

## Questions ouvertes

- **Licence des vidéos générées.** Elles contiennent des maillages Z-Anatomy en CC BY-SA 4.0 : leur
  diffusion peut impliquer de les proposer elles aussi sous cette licence, ce qui compte si le produit
  est commercial. À faire confirmer par une personne compétente avant toute diffusion ; le crédit
  est déjà incrusté.
- **Validation clinique.** Les quatre exercices livrés sont des brouillons rédigés sans expertise
  d'ostéopathe. Aucun ne doit être présenté à un salarié comme validé avant relecture, correction des
  poses et renseignement de `validated_by` / `validated_on`.
- **Limites du squelette.** 9 os, sans poignet ni main. Si l'ostéopathe veut des exercices de
  poignet ou de rotation du cou, le rig lui-même doit être étendu (hors périmètre).
- **Voix.** Aucune voix n'est livrée : le fournisseur par défaut ne fait rien. Choisir un moteur local
  open source (par exemple via `TMS_NARRATION_COMMAND`) reste à décider.
- **Catalogue final** de 30 à 45 exercices : à définir par l'ostéopathe ; cette tranche livre l'outil
  pour les produire, pas le contenu.

## Hors périmètre de cette tranche

- Génération de vidéo par un modèle génératif (texte vers vidéo).
- Contenu de la correction du geste.
- Choix d'un moteur de synthèse vocale, éditeur graphique d'exercices, extension du squelette.
