# Upload de fichier vidéo par chunks (Phase 2, tranche 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre d'importer un fichier vidéo déjà enregistré (en alternative à la capture caméra live), envoyé par chunks de 5 Mo pour rester sous les limites de taille de requête réseau, puis analysé par le pipeline RULA existant sans aucune modification.

**Architecture:** Trois nouveaux endpoints FastAPI (`POST /uploads`, `PUT /uploads/{id}/chunks/{index}`, `POST /uploads/{id}/complete`) gèrent une session d'upload dont l'état vit entièrement sur le système de fichiers (`outputs/.uploads/{upload_id}/`, un `meta.json` + des fichiers `chunk_NNNNNN`) — pas de dict en mémoire, pas de DB. `complete` réassemble les chunks dans l'ordre de leur index (pas de leur ordre d'arrivée), puis appelle `analyze_video()` exactement comme `/analyses` le fait aujourd'hui, via un helper partagé. Côté navigateur, la page Next.js gagne un second mode (« Importer une vidéo ») qui découpe le `File` sélectionné en tranches de 5 Mo et les envoie séquentiellement, avec retry par chunk.

**Tech Stack:** Python 3.11 (venv dédié), FastAPI, pytest, httpx (TestClient) ; Next.js 16 (App Router, TypeScript), React, `fetch`/`FormData`/`File.slice()`.

## Global Constraints

- Python 3.11 dans le venv dédié du projet — toute commande Python passe par `venv/bin/python`, `venv/bin/pytest`.
- Chunks de 5 Mo (`5 * 1024 * 1024` octets), envoi **séquentiel** (pas parallèle) — objectif : rester sous les limites de taille de requête réseau, pas la vitesse.
- Retry par chunk (3 tentatives) côté navigateur — pas de reprise de session après fermeture de l'onglet ou perte totale de connexion (hors périmètre).
- État de session d'upload **sur le système de fichiers uniquement** (`meta.json` + fichiers `chunk_NNNNNN`) — pas de dict en mémoire, pas de DB. Doit survivre à un redémarrage d'`uvicorn --reload`.
- `analyze_video()` (`src/tms_vision/pipeline.py`) reste inchangé — aucune modification du pipeline Phase 1.
- Le chemin caméra existant (`POST /analyses`) n'est pas modifié dans son comportement observable (une extraction de helper interne est autorisée si tous les tests existants continuent de passer).
- `pytest.ini` fixe `pythonpath = src` et `testpaths = tests` : `venv/bin/pytest` s'exécute depuis la racine du projet (`~/Desktop/TMS vision`).
- Tout se développe directement sur `main`, pas de branche ni de worktree (cohérent avec la tranche 1).
- Hors périmètre (ne pas implémenter) : reprise après fermeture du navigateur, upload parallèle, nettoyage automatique des sessions abandonnées, limite de taille totale côté serveur, authentification.
- Spec de référence : `docs/superpowers/specs/2026-09-15-web-upload-chunked-design.md`.

---

## Task 1: Démarrer une session d'upload (`POST /uploads`)

**Files:**
- Modify: `src/tms_vision/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `OUTPUT_DIR` (module global déjà existant dans `api.py`, lu à chaque requête — jamais mis en cache dans une constante au niveau module, pour rester compatible avec le `monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)` déjà utilisé par tous les tests existants).
- Produces: endpoint `POST /uploads` (form fields `filename: str`, `total_chunks: int`) → `{"upload_id": str}`. Layout disque : `OUTPUT_DIR/.uploads/{upload_id}/meta.json` contenant `{"filename": <str>, "total_chunks": <int>}`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/test_api.py` :

```python
def test_start_upload_creates_session_with_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/uploads",
        data={"filename": "clip.mp4", "total_chunks": "3"},
    )

    assert response.status_code == 200
    upload_id = response.json()["upload_id"]
    meta_path = tmp_path / ".uploads" / upload_id / "meta.json"
    assert meta_path.is_file()
    assert json.loads(meta_path.read_text()) == {"filename": "clip.mp4", "total_chunks": 3}


def test_start_upload_rejects_zero_total_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/uploads",
        data={"filename": "clip.mp4", "total_chunks": "0"},
    )

    assert response.status_code == 422
```

