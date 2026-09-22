# Recommandation de capsules par zone — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recommander automatiquement, une fois une analyse RULA terminée, la capsule
d'étirement correspondant à la zone anatomique la plus dégradée (post-analyse, pas de temps réel).

**Architecture:** Un nouveau module pur `src/tms_vision/capsules.py` calcule la zone la plus
dégradée à partir des lignes de frame d'une analyse et sélectionne la capsule correspondante dans
un catalogue statique. `storage.py` gagne une seule fonction de lecture pour fournir ces lignes.
`api.py` expose le tout via `GET /analyses/{id}/recommendation`, affiché sur la page de résultat
existante.

**Tech Stack:** Python 3.11 (backend), Next.js/TypeScript (frontend), pytest, DuckDB (déjà en place).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-22-capsule-zone-recommendation-design.md`.
- 4 zones seulement : `neck`, `trunk`, `upper_arm`, `lower_arm` — pas de zone poignets/mains ni
  hanches.
- Niveaux "dégradés" = exactement `investigation_et_changement_bientot` et `changement_immediat`
  (pas `investigation_recommandee`).
- Égalité stricte entre zones → ordre de priorité fixe `trunk > neck > upper_arm > lower_arm`.
- Aucune zone dégradée → `zone: null`, `capsule: null` (pas de recommandation forcée).
- Une seule capsule recommandée (pas une liste).
- Catalogue de capsules statique en Python (`src/tms_vision/capsules.py`), pas de table DuckDB,
  contenu placeholder (pas de vraies vidéos).
- `storage.py` reste une couche de persistance pure — aucune logique de zone n'y vit.

---

### Task 1: `capsules.py` — catalogue et calcul de zone dégradée

**Files:**
- Create: `src/tms_vision/capsules.py`
- Test: `tests/test_capsules.py`

**Interfaces:**
- Produces: `capsules.Capsule` (dataclass : `zone: str`, `title: str`, `description: str`,
  `video_url: str`), `capsules.CAPSULES: list[Capsule]`, `capsules.ZONES: list[str]` (`["neck",
  "trunk", "upper_arm", "lower_arm"]`), `capsules.compute_worst_zone(frames: list[dict]) -> str |
  None` (chaque dict a les clés `frame_index`, `timestamp_seconds`,
  `neck_segment_action_level`, `trunk_segment_action_level`, `upper_arm_segment_action_level`,
  `lower_arm_segment_action_level` — même forme que ce que `storage.get_frame_segments` produira à
  la Task 2), `capsules.recommend_capsule(zone: str | None) -> Capsule | None`.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/test_capsules.py` :

