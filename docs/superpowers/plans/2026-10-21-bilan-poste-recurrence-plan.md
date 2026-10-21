# Bilan de poste et récurrence — Plan d'implémentation (Tranche 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regrouper plusieurs analyses d'un même poste dans un « bilan de poste », mesurer la
récurrence des mouvements par zone sur chaque vidéo, et projeter ces mesures sur la journée de
travail en pondérant chaque vidéo par la durée de l'activité qu'elle représente.

**Architecture:** Deux nouveaux modules purs : `src/tms_vision/recurrence.py` (indicateurs par
zone à partir des frames d'une analyse) et `src/tms_vision/bilan.py` (projection pondérée sur un
bilan). `storage.py` gagne deux tables (`bilans`, `bilan_analyses`) et les fonctions de lecture
nécessaires. `api.py` expose le bilan et son rapport. Le frontend ajoute une page de bilan. Les
analyses existantes ne sont pas modifiées : toutes les données de récurrence se recalculent depuis
`analysis_frames` (les angles par zone y sont déjà persistés).

**Tech Stack:** Python 3.11 (backend), Next.js/TypeScript (frontend), pytest, DuckDB (déjà en place).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md`
  (Partie A uniquement ; les parties B, C, D sont d'autres tranches).
- 4 zones seulement : `neck`, `trunk`, `upper_arm`, `lower_arm`, avec les colonnes d'angle
  `neck_flexion_deg`, `trunk_flexion_deg`, `upper_arm_flexion_deg`, `lower_arm_angle_deg`.
- **Aucun seuil n'est codé en dur dans `recurrence.py`.** Tous vivent par zone dans
  `recurrence_thresholds.json` : `min_prominence_deg` (amplitude minimale d'un cycle) et
  `static_variation_deg` (variation maximale d'une plage statique) avec les valeurs du PoC
  (10° et 15°) comme point de départ provisoire, `repetitive_cycles_per_minute` et
  `static_seconds` (interprétation) à `null`. Le fichier porte `"calibrated": false` tant que
  l'ostéopathe n'a pas validé les valeurs.
- Tant que `calibrated` est faux, le rapport donne les chiffres bruts et la mention « seuils non
  calibrés ». Il ne classe aucune zone, ce que les seuils d'interprétation vides interdisent de
  toute façon.
- Le score RULA et `detect_muscle_use` **ne changent pas de comportement** : les helpers de
  `rula/scoring.py` sont seulement rendus réutilisables, avec des valeurs par défaut identiques.
- Une analyse non confirmée représentative est listée avec ses chiffres bruts mais **exclue** des
  sommes de projection.
- `sum(activity_hours) <= workday_hours` ; la part non documentée = `workday_hours - sum`.
- Échantillon de moins de 30 s : valeurs calculées, avertissement explicite dans le rapport.
- `storage.py` reste une couche de persistance pure : aucune logique de projection n'y vit.
- Frontend : avant d'écrire du code Next.js, lire le guide pertinent dans
  `web/node_modules/next/dist/docs/` (voir `web/AGENTS.md`).
- Lancer les tests avec `python -m pytest` depuis la racine ; côté web, `npm test` et
  `npm run lint` dans `web/`.

---

### Task 1: Rendre réutilisables les helpers de cycles de `rula/scoring.py`

**Files:**
- Modify: `src/tms_vision/rula/scoring.py`
- Modify: `tests/test_rula_scoring.py`

**Interfaces:**
- Produces: `scoring.count_direction_changes(history, min_prominence_deg=REPETITION_MIN_PROMINENCE_DEG) -> int`
  et `scoring.longest_static_span_seconds(history, variation_deg=STATIC_VARIATION_THRESHOLD_DEG) -> float`
  (renommages publics des helpers `_count_direction_changes` / `_longest_static_span_seconds`,
  avec un paramètre optionnel). `history` reste une liste de `(timestamp_secondes, angle)` triée.

- [ ] **Step 1:** Mettre à jour `tests/test_rula_scoring.py` : importer les noms publics à la place
  de `_longest_static_span_seconds` (ligne 156 et usage ligne 180), puis ajouter deux tests : un
  appel à `longest_static_span_seconds(history, variation_deg=...)` avec une valeur différente du
  défaut et un appel à `count_direction_changes(history, min_prominence_deg=...)` sur une série
  qui change de direction avec 6° d'amplitude (non comptée à 10°, comptée à 5°).
- [ ] **Step 2:** Lancer `python -m pytest tests/test_rula_scoring.py` : les nouveaux tests échouent.
- [ ] **Step 3:** Renommer les deux fonctions en versions publiques, ajouter le paramètre optionnel
  (valeur par défaut = constante actuelle) et remplacer leur usage interne par la constante passée
  en paramètre. `detect_muscle_use` appelle les versions publiques sans argument : comportement
  strictement identique.
- [ ] **Step 4:** `python -m pytest tests/test_rula_scoring.py tests/test_integration_angles_to_score.py tests/test_pipeline.py`
  : tout passe.
- [ ] **Step 5:** Commit `refactor: rend publics les helpers de détection de cycles et de statisme`.

---

### Task 2: Extraire le calcul de durée de frame et lire les angles par frame

**Files:**
- Modify: `src/tms_vision/capsules.py`
- Modify: `src/tms_vision/storage.py`
- Modify: `tests/test_capsules.py`, `tests/test_storage.py`

**Interfaces:**
- Produces: `capsules.frame_durations(frames: list[dict]) -> list[float]` (durée de chaque frame :
  écart au timestamp suivant, `1.0` si une seule frame, `0.0` pour la dernière sinon) ;
  `storage.get_frame_angles(analysis_id: str) -> list[dict] | None` renvoyant, par frame,
  `frame_index`, `timestamp_seconds`, `detected`, les 4 colonnes d'angle et les 4 colonnes
  `*_segment_action_level` (`None` si l'analyse n'existe pas).

- [ ] **Step 1:** Écrire les tests : `frame_durations` sur 0, 1 et 3 frames ; `get_frame_angles`
  (analyse inconnue → `None`, analyse sauvegardée → angles et niveaux relus ; réutiliser
  `_frame_row` de `tests/test_storage.py`).
- [ ] **Step 2:** Vérifier l'échec.
- [ ] **Step 3:** Extraire `frame_durations` depuis `compute_worst_zone` (même algorithme, même
  commentaire de justification déplacé avec lui) et faire utiliser cette fonction à
  `compute_worst_zone`. Ajouter `get_frame_angles` dans `storage.py` sur le modèle de
  `get_frame_segments`.
- [ ] **Step 4:** `python -m pytest tests/test_capsules.py tests/test_storage.py tests/test_api.py` :
  tout passe, y compris les tests existants de recommandation (régression).
- [ ] **Step 5:** Commit `refactor: extrait frame_durations et ajoute la lecture des angles par frame`.

---

### Task 3: `recurrence.py` — indicateurs par zone et seuils configurables

**Files:**
- Create: `src/tms_vision/recurrence.py`
- Create: `src/tms_vision/recurrence_thresholds.json`
- Test: `tests/test_recurrence.py`

**Interfaces:**
- Produces: `recurrence.ZONE_ANGLE_COLUMN: dict[str, str]`, `recurrence.load_thresholds(path=None) -> dict`
  (lit `recurrence_thresholds.json`, renvoie `{"calibrated": bool, "zones": {zone: {"min_prominence_deg": float, "static_variation_deg": float, "repetitive_cycles_per_minute": float | None, "static_seconds": float | None}}}`),
  `recurrence.compute_recurrence(frames: list[dict], thresholds: dict) -> dict`.
- `compute_recurrence` retourne :

```python
{
  "sample_seconds": float,          # frames[-1].timestamp - frames[0].timestamp (1.0 si une frame, 0.0 si aucune)
  "thresholds_calibrated": bool,    # reprend le drapeau "calibrated" du fichier de seuils
  "zones": {
    "<zone>": {
      "cycles": float,                  # changements de direction / 2
      "cycles_per_minute": float | None,   # None si sample_seconds <= 0
      "mean_cycle_seconds": float | None,  # None si aucun cycle
      "longest_static_seconds": float,
      "elevated_seconds": float,           # temps en niveau élevé pour la zone (capsules.ELEVATED_LEVELS)
      "assessment": "repetitive" | "not_repetitive" | None,  # None tant que le seuil de la zone est null
    },
  },
}
```

`recurrence_thresholds.json` livré avec `"calibrated": false`, les 4 zones à 10° / 15° pour
`min_prominence_deg` / `static_variation_deg`, et `repetitive_cycles_per_minute` /
`static_seconds` à `null`.

- [ ] **Step 1: Écrire les tests qui échouent** dans `tests/test_recurrence.py` :
  - série en dents de scie (amplitude 20°, 6 changements de direction sur 60 s) → `cycles == 3`,
    `cycles_per_minute == 3.0`, `mean_cycle_seconds == 20.0` ;
  - série constante → `cycles == 0`, `mean_cycle_seconds is None`, `longest_static_seconds` égal
    à la durée ;
  - frames avec `detected=False` ou angle `None` ignorées pour l'historique d'angle mais comptées
    dans `sample_seconds` ;
  - `elevated_seconds` : mêmes cas que `compute_worst_zone` (niveaux élevés cumulés par zone) ;
  - seuils d'interprétation `None` → `assessment is None` partout ; fichier livré →
    `thresholds_calibrated is False` ;
  - seuil `repetitive_cycles_per_minute = 2.0` avec 3.0 mesurés → `"repetitive"` ; avec 1.0 mesuré
    → `"not_repetitive"` ;
  - `min_prominence_deg` propre à chaque zone : la même série (amplitude 8°) donne 0 cycle avec
    10° et des cycles avec 5° ; idem pour `static_variation_deg` ;
  - `load_thresholds()` sur le fichier livré → `calibrated` faux, 4 zones, 10° / 15° et seuils
    d'interprétation `None`.
- [ ] **Step 2:** Lancer `python -m pytest tests/test_recurrence.py` : échec attendu.
- [ ] **Step 3:** Implémenter. Historique par zone = `[(timestamp, angle)]` des frames détectées avec
  angle non nul. Cycles via `count_direction_changes(history, min_prominence_deg=...)` / 2 ;
  statisme via `longest_static_span_seconds(history, variation_deg=...)` ; les deux paramètres
  viennent de la zone dans le JSON. Durée élevée via `frame_durations(frames)` et
  `ELEVATED_LEVELS` de `capsules.py`. Aucune valeur de seuil dans le code Python.
- [ ] **Step 4:** Tests au vert.
- [ ] **Step 5:** Commit `feat: calcule les indicateurs de récurrence par zone`.

---

### Task 4: `bilan.py` — projection pondérée sur la journée

**Files:**
- Create: `src/tms_vision/bilan.py`
- Test: `tests/test_bilan.py`

**Interfaces:**
- Consumes: la sortie de `recurrence.compute_recurrence` par analyse.
- Produces: `bilan.SHORT_SAMPLE_SECONDS = 30.0`,
  `bilan.project_bilan(workday_hours: float, items: list[dict]) -> dict`. Chaque `item` :
  `{"analysis_id": str, "activity_hours": float, "representative": bool, "recurrence": dict}`.

Sortie :

```python
{
  "workday_hours": float,
  "documented_hours": float,        # somme des activity_hours (toutes analyses du bilan)
  "undocumented_hours": float,      # max(workday_hours - documented_hours, 0)
  "thresholds_calibrated": bool,    # AND des recurrence["thresholds_calibrated"] des analyses prises en compte
  "zones": {"<zone>": {"projected_cycles": float, "projected_elevated_hours": float}},
  "analyses": [{"analysis_id", "activity_hours", "representative", "included": bool,
                "sample_seconds", "warnings": [str], "recurrence": dict}],
  "warnings": [str],
}
```

Règles : seules les analyses `representative=True` alimentent `zones`.
`projected_cycles = sum(cycles_per_minute * 60 * activity_hours)` ; `projected_elevated_hours =
sum(elevated_seconds / sample_seconds * activity_hours)` (0 si `sample_seconds <= 0`). Une analyse
avec `sample_seconds < SHORT_SAMPLE_SECONDS` reçoit un avertissement d'échantillon trop court.
`documented_hours > workday_hours` → `ValueError`.

- [ ] **Step 1: Écrire les tests** : deux analyses (5 h à 3 cycles/min, 3 h à 6 cycles/min) →
  `projected_cycles = 3*60*5 + 6*60*3 = 1980` ; analyse non représentative exclue des sommes mais
  présente dans `analyses` avec `included=False` ; part non documentée (8 h documentées sur 9 →
  `undocumented_hours == 1.0`) ; échantillon de 20 s → avertissement ; somme > journée →
  `ValueError` ; liste vide → zones à zéro et `undocumented_hours == workday_hours`.
- [ ] **Step 2:** Vérifier l'échec.
- [ ] **Step 3:** Implémenter `project_bilan` (module pur, aucune dépendance à DuckDB).
- [ ] **Step 4:** Tests au vert.
- [ ] **Step 5:** Commit `feat: projette la récurrence d'un bilan de poste sur la journée`.