Cette suite utilise `json`, qui n'est pas encore importé dans `tests/test_api.py`. Ajouter en toute
première ligne du fichier :

```python
import json
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `venv/bin/pytest tests/test_api.py -k test_start_upload -v`
Expected: FAIL — `404 Not Found` (la route `/uploads` n'existe pas encore).

- [ ] **Step 3: Implémenter l'endpoint**

Dans `src/tms_vision/api.py`, ajouter `import uuid` avec les autres imports du haut de fichier
(après `import tempfile`) :

```python
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Literal
```

Puis ajouter le nouvel endpoint juste après `get_output_file` et avant `create_analysis` :

```python
@app.post("/uploads")
async def start_upload(
    filename: str = Form(...),
    total_chunks: int = Form(..., ge=1),
) -> dict:
    """Démarre une session d'upload par chunks. L'état de la session vit
    entièrement sur le système de fichiers (meta.json + fichiers chunk_NNNNNN
    écrits par upload_chunk/complete_upload) : pas de dict en mémoire, pour
    survivre à un redémarrage d'uvicorn --reload en cours d'upload."""
    upload_id = uuid.uuid4().hex
    session_dir = OUTPUT_DIR / ".uploads" / upload_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"filename": filename, "total_chunks": total_chunks})
    )
    return {"upload_id": upload_id}
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `venv/bin/pytest tests/test_api.py -k test_start_upload -v`
Expected: `2 passed`

- [ ] **Step 5: Lancer toute la suite pour vérifier l'absence de régression**

Run: `venv/bin/pytest -v`
Expected: tous les tests passent (les tests existants de `test_api.py` sur `/analyses` et
`/outputs` ne sont pas concernés par ce changement).

- [ ] **Step 6: Commit**

```bash
git add src/tms_vision/api.py tests/test_api.py
git commit -m "feat: endpoint POST /uploads pour démarrer une session d'upload par chunks"
```

---

## Task 2: Recevoir un chunk (`PUT /uploads/{upload_id}/chunks/{index}`)

**Files:**
- Modify: `src/tms_vision/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: layout de session créé par Task 1 (`OUTPUT_DIR/.uploads/{upload_id}/meta.json`
  contenant `total_chunks`).
- Produces: endpoint `PUT /uploads/{upload_id}/chunks/{index}` (multipart, champ `file`) → écrit
  `OUTPUT_DIR/.uploads/{upload_id}/chunk_{index:06d}` ; 404 si la session n'existe pas, 400 si
  `index` est hors de `[0, total_chunks)`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_api.py` :

```python
def test_upload_chunk_writes_chunk_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 200
    chunk_path = tmp_path / ".uploads" / upload_id / "chunk_000000"
    assert chunk_path.read_bytes() == b"hello"


def test_upload_chunk_rejects_unknown_upload_id(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.put(
        "/uploads/does-not-exist/chunks/0",
        files={"file": ("chunk-0", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 404


def test_upload_chunk_rejects_out_of_range_index(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/5",
        files={"file": ("chunk-5", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 400
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `venv/bin/pytest tests/test_api.py -k test_upload_chunk -v`
Expected: FAIL — `404 Not Found` (la route `/uploads/{upload_id}/chunks/{index}` n'existe pas
encore, y compris pour le premier test qui attend un 200).

- [ ] **Step 3: Implémenter l'endpoint**

Ajouter dans `src/tms_vision/api.py`, juste après `start_upload` :

```python
@app.put("/uploads/{upload_id}/chunks/{index}")
async def upload_chunk(upload_id: str, index: int, file: UploadFile = File(...)) -> dict:
    session_dir = OUTPUT_DIR / ".uploads" / upload_id
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Session d'envoi introuvable.")

    total_chunks = json.loads(meta_path.read_text())["total_chunks"]
    if not 0 <= index < total_chunks:
        raise HTTPException(status_code=400, detail="Index de morceau hors limites.")

    chunk_path = session_dir / f"chunk_{index:06d}"
    with open(chunk_path, "wb") as chunk_file:
        shutil.copyfileobj(file.file, chunk_file)

    return {"received": index}
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `venv/bin/pytest tests/test_api.py -k test_upload_chunk -v`
Expected: `3 passed`