```python
from tms_vision.capsules import CAPSULES, ZONES, compute_worst_zone, recommend_capsule


def _frame(frame_index, timestamp_seconds, **levels):
    row = {
        "frame_index": frame_index,
        "timestamp_seconds": timestamp_seconds,
        "neck_segment_action_level": None,
        "trunk_segment_action_level": None,
        "upper_arm_segment_action_level": None,
        "lower_arm_segment_action_level": None,
    }
    for zone, level in levels.items():
        row[f"{zone}_segment_action_level"] = level
    return row


def test_compute_worst_zone_picks_zone_with_most_cumulative_time_in_elevated_levels():
    frames = [
        _frame(0, 0.0, trunk="changement_immediat", neck="acceptable"),
        _frame(1, 1.0, trunk="changement_immediat", neck="acceptable"),
        _frame(2, 2.0, trunk="acceptable", neck="investigation_et_changement_bientot"),
        _frame(3, 3.0, trunk="acceptable", neck="acceptable"),
    ]
    # trunk dégradé sur [0,1] -> 2.0s cumulées ; neck dégradé sur [2,3) -> 1.0s cumulée.
    assert compute_worst_zone(frames) == "trunk"


def test_compute_worst_zone_returns_none_when_nothing_is_degraded():
    frames = [
        _frame(0, 0.0, trunk="acceptable", neck="investigation_recommandee"),
        _frame(1, 1.0, trunk="acceptable", neck="acceptable"),
    ]
    # investigation_recommandee ne compte pas comme "dégradé".
    assert compute_worst_zone(frames) is None


def test_compute_worst_zone_breaks_exact_ties_by_fixed_priority_order():
    frames = [
        _frame(
            0, 0.0,
            trunk="changement_immediat", neck="changement_immediat",
            upper_arm="changement_immediat", lower_arm="changement_immediat",
        ),
        _frame(1, 1.0),
    ]
    # Les 4 zones cumulent exactement 1.0s chacune -> égalité stricte, trunk gagne (priorité).
    assert compute_worst_zone(frames) == "trunk"


def test_compute_worst_zone_ignores_undetected_frames_for_cumulation_but_uses_their_timestamp():
    frames = [
        _frame(0, 0.0, trunk="changement_immediat"),
        _frame(1, 1.0),  # non détectée : tous les niveaux à None
        _frame(2, 5.0, trunk="acceptable"),
    ]
    # trunk dégradé seulement sur la frame 0, durée jusqu'à la frame 1 (non détectée) = 1.0s.
    assert compute_worst_zone(frames) == "trunk"


def test_compute_worst_zone_handles_empty_frame_list():
    assert compute_worst_zone([]) is None


def test_recommend_capsule_returns_first_catalog_entry_for_the_zone():
    capsule = recommend_capsule("neck")
    assert capsule is not None
    assert capsule.zone == "neck"
    assert capsule == next(c for c in CAPSULES if c.zone == "neck")


def test_recommend_capsule_returns_none_for_none_zone():
    assert recommend_capsule(None) is None


def test_catalog_has_at_least_one_capsule_per_measured_zone():
    catalog_zones = {c.zone for c in CAPSULES}
    assert set(ZONES) <= catalog_zones
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_capsules.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'tms_vision.capsules'`

- [ ] **Step 3: Créer `capsules.py`**

```python
"""Sélection de la capsule d'étirement recommandée en fonction de la zone
RULA la plus dégradée d'une analyse terminée (voir
docs/superpowers/specs/2026-09-22-capsule-zone-recommendation-design.md).
Module pur, sans dépendance à DuckDB : il calcule uniquement à partir des
lignes de frame que storage.get_frame_segments() a déjà lues."""
from dataclasses import dataclass

ZONES = ["neck", "trunk", "upper_arm", "lower_arm"]
ZONE_PRIORITY = ["trunk", "neck", "upper_arm", "lower_arm"]
ELEVATED_LEVELS = {"investigation_et_changement_bientot", "changement_immediat"}


@dataclass
class Capsule:
    zone: str
    title: str
    description: str
    video_url: str


CAPSULES: list[Capsule] = [
    Capsule(
        zone="neck",
        title="Étirements cervicaux",
        description=(
            "3 étirements pour décompresser les cervicales après une posture tête baissée "
            "prolongée."
        ),
        video_url="https://example.com/capsules/neck-stretch.mp4",
    ),
    Capsule(
        zone="trunk",
        title="Mobilisation lombaire",
        description=(
            "Exercices doux de mobilisation du bas du dos après une posture penchée en avant."
        ),
        video_url="https://example.com/capsules/trunk-mobility.mp4",
    ),
    Capsule(
        zone="upper_arm",
        title="Étirement des épaules",
        description=(
            "Étirement des épaules après un travail prolongé bras levés ou écartés du corps."
        ),
        video_url="https://example.com/capsules/shoulder-stretch.mp4",
    ),
    Capsule(
        zone="lower_arm",
        title="Étirement de l'avant-bras et du coude",
        description=(
            "Étirement de l'avant-bras après une flexion répétée ou prolongée du coude."
        ),
        video_url="https://example.com/capsules/forearm-stretch.mp4",
    ),
]


def _segment_column(zone: str) -> str:
    return f"{zone}_segment_action_level"


def compute_worst_zone(frames: list[dict]) -> str | None:
    cumulative_seconds = {zone: 0.0 for zone in ZONES}

    for index, frame in enumerate(frames):
        if index + 1 < len(frames):
            next_timestamp = frames[index + 1]["timestamp_seconds"]
        else:
            next_timestamp = None

        if next_timestamp is None:
            duration = 1.0 if len(frames) == 1 else 0.0
        else:
            duration = max(next_timestamp - frame["timestamp_seconds"], 0.0) or (
                1.0 if len(frames) == 1 else 0.0
            )

        for zone in ZONES:
            if frame[_segment_column(zone)] in ELEVATED_LEVELS:
                cumulative_seconds[zone] += duration

    best_zone = None
    best_seconds = 0.0
    for zone in ZONE_PRIORITY:
        seconds = cumulative_seconds[zone]
        if seconds > best_seconds:
            best_zone = zone
            best_seconds = seconds

    return best_zone


def recommend_capsule(zone: str | None) -> Capsule | None:
    if zone is None:
        return None
    for capsule in CAPSULES:
        if capsule.zone == zone:
            return capsule
    return None
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_capsules.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/capsules.py tests/test_capsules.py
git commit -m "feat: catalogue de capsules et calcul de la zone RULA la plus dégradée"
```