---

### Task 5: Persistance des bilans

**Files:**
- Modify: `src/tms_vision/storage.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Produces, dans `storage.py` :
  - tables `bilans (id VARCHAR PRIMARY KEY, created_at TIMESTAMP NOT NULL, label VARCHAR, workday_hours DOUBLE NOT NULL)`
    et `bilan_analyses (bilan_id VARCHAR NOT NULL REFERENCES bilans(id), analysis_id VARCHAR NOT NULL REFERENCES analyses(id), activity_hours DOUBLE NOT NULL, representative BOOLEAN NOT NULL, PRIMARY KEY (bilan_id, analysis_id))`,
    créées par `_connect()` (même mécanisme que les tables existantes, donc sans migration) ;
  - `create_bilan(*, bilan_id, created_at, label, workday_hours) -> None` ;
  - `attach_analysis(*, bilan_id, analysis_id, activity_hours, representative) -> None`
    (lève `KeyError` si bilan ou analyse inconnus, `ValueError` si l'analyse est déjà rattachée) ;
  - `get_bilan(bilan_id) -> dict | None` (`id`, `created_at` ISO UTC, `label`, `workday_hours`,
    `items`: liste de `{analysis_id, activity_hours, representative}`) ;
  - `list_bilans() -> list[dict]` (même forme, sans `items`, du plus récent au plus ancien).

- [ ] **Step 1:** Tests : création et relecture d'un bilan ; rattachement ; bilan inconnu → `None` ;
  rattachement d'une analyse inconnue → `KeyError` ; doublon → `ValueError` ; `list_bilans` ordonné ;
  les tables sont bien créées par `_connect()` (compléter `test_connect_creates_both_tables`).
- [ ] **Step 2:** Vérifier l'échec.
- [ ] **Step 3:** Implémenter sur le modèle des fonctions existantes (connexion ouverte et fermée
  par fonction, `_to_naive_utc` / `_attach_utc` pour `created_at`).
- [ ] **Step 4:** `python -m pytest tests/test_storage.py` au vert.
- [ ] **Step 5:** Commit `feat: persiste les bilans de poste et leurs analyses`.

---

### Task 6: Endpoints API

**Files:**
- Modify: `src/tms_vision/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces :
  - `POST /bilans` (JSON `{label?: str, workday_hours?: float}`, défaut `9.0`, validation `0 < h <= 24`) → `{id, created_at, label, workday_hours}` ;
  - `GET /bilans` → liste ; `GET /bilans/{id}` → bilan avec `items` (404 si inconnu) ;
  - `POST /bilans/{id}/analyses` (JSON `{analysis_id, activity_hours, representative}`, `activity_hours > 0`) → bilan à jour.
    404 si bilan ou analyse inconnus ; 409 si analyse déjà rattachée ; 422 si la somme des
    `activity_hours` dépasserait `workday_hours` ;
  - `GET /bilans/{id}/recurrence` → sortie de `bilan.project_bilan` (404 si inconnu) ;
  - `GET /analyses/{id}/recurrence` → sortie de `recurrence.compute_recurrence` pour une analyse
    seule (404 si inconnue).