- [ ] **Step 5: Lancer toute la suite**

Run: `venv/bin/pytest -v`
Expected: tous les tests passent.

- [ ] **Step 6: Commit**

```bash
git add src/tms_vision/api.py tests/test_api.py
git commit -m "feat: endpoint PUT /uploads/{id}/chunks/{index} pour recevoir un chunk"
```

---

## Task 3: Finaliser l'upload et lancer l'analyse (`POST /uploads/{upload_id}/complete`)

**Files:**
- Modify: `src/tms_vision/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: layout de session des Tasks 1-2 (`meta.json`, fichiers `chunk_NNNNNN`) ;
  `tms_vision.pipeline.analyze_video(source, side, load_kg, wrist_twist, output_dir) ->
  AnalysisResult` (inchangé, déjà utilisé par `create_analysis`).
- Produces: endpoint `POST /uploads/{upload_id}/complete` (form fields `side`, `load_kg`,
  `wrist_twist`) → même forme de réponse JSON que `POST /analyses`
  (`{"summary": ..., "annotated_video_url": ..., "csv_url": ...}`) ; helper interne
  `_analyze_and_build_response(video_path: Path, side: str, load_kg: float, wrist_twist: str) ->
  dict`, extrait de `create_analysis` et réutilisé par les deux endpoints.

Cette tâche refactore `create_analysis` (extraction d'un helper partagé) : les tests existants de
`test_api.py` sur `/analyses` doivent continuer de passer sans modification — c'est la garde-fou
de non-régression de cette étape.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_api.py` :

```python
def test_upload_chunks_then_complete_matches_direct_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)
    video_bytes = video_path.read_bytes()
    midpoint = len(video_bytes) // 2
    chunks = [video_bytes[:midpoint], video_bytes[midpoint:]]

    client = TestClient(app)
    start_response = client.post(
        "/uploads", data={"filename": "synthetic.mp4", "total_chunks": str(len(chunks))}
    )
    upload_id = start_response.json()["upload_id"]

    for index, chunk in enumerate(chunks):
        chunk_response = client.put(
            f"/uploads/{upload_id}/chunks/{index}",
            files={"file": (f"chunk-{index}", chunk, "application/octet-stream")},
        )
        assert chunk_response.status_code == 200

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["detected_frame_count"] == 0
    assert body["summary"]["max_score"] == 0
    assert body["annotated_video_url"].startswith("/outputs/")
    assert body["csv_url"].startswith("/outputs/")

    # La session est nettoyée après complétion, réussie ou pas.
    assert not (tmp_path / ".uploads" / upload_id).exists()


def test_chunks_reassembled_by_index_regardless_of_arrival_order(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)
    video_bytes = video_path.read_bytes()
    midpoint = len(video_bytes) // 2
    chunks = [video_bytes[:midpoint], video_bytes[midpoint:]]

    client = TestClient(app)
    start_response = client.post(
        "/uploads", data={"filename": "synthetic.mp4", "total_chunks": "2"}
    )
    upload_id = start_response.json()["upload_id"]

    # Chunk 1 envoyé avant chunk 0 : l'ordre d'arrivée est inversé par rapport
    # à l'ordre d'index. La réassemblage doit suivre l'index, pas l'arrivée.
    client.put(
        f"/uploads/{upload_id}/chunks/1",
        files={"file": ("chunk-1", chunks[1], "application/octet-stream")},
    )
    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", chunks[0], "application/octet-stream")},
    )

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["frame_count"] == 3


def test_complete_upload_fails_when_chunk_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    # Seul le chunk 0 est envoyé ; le chunk 1 manque.
    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"data", "application/octet-stream")},
    )

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 422


def test_complete_upload_rejects_unknown_upload_id(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/uploads/does-not-exist/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 404
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

Run: `venv/bin/pytest tests/test_api.py -k "complete or reassembled" -v`
Expected: FAIL — `404 Not Found` (la route `/uploads/{upload_id}/complete` n'existe pas encore).

- [ ] **Step 3: Extraire le helper partagé et implémenter l'endpoint**

Dans `src/tms_vision/api.py`, remplacer la fonction `create_analysis` existante :

```python
@app.post("/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(..., ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
) -> dict:
    suffix = Path(file.filename or "").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            shutil.copyfileobj(file.file, tmp)

        result = await run_in_threadpool(
            analyze_video,
            source=str(upload_path),
            side=side,
            load_kg=load_kg,
            wrist_twist=wrist_twist,
            output_dir=str(OUTPUT_DIR),
        )
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        upload_path.unlink(missing_ok=True)

    if result.empty:
        raise HTTPException(
            status_code=422,
            detail="Vidéo illisible ou vide : aucune frame n'a pu être extraite.",
        )

    summary = json.loads(result.summary_json_path.read_text())

    return {
        "summary": summary,
        "annotated_video_url": f"/outputs/{result.video_path.name}",
        "csv_url": f"/outputs/{result.csv_path.name}",
    }