---

### Task 2: `storage.py` — `get_frame_segments`

**Files:**
- Modify: `src/tms_vision/storage.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Consumes: `storage._connect()`, `storage.SEGMENT_COLUMNS` (déjà présents dans le fichier).
- Produces: `storage.get_frame_segments(analysis_id: str) -> list[dict] | None` — `None` si
  `analysis_id` inconnu, sinon une liste ordonnée par `frame_index`, chaque dict ayant les clés
  `frame_index`, `timestamp_seconds`, `neck_segment_action_level`, `trunk_segment_action_level`,
  `upper_arm_segment_action_level`, `lower_arm_segment_action_level` — exactement la forme
  attendue par `capsules.compute_worst_zone` (Task 1).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `tests/test_storage.py` (le fichier importe déjà `storage`, `datetime`, `timezone` —
réutiliser le helper `_frame_row` déjà présent dans ce fichier si possible, sinon construire les
lignes directement comme ci-dessous) :

```python
def test_get_frame_segments_returns_ordered_rows_with_segment_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    summary = {
        "frame_count": 2, "detected_frame_count": 2, "max_score": 1,
        "average_score": 1.0, "time_by_action_level": {"acceptable": 2.0},
    }
    row0 = _frame_row(frame_index=0, timestamp_seconds=0.0)
    row0["neck_segment_action_level"] = "acceptable"
    row0["trunk_segment_action_level"] = "changement_immediat"
    row0["upper_arm_segment_action_level"] = "acceptable"
    row0["lower_arm_segment_action_level"] = "acceptable"
    row1 = _frame_row(frame_index=1, timestamp_seconds=1.0)
    row1["neck_segment_action_level"] = "investigation_recommandee"
    row1["trunk_segment_action_level"] = "acceptable"
    row1["upper_arm_segment_action_level"] = "acceptable"
    row1["lower_arm_segment_action_level"] = "acceptable"

    storage.save_analysis(
        analysis_id="seg-1", created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=[row0, row1],
    )

    frames = storage.get_frame_segments("seg-1")

    assert frames is not None
    assert len(frames) == 2
    assert frames[0]["frame_index"] == 0
    assert frames[0]["timestamp_seconds"] == 0.0
    assert frames[0]["trunk_segment_action_level"] == "changement_immediat"
    assert frames[1]["frame_index"] == 1
    assert frames[1]["neck_segment_action_level"] == "investigation_recommandee"


def test_get_frame_segments_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")
    assert storage.get_frame_segments("does-not-exist") is None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL avec `AttributeError: module 'tms_vision.storage' has no attribute
'get_frame_segments'`

- [ ] **Step 3: Implémenter `get_frame_segments`**

Ajouter à `src/tms_vision/storage.py` (après `frames_csv_text`) :