- [ ] **Step 1:** Tests API avec `TestClient` : sauvegarder des analyses de test via
  `storage.save_analysis` (déjà fait par les tests de recommandation, s'en inspirer), puis couvrir
  chaque statut ci-dessus, plus un cas complet : deux analyses rattachées, l'une non représentative,
  vérifier `included`, `undocumented_hours` et les `projected_cycles`.
- [ ] **Step 2:** Vérifier l'échec.
- [ ] **Step 3:** Implémenter les routes. `/bilans/{id}/recurrence` : `storage.get_bilan`, puis pour
  chaque item `storage.get_frame_angles` + `recurrence.compute_recurrence(frames,
  recurrence.load_thresholds())`, puis `bilan.project_bilan`.
- [ ] **Step 4:** `python -m pytest` complet au vert.
- [ ] **Step 5:** Commit `feat: expose les bilans de poste et leur rapport de récurrence`.

---

### Task 7: Page de bilan dans le frontend

**Files:**
- Create: `web/app/bilans/page.tsx` (liste et création)
- Create: `web/app/bilans/[id]/page.tsx` (détail, ajout d'analyses, rapport)
- Create: `web/app/bilans/RecurrenceReport.tsx`
- Modify: `web/app/page.tsx` ou le lien de navigation existant vers `/historique` pour ajouter un
  lien « Bilans de poste » (suivre le pattern `next/link` déjà utilisé, voir le README sur
  l'exception `next/link`)
- Test: `web/app/bilans/recurrenceFormat.test.ts` si une fonction de formatage pure est extraite

**Contenu :**
- `/bilans` : liste (`GET /bilans`) et formulaire de création (libellé, durée de journée en
  heures, défaut 9).
- `/bilans/[id]` : liste des analyses rattachées ; formulaire d'ajout (sélecteur parmi
  `GET /analyses`, durée d'activité en heures, case « Cette séquence est représentative de cette
  activité ») ; affichage des erreurs 409 / 422 renvoyées par l'API.
- `RecurrenceReport` : tableau par zone (cycles projetés, heures projetées en niveau élevé), part
  non documentée, bandeau « Estimation basée sur des échantillons de X min au total » ; badge
  « seuils non calibrés » quand `thresholds_calibrated` est faux ; analyses non confirmées listées
  avec leurs chiffres bruts et une mention « exclue de la projection » ; avertissements d'échantillon
  court.
- Conventions : même gestion d'état et d'annulation que `historique/page.tsx`
  (`cancelled` dans les effets, état réinitialisé sur erreur réseau), `API_URL` via
  `process.env.NEXT_PUBLIC_API_URL`, contraste conforme à `scoreBadge.ts`.

- [ ] **Step 1:** Lire `web/AGENTS.md` et le guide Next.js correspondant dans
  `web/node_modules/next/dist/docs/` (routes dynamiques, composants client).
- [ ] **Step 2:** Extraire dans un module pur les fonctions de formatage (heures, nombre de cycles,
  texte « X min au total ») et les tester avec Vitest.
- [ ] **Step 3:** Écrire les pages et le composant.
- [ ] **Step 4:** `cd web && npm test && npm run lint && npx tsc --noEmit` au vert.
- [ ] **Step 5:** Vérification manuelle dans un navigateur : démarrer l'API et le frontend, créer
  un bilan, y rattacher deux analyses (une confirmée, une non), vérifier que la projection n'inclut
  que la première et que le badge « seuils non calibrés » s'affiche. Consigner le résultat.
- [ ] **Step 6:** Commit `feat: ajoute la page de bilan de poste et le rapport de récurrence`.

---

### Task 8: Documentation et vérification finale

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md` (statut)

- [ ] **Step 1:** Ajouter dans `README.md` une section « Bilan de poste et récurrence » : concept,
  endpoints, fichier `recurrence_thresholds.json` et sa règle (valeurs `null` tant que la
  calibration n'est pas faite), lien vers la spec et le plan, et dans la liste des documents de
  référence de la section 8.
- [ ] **Step 2:** Mettre le statut de la spec à « Tranche 1 livrée ».
- [ ] **Step 3:** `python -m pytest` et `cd web && npm test && npm run lint` : tout au vert.
- [ ] **Step 4:** Commit `docs: documente le bilan de poste et la récurrence`.

---

## Hors périmètre de cette tranche

- Poids en fourchette, recalcul de score, programme de 2 à 3 capsules (Tranche 2).
- Génération des vidéos d'étirement et fournisseurs IA (Tranche 3).
- Correction du geste (Partie D, structure prévue en Tranche 2).
- Calibration des seuils de cycles avec l'ostéopathe : le fichier de configuration attend ses
  valeurs. Les 10° et 15° de départ sont ceux du PoC, provisoires (`calibrated: false`) ; les
  seuils d'interprétation restent vides.