```

par :

```python
async def _analyze_and_build_response(
    video_path: Path, side: str, load_kg: float, wrist_twist: str
) -> dict:
    """Appelle analyze_video sur un fichier déjà sur disque et construit la
    réponse JSON standard. Partagé par create_analysis (upload direct) et
    complete_upload (upload par chunks) : les deux finissent par produire un
    seul fichier vidéo local, traité de façon identique à partir de ce point."""
    try:
        result = await run_in_threadpool(
            analyze_video,
            source=str(video_path),
            side=side,
            load_kg=load_kg,
            wrist_twist=wrist_twist,
            output_dir=str(OUTPUT_DIR),
        )
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.empty:
        raise HTTPException(
            status_code=422,
            detail="Vidéo illisible ou vide : aucune frame n'a pu être extraite.",
        )

    summary = json.loads(result.summary_json_path.read_text())
    return {
        "summary": summary,
        "annotated_video_url": f"/outputs/{result.video_path.name}",
        "csv_url": f"/outputs/{result.csv_path.name}",
    }


@app.post("/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(..., ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
) -> dict:
    suffix = Path(file.filename or "").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            shutil.copyfileobj(file.file, tmp)
        return await _analyze_and_build_response(upload_path, side, load_kg, wrist_twist)
    finally:
        upload_path.unlink(missing_ok=True)
```

Puis ajouter le nouvel endpoint juste après (avant ou après `create_analysis`, peu importe
l'ordre — placer après `upload_chunk` pour garder les 3 endpoints `/uploads*` groupés) :

```python
@app.post("/uploads/{upload_id}/complete")
async def complete_upload(
    upload_id: str,
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(..., ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
) -> dict:
    session_dir = OUTPUT_DIR / ".uploads" / upload_id
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Session d'envoi introuvable.")

    meta = json.loads(meta_path.read_text())
    total_chunks = meta["total_chunks"]
    chunk_paths = [session_dir / f"chunk_{i:06d}" for i in range(total_chunks)]
    missing = [i for i, path in enumerate(chunk_paths) if not path.is_file()]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Morceau(x) manquant(s) : {missing}. Réessayez l'import du fichier.",
        )

    suffix = Path(meta["filename"]).suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            for chunk_path in chunk_paths:
                with open(chunk_path, "rb") as chunk_file:
                    shutil.copyfileobj(chunk_file, tmp)
        return await _analyze_and_build_response(upload_path, side, load_kg, wrist_twist)
    finally:
        upload_path.unlink(missing_ok=True)
        shutil.rmtree(session_dir, ignore_errors=True)
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