```python
def get_frame_segments(analysis_id: str) -> list[dict] | None:
    conn = _connect()
    try:
        exists = conn.execute(
            "SELECT 1 FROM analyses WHERE id = ?", [analysis_id]
        ).fetchone()
        if exists is None:
            return None
        columns = ["frame_index", "timestamp_seconds"] + SEGMENT_COLUMNS
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM analysis_frames "
            "WHERE analysis_id = ? ORDER BY frame_index",
            [analysis_id],
        ).fetchall()
    finally:
        conn.close()

    return [dict(zip(columns, row)) for row in rows]
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (tous les tests, y compris les 2 nouveaux)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/storage.py tests/test_storage.py
git commit -m "feat: get_frame_segments dans storage.py"
```

---

### Task 3: `api.py` — `GET /analyses/{id}/recommendation`

**Files:**
- Modify: `src/tms_vision/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `storage.get_frame_segments(analysis_id)` (Task 2), `capsules.Capsule`,
  `capsules.compute_worst_zone(frames)`, `capsules.recommend_capsule(zone)` (Task 1).
- Produces: `GET /analyses/{analysis_id}/recommendation` → 200 avec
  `{"zone": str | null, "capsule": {"zone", "title", "description", "video_url"} | null}` ; 404 si
  `analysis_id` inconnu.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `tests/test_api.py` (le fichier importe déjà `storage`, `TestClient`, `app`,
`_write_synthetic_video`, `_patch_db`) :

```python
def test_get_recommendation_returns_404_for_unknown_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.get("/analyses/does-not-exist/recommendation")
    assert response.status_code == 404


