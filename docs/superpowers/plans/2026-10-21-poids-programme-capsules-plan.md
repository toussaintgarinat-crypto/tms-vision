# Poids (précis ou fourchette) et programme de capsules — Plan d'implémentation (Tranche 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à l'opérateur de renseigner, après l'analyse vidéo, le poids manipulé (précis,
en fourchette, ou aucun), recalculer le score RULA sans relancer l'estimation de pose, et
recommander un programme de 2 à 3 capsules d'étirement classées par charge de chaque zone, avec
la structure réservée à la correction du geste.

**Architecture:** Trois modules purs : `load.py` (valeur de poids et bornes), `rescore.py`
(recalcul des scores d'une analyse à partir des sous-scores déjà persistés) et un classement de
programme dans `capsules.py`. `storage.py` gagne une table `analysis_loads` et une fonction de mise
à jour transactionnelle. `api.py` expose `PUT /analyses/{id}/load` et les programmes. Le frontend
ajoute un éditeur de poids et l'affichage du programme.

**Tech Stack:** Python 3.11 (backend), Next.js/TypeScript (frontend), pytest, DuckDB (déjà en place).

## Constats qui cadrent ce plan (vérifiés dans le code)

1. **Le recalcul sans pose est possible.** `analysis_frames` ne persiste pas tous les champs de
   `JointAngles` (pas les booléens de torsion, d'abduction, etc.), mais elle persiste
   `posture_score_a`, `posture_score_b` et `muscle_use_score`. Or le poids n'intervient que dans
   `force_load_score`, puis `wrist_arm_score = A + muscle + force`, `neck_trunk_leg_score =
   B + muscle + force`, `final_score = lookup_table_c(...)`, `action_level(final_score)`
   (`rula/scoring.py::compute_rula_score`). Ces trois colonnes suffisent à tout recalculer, et
   `muscle_use_score` ne dépend pas du poids.
2. **Le poids ne change pas les niveaux par segment.** `segment_action_level` vient de
   `action_level(score.neck | trunk | upper_arm | lower_arm)`, des sous-scores de posture seuls.
   Conséquences : l'avatar 3D (qui ne lit que `segment_action_levels`) et le classement actuel des
   zones ne bougent pas quand le poids change. `pose3d_json` n'est donc **pas** réécrit (son champ
   `action_level` global n'est plus lu par le frontend).
3. **La vidéo annotée garde l'ancien score.** Le badge « RULA n » est dessiné dans les pixels
   (`overlay.py`) et la vidéo d'origine n'est pas conservée : elle ne peut pas être recalculée.
   L'interface doit le signaler quand le poids saisi diffère de celui utilisé à l'analyse.
4. **Décision ouverte, non tranchée ici : l'effet du poids sur le programme.** Vu le constat 2, le
   classement des zones reste fondé sur le temps en niveau élevé, comme aujourd'hui ; le poids
   s'affiche dans le motif de la recommandation mais ne change pas le classement. Faire peser une
   charge lourde sur le tronc et les épaules demande une règle que l'ostéopathe doit fixer
   (voir « Questions ouvertes »). Aucun coefficient n'est inventé.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md`
  (Partie B, plus la structure réservée de la Partie D).
- Trois formes de poids : `none` (équivaut à 0 kg), `exact` (`kg >= 0`), `range`
  (`0 <= kg_min <= kg_max`). Plafond de plausibilité : 500 kg.
- Pour une fourchette, le score est calculé aux deux bornes. Les colonnes persistées
  (`force_load_score`, `final_score`, `action_level` par frame, et `max_score`, `average_score`,
  `time_by_action_level`, `load_kg` de l'analyse) portent le **cas défavorable** (borne haute). Les
  deux bornes sont conservées dans `analysis_loads.score_range` pour afficher l'intervalle.
- Le recalcul doit reproduire **exactement** `compute_rula_score` : un test de propriété le
  garantit (voir Task 2).
- Les zones restent `neck`, `trunk`, `upper_arm`, `lower_arm`. Égalité de charge → ordre fixe
  `trunk > neck > upper_arm > lower_arm`. `lower_arm` ne peut toujours pas atteindre un niveau élevé
  (limite documentée dans `capsules.py`, hors périmètre).
- Programme : zones à charge > 0 uniquement, **3 au maximum**, classées par charge décroissante ;
  aucune zone chargée → liste vide (pas de recommandation forcée).
- Compatibilité : `GET /analyses/{id}/recommendation` conserve ses clés `zone` et `capsule`
  (premier élément du programme) et gagne `program` et `gesture_corrections`. Les analyses
  existantes (sans ligne `analysis_loads`) sont lues comme `exact` avec leur `load_kg`.
- `storage.py` reste une couche de persistance : aucune logique de scoring ni de classement n'y
  vit.
- Référence de non-régression : dans ce conteneur, 22 tests échouent **avant** tout changement
  (`tests/test_api.py`, `test_cli.py`, `test_pipeline.py`, `test_pose_estimation.py`, à cause de
  `mediapipe` sans `solutions`). Avant la première tâche, enregistrer la liste avec
  `python -m pytest -q 2>&1 | grep FAILED | sed 's/ - .*//' | sort > /tmp/baseline.txt`, puis vérifier
  après chaque tâche que la liste des échecs est identique.
- Frontend : lire le guide pertinent dans `web/node_modules/next/dist/docs/` avant d'écrire du
  code Next.js (voir `web/AGENTS.md`) ; `npm test`, `npm run lint` dans `web/`.

---

### Task 1: `load.py` — valeur de poids et bornes

**Files:**
- Create: `src/tms_vision/load.py`
- Test: `tests/test_load.py`

**Interfaces:**
- Produces : `load.Load` (dataclass gelée : `kind: str`, `kg: float | None`, `kg_min: float | None`,
  `kg_max: float | None`), `load.parse_load(kind, kg=None, kg_min=None, kg_max=None) -> Load`
  (lève `ValueError` si incohérent), `load.bounds(load) -> tuple[float, float]` (bas, haut ;
  `none` → `(0.0, 0.0)`, `exact` → `(kg, kg)`), `load.MAX_LOAD_KG = 500.0`.

- [ ] **Step 1:** Écrire les tests : `none` sans valeur ; `none` avec un poids → `ValueError` ;
  `exact` valide, négatif, absent, au-dessus de 500 ; `range` valide, `kg_min > kg_max`,
  borne absente, négative ; `kind` inconnu ; `bounds` pour les trois formes ; fourchette réduite
  (`kg_min == kg_max`) acceptée.
- [ ] **Step 2:** Lancer `python -m pytest tests/test_load.py` : échec attendu.
- [ ] **Step 3:** Implémenter.
- [ ] **Step 4:** Tests au vert.
- [ ] **Step 5:** Commit `feat: modélise le poids précis ou en fourchette`.

---

### Task 2: `rescore.py` et `summarize_rows` — recalcul des scores sans pose

**Files:**
- Modify: `src/tms_vision/export.py` (extraire `summarize_rows`)
- Create: `src/tms_vision/rescore.py`
- Modify: `tests/test_export.py`
- Test: `tests/test_rescore.py`

**Interfaces:**
- Produces : `export.summarize_rows(rows: list[dict]) -> dict` (même sortie que
  `ResultsExporter.summary()` ; chaque ligne a `frame_index`, `timestamp_seconds`, `detected`,
  `final_score`, `action_level`) ; `rescore.rescore_frames(frames: list[dict], load_kg: float) -> list[dict]`
  où chaque frame d'entrée porte `frame_index`, `timestamp_seconds`, `detected`, `posture_score_a`,
  `posture_score_b`, `muscle_use_score`, et chaque frame de sortie les mêmes clés plus
  `force_load_score`, `final_score`, `action_level` (valeurs `None` si la frame n'a pas de score) ;
  `rescore.summarize_for_load(frames, load_kg) -> dict` (`rescore_frames` puis `summarize_rows`).

- [ ] **Step 1:** Refactoriser sans changer le comportement. Déplacer l'algorithme de
  `ResultsExporter.summary()` dans `summarize_rows` (le test existant de `summary()` sert de
  régression) et faire appeler `summarize_rows(self.rows())` par `summary()`. Lancer
  `python -m pytest tests/test_export.py` : les tests existants passent toujours.
- [ ] **Step 2:** Écrire `tests/test_rescore.py` :
  - **test de propriété** : pour plusieurs `JointAngles` (posture neutre, tronc très fléchi, bras
    levé) et pour `load_kg` dans `{0, 1.9, 2, 5, 10, 10.1, 25}` et `muscle_use_score` dans `{0, 1}`,
    appeler `compute_rula_score(angles, wrist_twist=1, load_kg=load_kg, muscle_use_score=m)`, en
    extraire `posture_score_a`, `posture_score_b`, `muscle_use_score`, puis vérifier que
    `rescore_frames` redonne exactement `force_load_score`, `final_score` et `action_level` ;
  - recalcul d'une analyse produite à 0 kg avec 15 kg : le score final augmente, les sous-scores de
    posture ne bougent pas ;
  - frame non détectée (`posture_score_a is None`) → `final_score` reste `None` ;
  - `summarize_for_load` : `max_score`, `average_score`, `time_by_action_level` cohérents avec un
    calcul manuel sur 3 frames ; aucune frame détectée → même résumé vide que `summary()`.
- [ ] **Step 3:** Vérifier l'échec, puis implémenter `rescore.py` avec les fonctions publiques
  existantes (`force_load_score`, `action_level` de `rula/scoring.py`, `lookup_table_c` de
  `rula/tables.py`). Ne pas dupliquer les formules : importer.
- [ ] **Step 4:** `python -m pytest tests/test_export.py tests/test_rescore.py tests/test_rula_scoring.py`
  au vert.
- [ ] **Step 5:** Commit `feat: recalcule les scores RULA d'une analyse à partir des sous-scores persistés`.

---

### Task 3: Persistance du poids et mise à jour transactionnelle

**Files:**
- Modify: `src/tms_vision/storage.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Produces : table `analysis_loads (analysis_id VARCHAR PRIMARY KEY REFERENCES analyses(id), kind VARCHAR NOT NULL, kg DOUBLE, kg_min DOUBLE, kg_max DOUBLE, original_load_kg DOUBLE NOT NULL, score_range VARCHAR, updated_at TIMESTAMP NOT NULL)`
  (créée par `_connect()`, aucune migration) ;
  `storage.get_frame_scores(analysis_id) -> list[dict] | None` (`frame_index`, `timestamp_seconds`,
  `detected`, `posture_score_a`, `posture_score_b`, `muscle_use_score`) ;
  `storage.update_load(analysis_id, *, load: dict, original_load_kg_if_new: float, frame_scores: list[dict], summary: dict, score_range: dict | None) -> None`
  (une transaction : écrit `analysis_loads`, met à jour `force_load_score`, `final_score`,
  `action_level` de chaque frame, puis `max_score`, `average_score`, `time_by_action_level` et
  `load_kg` de l'analyse ; `KeyError` si l'analyse est inconnue) ;
  `storage.get_analysis` ajoute la clé `load` : `{kind, kg, kg_min, kg_max, original_load_kg, score_range}`.
  Une analyse sans ligne `analysis_loads` donne `{kind: "exact", kg: <load_kg>, kg_min: None, kg_max: None, original_load_kg: <load_kg>, score_range: None}`.
- `original_load_kg` n'est fixé qu'à la **première** mise à jour (poids utilisé pour le badge de la
  vidéo annotée) et conservé ensuite.

- [ ] **Step 1: Test d'abord, contre le risque DuckDB.** Écrire un test qui sauvegarde une analyse,
  la rattache à un bilan (lignes enfants dans `bilan_analyses` et `analysis_frames`), puis appelle
  `update_load`. DuckDB a des limites connues sur la mise à jour d'une ligne parente référencée par
  une clé étrangère ; ce test doit passer **avant** d'écrire le reste.
- [ ] **Step 2:** Autres tests : relecture du `load` d'une analyse legacy ; `update_load` met à jour
  frames et résumé de façon cohérente ; deuxième appel conserve `original_load_kg` ; échec au milieu
  d'une mise à jour (simuler une exception sur l'écriture des frames) → rollback complet, ancien
  état intact ; analyse inconnue → `KeyError` ; `get_frame_scores` ordonné et `None` si inconnue ;
  la table est créée par `_connect()` (compléter le test des tables).
- [ ] **Step 3:** Vérifier l'échec, implémenter sur le modèle de `save_analysis` (transaction
  explicite, `executemany` pour les frames).
- [ ] **Step 4 (si le Step 1 échoue sur la clé étrangère) :** ne pas contourner par des
  suppressions-réinsertions. Solution de repli : ne **pas** modifier `analyses` ; porter
  `max_score`, `average_score`, `time_by_action_level` et le poids effectif dans
  `analysis_loads`, et faire lire `get_analysis` / `list_analyses` avec `COALESCE` sur cette table.
  Adapter les tests en conséquence et le noter dans le commit.
- [ ] **Step 5:** `python -m pytest tests/test_storage.py tests/test_api.py` : mêmes échecs que la
  référence, aucun nouveau.
- [ ] **Step 6:** Commit `feat: persiste le poids et recalcule les scores d'une analyse`.

---

### Task 4: Endpoint de mise à jour du poids

**Files:**
- Modify: `src/tms_vision/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces : `PUT /analyses/{id}/load` (JSON `{kind: "none" | "exact" | "range", kg?, kg_min?, kg_max?}`)
  → l'analyse mise à jour (même forme que `GET /analyses/{id}`, donc avec `load` et le résumé
  recalculé). 404 si l'analyse est inconnue ; 422 si le poids est incohérent (message lisible, voir
  `load.parse_load`) ; idempotent.
  `POST /analyses` et `POST /uploads/{id}/complete` : `load_kg` devient **facultatif** (défaut 0.0,
  `ge=0`), comportement inchangé quand il est fourni.
  CORS : ajouter `PUT` est déjà autorisé ; aucune modification.

- [ ] **Step 1:** Tests API (analyses créées avec `storage.save_analysis` et des lignes de frame
  portant `posture_score_a`, `posture_score_b`, `muscle_use_score`) : `exact` 15 kg → scores et
  résumé relevés ; `range` 8 à 12 kg à cheval sur le seuil de 10 kg → `max_score` = cas haut,
  `load.score_range.low.max_score < high.max_score` ; `range` entièrement sous le seuil → `low == high` ;
  `none` → 0 kg ; mêmes valeurs deux fois → même résultat ; 404 ; 422 (`kg_min > kg_max`, négatif,
  champs manquants, 600 kg) ; `GET /analyses/{id}` reflète le `load` ; création sans `load_kg`
  acceptée (compléter les tests de création existants sans les casser).
- [ ] **Step 2:** Vérifier l'échec, implémenter : `load.parse_load` → `load.bounds` →
  `storage.get_frame_scores` → `rescore.summarize_for_load` aux deux bornes → `storage.update_load`
  (frames et résumé du cas haut, `score_range` = résumés bas et haut seulement si les bornes
  diffèrent).
- [ ] **Step 3:** `python -m pytest` : mêmes échecs que la référence, tous les nouveaux tests passent.
- [ ] **Step 4:** Commit `feat: expose la saisie du poids précis ou en fourchette`.

---

### Task 5: Programme de 2 à 3 capsules et structure du geste

**Files:**
- Modify: `src/tms_vision/capsules.py`
- Modify: `src/tms_vision/api.py`
- Modify: `tests/test_capsules.py`, `tests/test_api.py`

**Interfaces:**
- Produces : `capsules.Capsule` gagne `kind: str = "stretch"` (la correction du geste, plus tard,
  utilisera `kind="gesture"`) ; `capsules.MAX_PROGRAM_SIZE = 3` ;
  `capsules.rank_zones(load_by_zone: dict[str, float]) -> list[tuple[str, float]]` (zones à charge
  > 0, charge décroissante, égalité par `ZONE_PRIORITY`, tronquée à `MAX_PROGRAM_SIZE`) ;
  `capsules.build_program(load_by_zone, unit_label) -> list[dict]` renvoyant, par élément :
  `rank`, `zone`, `capsule`, `reason`, `load` (valeur de la charge) ;
  `capsules.elevated_seconds_by_zone(frames) -> dict[str, float]` (le cumul que
  `compute_worst_zone` calcule déjà, extrait pour être partagé ; `compute_worst_zone` s'appuie
  dessus, comportement inchangé).
- Endpoints : `GET /analyses/{id}/recommendation` renvoie
  `{zone, capsule, program: [...], gesture_corrections: [], load}` (`zone`/`capsule` = premier
  élément, `null` si le programme est vide ; `load` = objet poids de l'analyse pour le motif) ;
  `GET /bilans/{id}/program` renvoie `{program: [...], gesture_corrections: [], warnings: []}` classé
  par `projected_elevated_hours` de `bilan.project_bilan`. `gesture_corrections` est toujours la
  liste vide dans cette tranche.
- Motif d'un élément : texte factuel, par exemple « Tronc : 42 s en posture à risque sur l'échantillon »
  pour une analyse, « Tronc : environ 4 h 12 en posture à risque sur 9 h estimées » pour un bilan ; si
  un poids est saisi, ajouter « charge manipulée : 12 kg » ou « 8 à 12 kg ». Aucune règle de
  pondération par le poids.

- [ ] **Step 1:** Tests unitaires : `rank_zones` (tri, égalité, zéro exclu, plafond à 3, entrée
  vide) ; `build_program` (rang, motif, 1 / 2 / 3 éléments) ; `elevated_seconds_by_zone` ; non-régression
  de `compute_worst_zone` (tous les tests existants passent sans modification).
- [ ] **Step 2:** Tests API : analyse avec trois zones chargées → `program` de 3 éléments, premier =
  même zone que l'ancien `zone` ; une seule zone → 1 élément ; aucune → `program == []`, `zone is None` ;
  `gesture_corrections == []` ; motif contenant le poids quand il est saisi ; bilan à deux analyses →
  programme classé par heures projetées ; bilan vide → programme vide ; 404 pour un bilan inconnu.
- [ ] **Step 3:** Vérifier l'échec, implémenter.
- [ ] **Step 4:** `python -m pytest` : mêmes échecs que la référence.
- [ ] **Step 5:** Commit `feat: recommande un programme de 2 à 3 capsules classées par charge`.

---

### Task 6: Interface — éditeur de poids et programme

**Files:**
- Create: `web/app/LoadEditor.tsx`
- Create: `web/app/loadFormat.ts`, `web/app/loadFormat.test.ts`
- Modify: `web/app/AnalysisResult.tsx` (éditeur, intervalle de score, programme)
- Modify: `web/app/bilans/[id]/page.tsx` (programme du bilan)
- Modify: `web/app/historique/page.tsx`, `web/app/historique/[id]/page.tsx` (types : `load`)

**Contenu :**
- `LoadEditor` : choix « Aucun poids », « Poids précis (kg) », « Fourchette (de … à … kg) ». Validation
  côté client identique à l'API (valeurs, ordre des bornes, 500 kg), envoi en `PUT /analyses/{id}/load`,
  affichage du message `detail` en cas d'erreur 422. Le résultat met à jour le résumé affiché sans
  recharger la page.
- `loadFormat.ts` (pur, testé) : `formatLoad(load)` (« 12 kg », « 8 à 12 kg », « Aucun poids »),
  `formatScoreRange(summary, load)` (« 5 » ou « 5 à 6 selon la charge »), `isVideoBadgeStale(load)`
  (poids effectif différent de `original_load_kg`).
- Dans `AnalysisResult` : intervalle de score quand `score_range` existe ; mention « La vidéo annotée
  affiche le score calculé avec X kg à l'analyse » quand `isVideoBadgeStale` ; le bloc de
  recommandation unique devient la liste du programme (rang, zone, titre, description, motif) avec
  repli sur le comportement actuel si `program` est absent ; la section « Correction du geste »
  n'apparaît que si `gesture_corrections` est non vide (donc jamais dans cette tranche).
- Page de bilan : section « Programme d'étirements » alimentée par `/bilans/{id}/program`.
- Conventions : état porté par la clé (`analysisId`) comme dans `AnalysisResult.tsx`, `cancelled` dans
  les effets, `API_URL` via `NEXT_PUBLIC_API_URL`, liens vers routes dynamiques en `<a>` (voir README
  sur l'exception `next/link`).

- [ ] **Step 1:** Lire `web/AGENTS.md` et le guide Next.js pertinent.
- [ ] **Step 2:** Écrire les tests de `loadFormat.ts` (Vitest), vérifier l'échec, implémenter.
- [ ] **Step 3:** Écrire `LoadEditor` et brancher `AnalysisResult` et la page de bilan.
- [ ] **Step 4:** `cd web && npm test && npm run lint` au vert.
- [ ] **Step 5 :** Vérification manuelle dans un navigateur (Playwright de `/opt/node-tools` ou
  navigateur réel ; démarrer l'API avec `PYTHONPATH=src python -m uvicorn tms_vision.api:app` et le
  frontend avec `npm run dev`, avec des analyses créées par `storage.save_analysis` si MediaPipe est
  indisponible) : saisir un poids précis, une fourchette à cheval sur 10 kg, « Aucun poids » ;
  vérifier le score ou l'intervalle affiché, le message sur la vidéo annotée, un 422 lisible, le
  programme de 2 à 3 capsules sur une analyse et sur un bilan. Consigner le résultat.
- [ ] **Step 6:** Commit `feat: ajoute la saisie du poids et l'affichage du programme d'étirements`.

---

### Task 7: Documentation et vérification finale

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md`

- [ ] **Step 1:** README : section « Poids et programme d'étirements » (formes de poids, recalcul sans
  relancer la pose, cas défavorable, limite du badge de la vidéo annotée, programme de 2 à 3
  capsules, structure réservée à la correction du geste) et liens vers la spec et le plan dans la
  liste de la section 8.
- [ ] **Step 2:** Spec : statut « Tranches 1 et 2 livrées » ; corriger la Partie B selon le constat 2
  (le poids ne modifie pas le classement des zones) tant que la question ouverte n'est pas tranchée.
- [ ] **Step 3:** `python -m pytest` (mêmes échecs que la référence), `cd web && npm test && npm run lint`.
- [ ] **Step 4:** Commit `docs: documente le poids et le programme d'étirements`.

---

## Questions ouvertes

- **Effet du poids sur le programme.** Aujourd'hui le poids ne change que le score global, pas le
  classement des zones. Si une charge lourde doit faire monter le tronc et les épaules dans le
  programme, il faut une règle fixée avec l'ostéopathe (seuil de poids, zones concernées). À
  trancher avant ou pendant la Tranche 2 ; seule la Task 5 serait concernée.
- **Badge de la vidéo annotée.** Il garde le score du poids initial. Acceptable avec la mention de
  l'interface ; la seule alternative est de conserver la vidéo d'origine, hors périmètre.

## Hors périmètre de cette tranche

- Génération des vidéos d'étirement et fournisseurs IA (Tranche 3).
- Contenu de la correction du geste (la structure vide existe, rien n'est affiché).
- Fréquence de micro-pause suggérée, seuils par segment pour `lower_arm`.