Run: `venv/bin/pytest tests/test_api.py -v`
Expected: tous les tests de `test_api.py` passent, y compris les 5 nouveaux et l'intégralité des
tests existants sur `/analyses` (non-régression du refactor).

- [ ] **Step 5: Lancer toute la suite du projet**

Run: `venv/bin/pytest -v`
Expected: tous les tests passent (backend complet).

- [ ] **Step 6: Commit**

```bash
git add src/tms_vision/api.py tests/test_api.py
git commit -m "feat: endpoint POST /uploads/{id}/complete, réassemble et lance l'analyse"
```

---

## Task 4: Interface web — mode « Importer une vidéo » (sans chunking, upload direct)

**Files:**
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes : état/fonctions existants de `page.tsx` (`recordedFile`, `setRecordedFile`, `side`,
  `loadKg`, `wristTwist`, `setError`, `setResult`, section formulaire déjà rendue quand
  `recordedFile && !recording`).
- Produces : état `mode: "camera" | "upload" | null` (initialisé à `null`), `fileInputRef`,
  `handleFileSelected(event)`. Ce mode est consommé par Task 5 pour brancher `analyze()` sur le
  flux chunké.

Ce chemin utilise volontairement encore l'upload direct (`POST /analyses`, comme la caméra)
plutôt que le chunking — l'objectif de cette tâche est uniquement l'UI de sélection de fichier,
vérifiable seule dans le navigateur avant d'ajouter la complexité du chunking à la Task 5.

- [ ] **Step 1: Ajouter l'état et la référence au fichier**

Dans `web/app/page.tsx`, ajouter après la ligne `const recordingTimeoutRef = ...` (ligne 30) :

```typescript
  const fileInputRef = useRef<HTMLInputElement | null>(null);
```

Ajouter après la ligne `const [cameraReady, setCameraReady] = useState(false);` (ligne 32) :

```typescript
  const [mode, setMode] = useState<"camera" | "upload" | null>(null);
```

- [ ] **Step 2: Marquer le mode caméra au démarrage de la caméra**

Dans `startCamera()`, juste après `setCameraReady(true);` (ligne 58), ajouter :

```typescript
      setMode("camera");
```

- [ ] **Step 3: Ajouter le gestionnaire de sélection de fichier**

Ajouter une nouvelle fonction juste après `startCamera()` (avant `startRecording`) :

```typescript
  function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(null);
    setResult(null);
    setMode("upload");
    setRecordedFile(file);
  }
```

- [ ] **Step 4: Ajouter le bouton d'import et l'input file dans le JSX**

Remplacer le bloc actuel :

```tsx
      {!cameraReady && (
        <button onClick={startCamera} className="rounded bg-black px-4 py-2 text-white">
          Démarrer la caméra
        </button>
      )}
```

par :

```tsx
      {mode === null && (
        <div className="flex gap-2">
          <button onClick={startCamera} className="rounded bg-black px-4 py-2 text-white">
            Démarrer la caméra
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="rounded border border-black px-4 py-2"
          >
            Importer une vidéo
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={handleFileSelected}
          />
        </div>
      )}
```

- [ ] **Step 5: Vérification manuelle dans le navigateur**

Démarrer les deux serveurs (voir README section 10) :

```bash
PYTHONPATH=src venv/bin/uvicorn tms_vision.api:app --reload --port 8000
```

```bash
cd web && npm run dev
```

Ouvrir `http://localhost:3000`. Vérifier :
- Les deux boutons « Démarrer la caméra » et « Importer une vidéo » sont visibles côte à côte.
- Cliquer « Importer une vidéo » ouvre le sélecteur de fichier du système.
- Choisir `samples/synthetic_smoke_test.mp4` fait apparaître le formulaire (côté/charge/torsion)
  et le bouton « Analyser », exactement comme après un enregistrement caméra.