def test_get_recommendation_returns_null_zone_when_nothing_is_degraded(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        create_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    analysis_id = create_response.json()["analysis_id"]

    # Vidéo synthétique noire : aucune pose détectée -> aucun segment_action_level
    # jamais non-null -> aucune zone ne peut être dégradée.
    response = client.get(f"/analyses/{analysis_id}/recommendation")

    assert response.status_code == 200
    body = response.json()
    assert body["zone"] is None
    assert body["capsule"] is None


def test_get_recommendation_returns_worst_zone_and_matching_capsule(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)

    summary = {
        "frame_count": 1, "detected_frame_count": 1, "max_score": 7,
        "average_score": 7.0, "time_by_action_level": {"changement_immediat": 1.0},
    }
    row = {field: None for field in storage.CSV_FIELDS}
    row.update(frame_index=0, timestamp_seconds=0.0, detected=True)
    row["neck_segment_action_level"] = "acceptable"
    row["trunk_segment_action_level"] = "changement_immediat"
    row["upper_arm_segment_action_level"] = "acceptable"
    row["lower_arm_segment_action_level"] = "acceptable"
    storage.save_analysis(
        analysis_id="rec-1", created_at=datetime.now(timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=[row],
    )

    client = TestClient(app)
    response = client.get("/analyses/rec-1/recommendation")

    assert response.status_code == 200
    body = response.json()
    assert body["zone"] == "trunk"
    assert body["capsule"]["zone"] == "trunk"
    assert body["capsule"]["title"]
    assert body["capsule"]["video_url"]
```

Ajouter en tête de `tests/test_api.py` les imports manquants pour ce test (`storage.CSV_FIELDS`
est déjà accessible via l'import `from tms_vision import storage` existant ; ajouter seulement
`from datetime import datetime, timezone` si absent du fichier).

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pytest tests/test_api.py -v -k recommendation`
Expected: FAIL avec `404` inattendu sur les deux premiers tests (route inexistante -> FastAPI
renvoie 404 par défaut sur une route non déclarée, donc le premier test passe accidentellement
mais pas pour la bonne raison -- le deuxième et le troisième échouent clairement, confirmant que
la route n'existe pas encore)

- [ ] **Step 3: Implémenter la route**

Modifier `src/tms_vision/api.py` : ajouter l'import (dans le bloc d'imports en tête de fichier,
après `from tms_vision.pose3d_export import build_pose3d_payload`) :

```python
from tms_vision.capsules import Capsule, compute_worst_zone, recommend_capsule
```

Ajouter la route à la fin du fichier (après `get_analysis_frames_csv`) :

```python
def _capsule_to_dict(capsule: Capsule) -> dict:
    return {
        "zone": capsule.zone,
        "title": capsule.title,
        "description": capsule.description,
        "video_url": capsule.video_url,
    }


@app.get("/analyses/{analysis_id}/recommendation")
async def get_analysis_recommendation(analysis_id: str) -> dict:
    frames = storage.get_frame_segments(analysis_id)
    if frames is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")

    zone = compute_worst_zone(frames)
    capsule = recommend_capsule(zone)
    return {"zone": zone, "capsule": _capsule_to_dict(capsule) if capsule is not None else None}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pytest tests/test_api.py -v -k recommendation`
Expected: PASS (3 tests)

- [ ] **Step 5: Lancer toute la suite Python pour vérifier l'absence de régression**

Run: `pytest -q`
Expected: PASS (tous les tests)

- [ ] **Step 6: Commit**

```bash
git add src/tms_vision/api.py tests/test_api.py
git commit -m "feat: route GET /analyses/{id}/recommendation"
```

---

### Task 4: Frontend — affichage de la recommandation

**Files:**
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: `GET /analyses/{analysis_id}/recommendation` (Task 3) — réponse
  `{zone: string | null, capsule: {zone, title, description, video_url} | null}`.
- `AnalysisResponse` (type existant dans `page.tsx`) gagne le champ `analysis_id: string` — déjà
  renvoyé par l'API depuis le sprint précédent (`api.py`), mais jamais ajouté au type TypeScript
  jusqu'ici (nécessaire pour construire l'URL de la nouvelle route).

- [ ] **Step 1: Ajouter `analysis_id` au type `AnalysisResponse` et les nouveaux types**

Dans `web/app/page.tsx`, remplacer :

```typescript
type AnalysisResponse = {
  summary: AnalysisSummary;
  annotated_video_url: string;
  csv_url: string;
  pose3d_url: string;
  side: Side;
};
```

par :

```typescript
type AnalysisResponse = {
  analysis_id: string;
  summary: AnalysisSummary;
  annotated_video_url: string;
  csv_url: string;
  pose3d_url: string;
  side: Side;
};

type Capsule = {
  zone: string;
  title: string;
  description: string;
  video_url: string;
};

type Recommendation = {
  zone: string | null;
  capsule: Capsule | null;
};

const ZONE_LABELS: Record<string, string> = {
  neck: "cou",
  trunk: "tronc",
  upper_arm: "bras",
  lower_arm: "avant-bras",
};
```

- [ ] **Step 2: Ajouter l'état et l'effet de récupération de la recommandation**

Dans le composant `Home`, juste après la déclaration de `const [result, setResult] =
useState<AnalysisResponse | null>(null);` (ligne existante), ajouter :

```typescript
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
```

Juste après le `useEffect` existant qui nettoie le flux caméra au démontage (celui avec
`streamRef.current?.getTracks()...`), ajouter un nouveau `useEffect` :

```typescript
  useEffect(() => {
    if (!result) {
      setRecommendation(null);
      return;
    }
    let cancelled = false;
    fetch(`${API_URL}/analyses/${result.analysis_id}/recommendation`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<Recommendation>;
      })
      .then((data) => {
        if (!cancelled) setRecommendation(data);
      })
      .catch(() => {
        if (!cancelled) setRecommendation(null);
      });
    return () => {
      cancelled = true;
    };
  }, [result]);
```

- [ ] **Step 3: Afficher la recommandation dans la section résultat**

Dans le JSX, juste après le lien `<a href={...}>Télécharger le CSV détaillé</a>` et avant la
fermeture `</section>` de la section résultat, ajouter :

```tsx
          {recommendation?.capsule && (
            <div className="rounded border border-blue-200 bg-blue-50 p-3">
              <p className="text-sm font-semibold">
                Recommandation : zone{" "}
                {ZONE_LABELS[recommendation.zone ?? ""] ?? recommendation.zone}
              </p>
              <p className="font-medium">{recommendation.capsule.title}</p>
              <p className="text-sm text-gray-700">{recommendation.capsule.description}</p>
            </div>
          )}
```

- [ ] **Step 4: Vérifier les types**

Run: `cd web && npx tsc --noEmit`
Expected: aucune erreur

- [ ] **Step 5: Vérifier le build**

Run: `cd web && npm run build`
Expected: build réussi, aucune erreur

- [ ] **Step 6: Vérification manuelle dans un vrai navigateur (Playwright)**

Cette étape suit la discipline de vérification déjà établie pour les tranches précédentes de
`web/` (voir les entrées "Vérifié manuellement" du README) : un changement d'interface se
vérifie en le faisant réellement tourner, pas seulement en le compilant.

1. Démarrer l'API : `cd "/Users/garinat_t/Desktop/TMS vision" && source venv/bin/activate &&
   uvicorn tms_vision.api:app --reload` (dans un terminal séparé, ou en arrière-plan).
2. Démarrer le frontend : `cd web && npm run dev` (dans un autre terminal, ou en arrière-plan).
3. Avec Playwright (MCP déjà disponible dans cette session) : naviguer vers
   `http://localhost:3000`, importer `samples/synthetic_smoke_test.mp4` (vidéo sans personne
   détectée, déjà utilisée par les tests existants) via le flux d'import de fichier existant,
   lancer l'analyse.
   - Vérifier qu'aucun bloc "Recommandation" ne s'affiche (zone `null` attendue sur cette vidéo,
     cf. Task 3 test `test_get_recommendation_returns_null_zone_when_nothing_is_degraded`) et
     qu'aucune erreur console n'apparaît.