- Cliquer « Analyser » envoie le fichier à `POST /analyses` (visible dans l'onglet Réseau du
  navigateur) et affiche le résultat RULA, comme pour le flux caméra.

- [ ] **Step 6: Commit**

```bash
git add web/app/page.tsx
git commit -m "feat: bouton d'import de fichier vidéo, alternative à la capture caméra"
```

---

## Task 5: Brancher le mode upload sur l'envoi par chunks

**Files:**
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes : `mode`, `recordedFile`, `side`, `loadKg`, `wristTwist` (Task 4) ; endpoints
  `POST /uploads`, `PUT /uploads/{id}/chunks/{index}`, `POST /uploads/{id}/complete` (Tasks 1-3).
- Produces : `CHUNK_SIZE` (constante), `uploadChunkWithRetry()`, `analyzeViaChunkedUpload()`,
  `analyzeViaCameraCapture()`, état `uploadProgress: { current: number; total: number } | null`.

- [ ] **Step 1: Extraire le chemin caméra existant dans sa propre fonction**

Dans `web/app/page.tsx`, remplacer le corps actuel de `analyze()` :

```typescript
  async function analyze() {
    if (!recordedFile) return;
    if (loadKg.trim() === "") {
      setError("Renseignez une charge en kg (0 si aucune).");
      return;
    }
    setAnalyzing(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", recordedFile);
      formData.append("side", side);
      formData.append("load_kg", loadKg);
      formData.append("wrist_twist", wristTwist);

      const response = await fetch(`${API_URL}/analyses`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const detail = body?.detail;
        const message =
          typeof detail === "string"
            ? detail
            : `Erreur de validation (code ${response.status}).`;
        throw new Error(message);
      }

      const data: AnalysisResponse = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue pendant l'analyse.");
    } finally {
      setAnalyzing(false);
    }
  }
```

par :

```typescript
  async function analyzeViaCameraCapture(
    file: File,
    side: Side,
    loadKg: string,
    wristTwist: WristTwist
  ): Promise<AnalysisResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("side", side);
    formData.append("load_kg", loadKg);
    formData.append("wrist_twist", wristTwist);

    const response = await fetch(`${API_URL}/analyses`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = body?.detail;
      const message =
        typeof detail === "string" ? detail : `Erreur de validation (code ${response.status}).`;
      throw new Error(message);
    }

    return (await response.json()) as AnalysisResponse;
  }

  async function analyze() {
    if (!recordedFile) return;
    if (loadKg.trim() === "") {
      setError("Renseignez une charge en kg (0 si aucune).");
      return;
    }
    setAnalyzing(true);
    setError(null);
    setResult(null);
    try {
      const data =
        mode === "upload"
          ? await analyzeViaChunkedUpload(recordedFile, side, loadKg, wristTwist)
          : await analyzeViaCameraCapture(recordedFile, side, loadKg, wristTwist);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue pendant l'analyse.");
    } finally {
      setAnalyzing(false);
      setUploadProgress(null);
    }
  }
```

- [ ] **Step 2: Ajouter la constante de taille de chunk et l'état de progression**

Ajouter après `const MAX_RECORDING_MS = 30_000;` (ligne 6) :

```typescript
const CHUNK_SIZE = 5 * 1024 * 1024; // 5 Mo
const MAX_CHUNK_RETRIES = 3;
```

Ajouter après `const [result, setResult] = useState<AnalysisResponse | null>(null);` (ligne 40) :

```typescript
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(
    null
  );
```

- [ ] **Step 3: Implémenter le retry par chunk**

Ajouter cette fonction juste avant `analyzeViaCameraCapture` (celle écrite au Step 1) :

```typescript
  async function uploadChunkWithRetry(uploadId: string, index: number, chunk: Blob) {
    let lastError: unknown;
    for (let attempt = 1; attempt <= MAX_CHUNK_RETRIES; attempt++) {
      try {
        const formData = new FormData();
        formData.append("file", chunk, `chunk-${index}`);
        const response = await fetch(`${API_URL}/uploads/${uploadId}/chunks/${index}`, {
          method: "PUT",
          body: formData,
        });
        if (!response.ok) {
          throw new Error(`Échec de l'envoi du morceau ${index + 1} (code ${response.status}).`);
        }
        return;
      } catch (err) {
        lastError = err;
        if (attempt < MAX_CHUNK_RETRIES) {
          await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
        }
      }
    }
    throw lastError instanceof Error ? lastError : new Error("Échec de l'envoi du fichier.");
  }
```

- [ ] **Step 4: Implémenter le flux d'upload par chunks**

Ajouter juste après `uploadChunkWithRetry`, avant `analyzeViaCameraCapture` :

```typescript
  async function analyzeViaChunkedUpload(
    file: File,
    side: Side,
    loadKg: string,
    wristTwist: WristTwist
  ): Promise<AnalysisResponse> {
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

    const startResponse = await fetch(`${API_URL}/uploads`, {
      method: "POST",
      body: new URLSearchParams({ filename: file.name, total_chunks: String(totalChunks) }),
    });
    if (!startResponse.ok) {
      throw new Error("Impossible de démarrer l'envoi du fichier.");
    }
    const { upload_id: uploadId } = (await startResponse.json()) as { upload_id: string };

    for (let index = 0; index < totalChunks; index++) {
      const start = index * CHUNK_SIZE;
      const chunk = file.slice(start, start + CHUNK_SIZE);
      setUploadProgress({ current: index + 1, total: totalChunks });
      await uploadChunkWithRetry(uploadId, index, chunk);
    }
    setUploadProgress(null);

    const completeResponse = await fetch(`${API_URL}/uploads/${uploadId}/complete`, {
      method: "POST",
      body: new URLSearchParams({ side, load_kg: loadKg, wrist_twist: wristTwist }),
    });
    if (!completeResponse.ok) {
      const body = await completeResponse.json().catch(() => null);
      const detail = body?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : `Erreur de validation (code ${completeResponse.status}).`;
      throw new Error(message);
    }
    return (await completeResponse.json()) as AnalysisResponse;
  }
```

- [ ] **Step 5: Afficher la progression pendant l'envoi**

Remplacer le bouton « Analyser » actuel :

```tsx
          <button
            onClick={analyze}
            disabled={analyzing}
            className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {analyzing ? "Analyse en cours..." : "Analyser"}
          </button>
```

par :

```tsx
          <button
            onClick={analyze}
            disabled={analyzing}
            className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {uploadProgress
              ? `Envoi du fichier : ${uploadProgress.current}/${uploadProgress.total}...`
              : analyzing
                ? "Analyse en cours..."
                : "Analyser"}
          </button>
```

- [ ] **Step 6: Vérification manuelle dans le navigateur**

Avec les deux serveurs toujours lancés (Task 4, Step 5) :
- Ouvrir `http://localhost:3000`, cliquer « Importer une vidéo », choisir
  `samples/synthetic_smoke_test.mp4`, remplir le formulaire, cliquer « Analyser ».
- Dans l'onglet Réseau du navigateur, vérifier : un `POST /uploads`, puis un ou plusieurs
  `PUT /uploads/{id}/chunks/{i}` (1 seul chunk attendu ici car le fichier de test fait moins de
  5 Mo), puis un `POST /uploads/{id}/complete`. Aucune requête vers `POST /analyses` pour ce
  chemin.
- Le résultat affiché (score RULA, vidéo annotée, lien CSV) doit être cohérent avec celui obtenu
  au Step 5 de la Task 4 (même fichier, même formulaire) — confirme que le chunking ne change pas
  le résultat de l'analyse.
- Vérifier que le chemin caméra (« Démarrer la caméra » → enregistrer → Analyser) fonctionne
  toujours sans régression : requête unique vers `POST /analyses`, pas de `POST /uploads`.

- [ ] **Step 7: Commit**

```bash
git add web/app/page.tsx
git commit -m "feat: envoi par chunks pour les vidéos importées, avec retry et progression"
```