4. Toujours avec Playwright, intercepter la requête réseau vers
   `/analyses/*/recommendation` (`page.route` ou équivalent) pour lui faire renvoyer une réponse
   fabriquée `{"zone": "trunk", "capsule": {"zone": "trunk", "title": "Mobilisation lombaire",
   "description": "...", "video_url": "..."}}`, relancer/rafraîchir l'affichage du résultat, et
   prendre une capture d'écran confirmant que le bloc "Recommandation" s'affiche correctement
   (zone en français, titre, description) sans erreur console. Cela vérifie visuellement le rendu
   du chemin positif sans dépendre d'une vraie vidéo de posture dégradée.

- [ ] **Step 7: Commit**

```bash
git add web/app/page.tsx
git commit -m "feat: affiche la recommandation de capsule sur la page de résultat"
```

---

## Self-Review

**Couverture de la spec** : catalogue placeholder + 4 zones (Task 1), calcul par temps cumulé en
niveaux élevés avec départage par priorité (Task 1), lecture des frames (Task 2), endpoint API
avec 404 (Task 3), affichage frontend (Task 4), hors périmètre (vraies vidéos, admin UI, historique,
temps réel, zones non mesurées, plusieurs capsules) — non implémenté, conforme à la spec. Tout
couvert.

**Scan de placeholders** : aucun "TBD"/"TODO" ; chaque étape contient du code complet.

**Cohérence des types/signatures** : `compute_worst_zone(frames: list[dict]) -> str | None` (Task
1) reçoit exactement la forme produite par `storage.get_frame_segments` (Task 2) — mêmes clés
vérifiées dans les deux tâches (`frame_index`, `timestamp_seconds`, les 4
`*_segment_action_level`). `recommend_capsule(zone: str | None) -> Capsule | None` (Task 1) utilisé
identiquement dans Task 3. `Capsule` (dataclass, Task 1) sérialisé par `_capsule_to_dict` (Task 3)
avec exactement les 4 champs attendus par le type `Capsule` TypeScript (Task 4). `analysis_id`
déjà renvoyé par l'API depuis le sprint précédent, seulement absent du type frontend — corrigé en
Task 4 sans toucher au backend.
