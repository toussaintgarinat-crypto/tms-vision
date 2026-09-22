# Dashboard d'historique des analyses — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Donner accès, depuis l'interface web, à la liste des analyses déjà persistées en
DuckDB (avec filtres salarié/poste/période) et au détail complet de chacune (vidéo annotée,
avatar 3D, résumé RULA, recommandation de capsule).

**Architecture:** Deux nouvelles routes Next.js (`/historique` et `/historique/[id]`), toutes
deux des Client Components suivant les conventions déjà en place dans `web/app/page.tsx`
(`fetch` contre `NEXT_PUBLIC_API_URL`, pas de state management externe). Le bloc "Résultat" déjà
affiché sur la page d'accueil est extrait en composant partagé (`AnalysisResult.tsx`) et
réutilisé par la page de détail. Aucun changement backend : `GET /analyses` et
`GET /analyses/{id}` (existants) couvrent tout le besoin.

**Tech Stack:** Next.js 16.3.5 (App Router) / React 19 / TypeScript, `web/` uniquement. Backend
inchangé.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-22-analysis-history-dashboard-design.md`.
- Aucun changement à `src/tms_vision/` ni à l'API (`GET /analyses`, `GET /analyses/{id}` déjà
  suffisants).
- Pas de pagination dans ce sprint.
- Pas de tests unitaires automatisés sur les nouvelles pages (aucune logique pure nouvelle à
  tester ; suit le précédent déjà établi pour `page.tsx`/`PostureAvatar3D.tsx`) — vérification
  manuelle Playwright à la place, à chaque tâche qui touche l'UI.
- `params` est une Promise dans cette version de Next.js pour les Server Components, mais les
  pages de ce plan sont des Client Components : utiliser le hook `useParams()` de
  `next/navigation` (synchrone côté client), pas `use(params)`.
- Ce projet n'utilise `next/link` nulle part aujourd'hui : rester cohérent et utiliser des
  `<a href="...">` classiques pour la navigation interne, pas d'import `next/link` nouveau.
  **Exception découverte et approuvée pendant l'exécution (Task 2)** : `@next/eslint-plugin-next`
  (règle `no-html-link-for-pages`) construit ses regex de route pour `app/` via `normalizeAppPath`
  (pas de slash final forcé) mais teste les `href` littéraux via `normalizeURL` (slash final
  toujours ajouté) — un vrai bug de la règle, vérifié empiriquement (édition directe du fichier +
  relance de `npm run lint`), qui fait qu'un `<a href="/">` littéral échoue le lint (seul cas où
  les deux normalisations coïncident) alors qu'un `<a href="/historique">` ne se fait jamais
  flaguer, même une fois cette route créée. Le lien de retour vers la racine `/` utilise donc
  `next/link`'s `<Link>` — seul ce lien précis ; tout le reste (y compris les liens vers
  `/historique/{id}`) reste en `<a>` classique.
- Commandes de vérification standard pour tout `web/` : `cd web && npx tsc --noEmit`,
  `cd web && npm run lint`, `cd web && npm run build`, `cd web && npm run test` (vitest, suite
  existante de modules purs — doit rester verte après chaque tâche).
- Éviter tout `setState` synchrone de réinitialisation en tête de corps de `useEffect` (viole la
  règle ESLint `react-hooks/set-state-in-effect`, déjà rencontrée dans ce projet — voir le commit
  `4e99df9`) : préférer un état porteur de la clé à laquelle il correspond (ex. `{ id, data }`),
  comparé à la clé courante au moment du rendu plutôt que réinitialisé de façon synchrone au
  début de l'effet. `AnalysisResult.tsx` (Task 1) applique déjà ce motif ; `historique/[id]/page.tsx`
  (Task 3) doit faire de même.

---

### Task 1: Extraire `AnalysisResult.tsx`, réutilisé par `page.tsx`

Aujourd'hui, le bloc "Résultat" (vidéo annotée + avatar 3D + résumé + lien CSV + recommandation)
est câblé en dur dans `page.tsx`, autour de l'état `result` d'une analyse tout juste terminée. Ce
bloc doit devenir un composant partagé pour que la future page de détail d'historique (Task 3)
puisse l'afficher aussi. Cette tâche est un pur refactor : le comportement de `page.tsx` ne doit
pas changer.

**Files:**
- Create: `web/app/AnalysisResult.tsx`
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: `PostureAvatar3D`, `Side` (`./PostureAvatar3D`, inchangé).
- Produces: composant `AnalysisResult` (props `{ analysisId: string; side: Side; summary:
  AnalysisSummary; videoUrl: string; csvUrl: string; pose3dUrl: string }`, où `videoUrl`/
  `csvUrl`/`pose3dUrl` sont les chemins **relatifs** renvoyés par l'API, ex. `/analyses/{id}/video`
  — le composant préfixe lui-même `API_URL` pour la vidéo/le CSV ; `pose3dUrl` est passé tel quel
  à `PostureAvatar3D`, qui fait déjà son propre préfixage en interne) ; type `AnalysisSummary`
  (déplacé ici, `page.tsx` l'importera). Utilisé par Task 3.

- [ ] **Step 1: Créer `web/app/AnalysisResult.tsx`**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

import { PostureAvatar3D, Side } from "./PostureAvatar3D";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AnalysisSummary = {
  frame_count: number;
  detected_frame_count: number;
  max_score: number;
  average_score: number;
  time_by_action_level: Record<string, number>;
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

type AnalysisResultProps = {
  analysisId: string;
  side: Side;
  summary: AnalysisSummary;
  videoUrl: string;
  csvUrl: string;
  pose3dUrl: string;
};

export function AnalysisResult({
  analysisId,
  side,
  summary,
  videoUrl,
  csvUrl,
  pose3dUrl,
}: AnalysisResultProps) {
  const resultVideoRef = useRef<HTMLVideoElement | null>(null);
  const [recommendation, setRecommendation] = useState<{
    analysisId: string;
    data: Recommendation;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/analyses/${analysisId}/recommendation`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<Recommendation>;
      })
      .then((data) => {
        if (!cancelled) setRecommendation({ analysisId, data });
      })
      .catch(() => {
        // Erreur réseau ou analyse introuvable : on ne montre rien plutôt que
        // de bloquer l'affichage du résultat principal -- silence volontaire,
        // pas un oubli (voir revue finale de la tranche capsules).
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  return (
    <section className="flex flex-col gap-4 rounded border p-4">
      <h2 className="text-lg font-semibold">Résultat</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <video
          ref={resultVideoRef}
          src={`${API_URL}${videoUrl}`}
          controls
          className="w-full rounded-lg bg-black"
        />
        <PostureAvatar3D pose3dUrl={pose3dUrl} videoRef={resultVideoRef} side={side} />
      </div>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt>Frames analysées</dt>
        <dd>{summary.frame_count}</dd>
        <dt>Frames avec pose détectée</dt>
        <dd>{summary.detected_frame_count}</dd>
        <dt>Score RULA max</dt>
        <dd>{summary.max_score}</dd>
        <dt>Score RULA moyen</dt>
        <dd>{summary.average_score.toFixed(1)}</dd>
      </dl>
      <a href={`${API_URL}${csvUrl}`} className="text-blue-600 underline">
        Télécharger le CSV détaillé
      </a>
      {recommendation?.analysisId === analysisId && recommendation.data.capsule && (
        <div className="rounded border border-blue-200 bg-blue-50 p-3">
          <p className="text-sm font-semibold">
            Recommandation : zone{" "}
            {ZONE_LABELS[recommendation.data.zone ?? ""] ?? recommendation.data.zone}
          </p>
          <p className="font-medium">{recommendation.data.capsule.title}</p>
          <p className="text-sm text-gray-700">{recommendation.data.capsule.description}</p>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Réécrire `web/app/page.tsx` pour utiliser `AnalysisResult`**

Remplacer le fichier entier par :

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

import { AnalysisResult, AnalysisSummary } from "./AnalysisResult";
import { Side } from "./PostureAvatar3D";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_RECORDING_MS = 30_000;
const CHUNK_SIZE = 5 * 1024 * 1024; // 5 Mo
const MAX_CHUNK_RETRIES = 3;

type WristTwist = "normal" | "extreme";

type AnalysisResponse = {
  analysis_id: string;
  summary: AnalysisSummary;
  annotated_video_url: string;
  csv_url: string;
  pose3d_url: string;
  side: Side;
};

export default function Home() {
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [cameraReady, setCameraReady] = useState(false);
  const [mode, setMode] = useState<"camera" | "upload" | null>(null);
  const [recording, setRecording] = useState(false);
  const [recordedFile, setRecordedFile] = useState<File | null>(null);
  const [side, setSide] = useState<Side>("right");
  const [loadKg, setLoadKg] = useState("0");
  const [wristTwist, setWristTwist] = useState<WristTwist>("normal");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(
    null
  );

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function startCamera() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
      });
      streamRef.current = stream;
      if (videoPreviewRef.current) {
        videoPreviewRef.current.srcObject = stream;
      }
      setCameraReady(true);
      setMode("camera");
    } catch {
      setError(
        "Impossible d'accéder à la caméra. Vérifiez les permissions du navigateur et que la page est servie en HTTPS ou localhost."
      );
    }
  }

  function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size === 0) {
      setError("Le fichier sélectionné est vide.");
      return;
    }
    setError(null);
    setResult(null);
    setMode("upload");
    setRecordedFile(file);
  }

  function startRecording() {
    if (!streamRef.current) return;
    setError(null);
    try {
      const mimeType = MediaRecorder.isTypeSupported("video/mp4")
        ? "video/mp4"
        : "video/webm";
      const recorder = new MediaRecorder(streamRef.current, { mimeType });
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const extension = mimeType.includes("mp4") ? "mp4" : "webm";
        setRecordedFile(new File([blob], `capture.${extension}`, { type: mimeType }));
      };
      recorder.onerror = () => {
        if (recordingTimeoutRef.current) {
          clearTimeout(recordingTimeoutRef.current);
          recordingTimeoutRef.current = null;
        }
        setRecording(false);
        setError("Erreur pendant l'enregistrement, réessayez.");
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
      setResult(null);
      setRecordedFile(null);
      recordingTimeoutRef.current = setTimeout(() => {
        stopRecording();
      }, MAX_RECORDING_MS);
    } catch {
      setError(
        "L'enregistrement vidéo n'est pas supporté par ce navigateur. Essayez avec un navigateur à jour (Chrome, Firefox, Edge)."
      );
    }
  }

  function stopRecording() {
    if (recordingTimeoutRef.current) {
      clearTimeout(recordingTimeoutRef.current);
      recordingTimeoutRef.current = null;
    }
    recorderRef.current?.stop();
    setRecording(false);
  }

  class ChunkUploadError extends Error {
    retryable: boolean;
    constructor(message: string, retryable: boolean) {
      super(message);
      this.retryable = retryable;
    }
  }

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
          const retryable =
            response.status >= 500 || response.status === 408 || response.status === 429;
          throw new ChunkUploadError(
            `Échec de l'envoi du morceau ${index + 1} (code ${response.status}).`,
            retryable
          );
        }
        return;
      } catch (err) {
        lastError = err;
        if (err instanceof ChunkUploadError && !err.retryable) {
          break;
        }
        if (attempt < MAX_CHUNK_RETRIES) {
          await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
        }
      }
    }
    console.error(lastError);
    throw new Error("Envoi interrompu, réessayez l'import du fichier.");
  }

  async function readErrorMessage(response: Response, fallback: string): Promise<string> {
    const body = await response.json().catch(() => null);
    const detail = (body as { detail?: unknown } | null)?.detail;
    return typeof detail === "string" ? detail : fallback;
  }

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
      throw new Error(
        await readErrorMessage(startResponse, "Impossible de démarrer l'envoi du fichier.")
      );
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
      throw new Error(
        await readErrorMessage(completeResponse, `Erreur de validation (code ${completeResponse.status}).`)
      );
    }
    return (await completeResponse.json()) as AnalysisResponse;
  }

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
      throw new Error(await readErrorMessage(response, `Erreur de validation (code ${response.status}).`));
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

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">TMS Vision — Vérification RULA</h1>
        <a href="/historique" className="text-sm text-blue-600 underline">
          Historique
        </a>
      </div>

      <video
        ref={videoPreviewRef}
        autoPlay
        muted
        playsInline
        className="w-full rounded-lg bg-black"
      />

      <input
        ref={fileInputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={handleFileSelected}
      />

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
        </div>
      )}

      {mode === "upload" && !recording && (
        <div className="flex flex-col gap-1">
          {recordedFile && (
            <p className="text-sm text-gray-600">Fichier sélectionné : {recordedFile.name}</p>
          )}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="self-start text-sm text-blue-600 underline"
          >
            Changer de vidéo
          </button>
        </div>
      )}

      {cameraReady && !recording && (
        <div className="flex flex-col gap-1">
          <button onClick={startRecording} className="rounded bg-red-600 px-4 py-2 text-white">
            Démarrer l&apos;enregistrement
          </button>
          <span className="text-sm text-gray-500">
            Enregistrement limité à 30 secondes.
          </span>
        </div>
      )}

      {recording && (
        <button onClick={stopRecording} className="rounded bg-gray-700 px-4 py-2 text-white">
          Arrêter l&apos;enregistrement
        </button>
      )}

      {recordedFile && !recording && (
        <section className="flex flex-col gap-4 rounded border p-4">
          <label className="flex flex-col gap-1">
            Côté filmé
            <select
              value={side}
              onChange={(event) => setSide(event.target.value as Side)}
              className="rounded border p-2"
            >
              <option value="right">Droit</option>
              <option value="left">Gauche</option>
            </select>
          </label>

          <label className="flex flex-col gap-1">
            Charge tenue (kg)
            <input
              type="number"
              min="0"
              step="0.5"
              value={loadKg}
              onChange={(event) => setLoadKg(event.target.value)}
              className="rounded border p-2"
            />
          </label>

          <label className="flex flex-col gap-1">
            Torsion du poignet
            <select
              value={wristTwist}
              onChange={(event) => setWristTwist(event.target.value as WristTwist)}
              className="rounded border p-2"
            >
              <option value="normal">Normale</option>
              <option value="extreme">Extrême</option>
            </select>
          </label>

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
        </section>
      )}

      {error && <p className="text-red-600">{error}</p>}

      {result && (
        <AnalysisResult
          analysisId={result.analysis_id}
          side={result.side}
          summary={result.summary}
          videoUrl={result.annotated_video_url}
          csvUrl={result.csv_url}
          pose3dUrl={result.pose3d_url}
        />
      )}
    </main>
  );
}
```

Cette réécriture supprime uniquement : les types `AnalysisSummary` (déplacé, désormais importé),
`Capsule`/`Recommendation`/`ZONE_LABELS` (déplacés dans `AnalysisResult.tsx`), le ref
`resultVideoRef`, l'état `recommendation` et son `useEffect` de récupération (déplacés dans
`AnalysisResult.tsx`), et remplace le bloc JSX `{result && (...)}` par `<AnalysisResult ... />` ;
elle ajoute le lien "Historique" dans l'en-tête. Aucune autre logique ne change.

- [ ] **Step 3: Vérifier les types**

Run: `cd web && npx tsc --noEmit`
Expected: aucune erreur.

- [ ] **Step 4: Vérifier le lint**

Run: `cd web && npm run lint`
Expected: aucune erreur (en particulier, pas de régression `react-hooks/set-state-in-effect` sur
l'effet déplacé dans `AnalysisResult.tsx`).

- [ ] **Step 5: Vérifier le build**

Run: `cd web && npm run build`
Expected: build réussi, aucune erreur.

- [ ] **Step 6: Rejouer la suite de tests existante (régression)**

Run: `cd web && npm run test`
Expected: tous les tests passent (modules purs `pose3dSkeleton`, `muscleSegments`,
`testSkinnedGeometry`, `muscleRigInvariants`, `skinning-integration` — aucun n'est touché par ce
refactor, doit rester vert à l'identique).

- [ ] **Step 7: Vérification manuelle dans un vrai navigateur (Playwright) — non-régression**

1. Démarrer l'API : `cd "/Users/garinat_t/Desktop/TMS vision" && PYTHONPATH=src venv/bin/uvicorn tms_vision.api:app --reload --port 8000` (terminal séparé ou arrière-plan).
2. Démarrer le frontend : `cd web && npm run dev` (autre terminal ou arrière-plan).
3. Avec Playwright (MCP déjà disponible dans cette session) : naviguer vers
   `http://localhost:3000`, importer `samples/synthetic_smoke_test.mp4` via le flux d'import de
   fichier existant, lancer l'analyse.
4. Vérifier que le bloc "Résultat" s'affiche exactement comme avant ce refactor : vidéo annotée
   lisible, zone avatar 3D présente (message "Aucune posture détectée" attendu sur cette vidéo de
   test), résumé chiffré (`frame_count`/`detected_frame_count`/scores), lien "Télécharger le CSV
   détaillé" présent et pointant vers une URL absolue (`http://localhost:8000/analyses/.../frames.csv`).
   Aucune erreur console.
5. Vérifier que le nouveau lien "Historique" est visible en haut de la page d'accueil (la route
   `/historique` n'existe pas encore à ce stade du plan — cliquer dessus donnera une 404 Next.js,
   c'est attendu, Task 2 la crée).

- [ ] **Step 8: Commit**

```bash
git add web/app/AnalysisResult.tsx web/app/page.tsx
git commit -m "refactor: extrait AnalysisResult en composant partagé"
```

---

### Task 2: `web/app/historique/page.tsx` — liste des analyses avec filtres

**Files:**
- Create: `web/app/historique/page.tsx`

**Interfaces:**
- Consumes: `GET /analyses` (existant, `src/tms_vision/api.py`), paramètres de requête optionnels
  `worker_label`, `poste_label`, `since`, `until` (tous des égalités/bornes **exactes**, pas de
  recherche par sous-chaîne — `storage.list_analyses` fait `worker_label = ?`, pas de `LIKE`).
  Réponse : liste d'objets `{id, created_at, side, load_kg, wrist_twist, worker_label,
  poste_label, frame_count, detected_frame_count, max_score, average_score,
  time_by_action_level}`, déjà triée `created_at` décroissant côté serveur.
- Produces: route `/historique`, liens `<a href="/historique/{id}">` consommés par Task 3.

- [ ] **Step 1: Créer `web/app/historique/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type StoredAnalysis = {
  id: string;
  created_at: string;
  side: "left" | "right";
  load_kg: number;
  wrist_twist: "normal" | "extreme";
  worker_label: string | null;
  poste_label: string | null;
  frame_count: number;
  detected_frame_count: number;
  max_score: number;
  average_score: number;
  time_by_action_level: Record<string, number>;
};

const SIDE_LABELS: Record<string, string> = { right: "Droit", left: "Gauche" };

// Mêmes seuils que rula/scoring.py::action_level(), même palette que
// PostureAvatar3D.tsx::ACTION_LEVEL_COLORS -- dupliqué ici (4 couleurs figées,
// pas de dépendance ajoutée pour si peu).
function scoreBadgeColor(maxScore: number): string {
  if (maxScore <= 2) return "#4CAF50";
  if (maxScore <= 4) return "#EBD23C";
  if (maxScore <= 6) return "#EB9628";
  return "#D23232";
}

export default function HistoriquePage() {
  const [analyses, setAnalyses] = useState<StoredAnalysis[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [workerLabel, setWorkerLabel] = useState("");
  const [posteLabel, setPosteLabel] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams();
    if (workerLabel.trim()) params.set("worker_label", workerLabel.trim());
    if (posteLabel.trim()) params.set("poste_label", posteLabel.trim());
    if (since) params.set("since", since);
    if (until) params.set("until", `${until}T23:59:59`);
    const query = params.toString();
    fetch(`${API_URL}/analyses${query ? `?${query}` : ""}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<StoredAnalysis[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setAnalyses(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("Impossible de charger l'historique des analyses.");
      });
    return () => {
      cancelled = true;
    };
  }, [workerLabel, posteLabel, since, until]);

  const hasFilters = Boolean(workerLabel || posteLabel || since || until);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Historique des analyses</h1>
        <a href="/" className="text-sm text-blue-600 underline">
          ← Nouvelle analyse
        </a>
      </div>

      <section className="grid gap-4 rounded border p-4 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-sm">
          Salarié
          <input
            type="text"
            value={workerLabel}
            onChange={(event) => setWorkerLabel(event.target.value)}
            className="rounded border p-2"
          />
          <span className="text-xs text-gray-500">Correspondance exacte</span>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Poste
          <input
            type="text"
            value={posteLabel}
            onChange={(event) => setPosteLabel(event.target.value)}
            className="rounded border p-2"
          />
          <span className="text-xs text-gray-500">Correspondance exacte</span>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Depuis
          <input
            type="date"
            value={since}
            onChange={(event) => setSince(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Jusqu&apos;à
          <input
            type="date"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
            className="rounded border p-2"
          />
        </label>
      </section>

      {error && <p className="text-red-600">{error}</p>}

      {analyses === null && !error && <p>Chargement...</p>}

      {analyses !== null && analyses.length === 0 && (
        <p className="text-gray-600">
          {hasFilters
            ? "Aucune analyse ne correspond à ces filtres."
            : "Aucune analyse enregistrée."}
        </p>
      )}

      {analyses !== null && analyses.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="p-2">Date</th>
                <th className="p-2">Salarié</th>
                <th className="p-2">Poste</th>
                <th className="p-2">Côté</th>
                <th className="p-2">Score max</th>
                <th className="p-2">Score moyen</th>
                <th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {analyses.map((analysis) => (
                <tr key={analysis.id} className="border-b">
                  <td className="p-2">{new Date(analysis.created_at).toLocaleString("fr-FR")}</td>
                  <td className="p-2">{analysis.worker_label ?? "—"}</td>
                  <td className="p-2">{analysis.poste_label ?? "—"}</td>
                  <td className="p-2">{SIDE_LABELS[analysis.side]}</td>
                  <td className="p-2">
                    <span
                      className="rounded px-2 py-1 text-white"
                      style={{ backgroundColor: scoreBadgeColor(analysis.max_score) }}
                    >
                      {analysis.max_score}
                    </span>
                  </td>
                  <td className="p-2">{analysis.average_score.toFixed(1)}</td>
                  <td className="p-2">
                    <a href={`/historique/${analysis.id}`} className="text-blue-600 underline">
                      Voir
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Vérifier les types**

Run: `cd web && npx tsc --noEmit`
Expected: aucune erreur.

- [ ] **Step 3: Vérifier le lint**

Run: `cd web && npm run lint`
Expected: aucune erreur.

- [ ] **Step 4: Vérifier le build**

Run: `cd web && npm run build`
Expected: build réussi, aucune erreur (la route `/historique` doit apparaître dans la sortie du
build).

- [ ] **Step 5: Vérification manuelle dans un vrai navigateur (Playwright)**

1. S'assurer qu'il existe des données à afficher : `data/tms_vision.duckdb` contient déjà
   plusieurs analyses de sessions de vérification précédentes (vérifiable avec
   `PYTHONPATH=src venv/bin/python -c "from tms_vision import storage; print(len(storage.list_analyses()))"`
   depuis la racine du projet). Si ce nombre est 0, produire au moins une analyse au préalable
   via `http://localhost:3000` (import de `samples/synthetic_smoke_test.mp4` suffit).
2. Avec les deux serveurs démarrés (API sur :8000, frontend sur :3000, comme à la Task 1 Step 7),
   naviguer vers `http://localhost:3000/historique`.
3. Vérifier que le tableau affiche au moins une ligne, triée date décroissante, avec un badge de
   score coloré (vert pour un `max_score` de 0-2, cohérent avec les analyses existantes qui ont
   `max_score: 0`), et un lien "Voir" par ligne. Aucune erreur console.
4. Taper une valeur qui ne correspond à aucun `worker_label` existant dans le champ "Salarié"
   (ex. `zzz-inexistant`) : vérifier que le tableau se vide et affiche "Aucune analyse ne
   correspond à ces filtres.". Vider le champ : vérifier que les lignes réapparaissent.
5. Retourner sur `http://localhost:3000`, produire une nouvelle analyse via import de fichier
   (`samples/synthetic_smoke_test.mp4` ou `moi coupe.mp4`) en renseignant un salarié (ex.
   `Test Dashboard`) et un poste (ex. `Poste A`) dans le formulaire -- **note** : le formulaire
   actuel de `page.tsx` n'a pas de champs salarié/poste (l'API les accepte via
   `worker_label`/`poste_label` en `Form(...)`, mais le frontend ne les envoie pas encore) ;
   dans ce cas, vérifier plutôt que la nouvelle analyse apparaît bien dans `/historique` avec
   `worker_label`/`poste_label` à "—", ce qui est le comportement correct et attendu (aucune
   régression à corriger ici, l'ajout de ces champs au formulaire n'est pas dans le périmètre de
   ce sprint).
6. Cliquer "Historique" depuis la page d'accueil : vérifier la navigation vers `/historique`.
   Cliquer "← Nouvelle analyse" depuis `/historique` : vérifier le retour vers `/`.

- [ ] **Step 6: Commit**

```bash
git add web/app/historique/page.tsx
git commit -m "feat: page d'historique des analyses avec filtres"
```

---

### Task 3: `web/app/historique/[id]/page.tsx` — détail d'une analyse passée

**Files:**
- Create: `web/app/historique/[id]/page.tsx`

**Interfaces:**
- Consumes: `GET /analyses/{id}` (existant), `AnalysisResult`/`AnalysisSummary`
  (`../../AnalysisResult`, Task 1), `Side` (`../../PostureAvatar3D`).

- [ ] **Step 1: Créer `web/app/historique/[id]/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AnalysisResult, AnalysisSummary } from "../../AnalysisResult";
import { Side } from "../../PostureAvatar3D";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type StoredAnalysis = AnalysisSummary & {
  id: string;
  created_at: string;
  side: Side;
  load_kg: number;
  wrist_twist: "normal" | "extreme";
  worker_label: string | null;
  poste_label: string | null;
};

export default function AnalysisDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  // État porteur de l'id auquel il correspond, comparé à `id` au rendu plutôt
  // que réinitialisé de façon synchrone en tête de l'effet -- même motif que
  // `recommendation` dans AnalysisResult.tsx, pour satisfaire
  // react-hooks/set-state-in-effect (voir Global Constraints).
  const [analysis, setAnalysis] = useState<{ id: string; data: StoredAnalysis } | null>(null);
  const [notFoundFor, setNotFoundFor] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/analyses/${id}`)
      .then((response) => {
        if (response.status === 404) {
          if (!cancelled) setNotFoundFor(id);
          return null;
        }
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<StoredAnalysis>;
      })
      .then((data) => {
        if (!cancelled && data) setAnalysis({ id, data });
      })
      .catch(() => {
        if (!cancelled) setNotFoundFor(id);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const isNotFound = notFoundFor === id;
  // Booléen simple (pas de narrowing TypeScript de `analysis` à travers une
  // variable dérivée) : uniquement pour la condition "Chargement..." ci-dessous.
  // Le rendu d'AnalysisResult re-teste `analysis && analysis.id === id` en
  // ligne pour que TypeScript le rétrécisse correctement.
  const isLoaded = analysis !== null && analysis.id === id;

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Analyse {id}</h1>
        <a href="/historique" className="text-sm text-blue-600 underline">
          ← Retour à l&apos;historique
        </a>
      </div>

      {isNotFound && <p className="text-red-600">Analyse introuvable.</p>}

      {!isNotFound && !isLoaded && <p>Chargement...</p>}

      {analysis && analysis.id === id && (
        <AnalysisResult
          analysisId={analysis.data.id}
          side={analysis.data.side}
          summary={analysis.data}
          videoUrl={`/analyses/${analysis.data.id}/video`}
          csvUrl={`/analyses/${analysis.data.id}/frames.csv`}
          pose3dUrl={`/analyses/${analysis.data.id}/pose3d`}
        />
      )}
    </main>
  );
}
```

- [ ] **Step 2: Vérifier les types**

Run: `cd web && npx tsc --noEmit`
Expected: aucune erreur.

- [ ] **Step 3: Vérifier le lint**

Run: `cd web && npm run lint`
Expected: aucune erreur.

- [ ] **Step 4: Vérifier le build**

Run: `cd web && npm run build`
Expected: build réussi, aucune erreur (la route dynamique `/historique/[id]` doit apparaître dans
la sortie du build).

- [ ] **Step 5: Vérification manuelle dans un vrai navigateur (Playwright)**

1. Avec les deux serveurs démarrés et `/historique` peuplé (Task 2), naviguer vers
   `http://localhost:3000/historique` puis cliquer "Voir" sur une ligne.
2. Vérifier que `http://localhost:3000/historique/{id}` affiche exactement le même contenu que le
   bloc "Résultat" affiché sur la page d'accueil juste après avoir produit cette même analyse
   (vidéo annotée jouable, zone avatar 3D, résumé chiffré identique aux valeurs vues dans le
   tableau, lien CSV). Aucune erreur console.
3. Cliquer "← Retour à l'historique" : vérifier le retour vers `/historique`. Utiliser le bouton
   retour du navigateur depuis `/historique/{id}` : vérifier qu'il ramène correctement à
   `/historique` (pas de crash, l'historique de navigation fonctionne).
4. Naviguer directement vers une URL avec un id inexistant, ex.
   `http://localhost:3000/historique/id-qui-nexiste-pas` : vérifier l'affichage de "Analyse
   introuvable." avec le lien de retour, aucune erreur console non gérée (le rejet 404 de l'API
   doit être intercepté proprement, pas remonter comme une exception affichée à l'utilisateur).

- [ ] **Step 6: Commit**

```bash
git add "web/app/historique/[id]/page.tsx"
git commit -m "feat: page de détail d'une analyse passée"
```

---

### Task 4: Vérification bout-en-bout, croisement avec la base réelle, et mise à jour du README

Cette tâche ferme le sprint : un parcours complet croisant les trois pages avec des filtres
combinés, une vérification indépendante des données affichées contre la base DuckDB réelle
(discipline déjà établie dans ce projet : ne pas se contenter de ce que l'UI affiche), puis la
mise à jour de la documentation produit.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Parcours filtré bout-en-bout (Playwright)**

Avec les deux serveurs démarrés :

1. Sur `http://localhost:3000`, produire deux nouvelles analyses avec des salariés/postes
   distincts et bien remplis (le formulaire actuel n'a pas ces champs -- voir Task 2 Step 5 :
   c'est attendu, ces deux nouvelles analyses auront donc aussi `worker_label`/`poste_label`
   à `null`/"—". Utiliser plutôt deux valeurs de `côté` différentes ("Droit" puis "Gauche") pour
   avoir un signal distinctif à filtrer/vérifier à la place).
2. Sur `/historique`, filtrer par date ("Depuis" = aujourd'hui) : vérifier que seules les analyses
   du jour apparaissent (toutes, dans cet environnement de test).
3. Combiner ce filtre de date avec un filtre "Salarié" inexistant : vérifier que la liste se vide
   (intersection des filtres, pas union).

- [ ] **Step 2: Vérification indépendante contre la base réelle**

Run (depuis la racine du projet) :

```bash
PYTHONPATH=src venv/bin/python -c "
from tms_vision import storage
rows = storage.list_analyses()
print(f'{len(rows)} analyses en base')
for r in rows[:10]:
    print(r['id'], r['created_at'], r['side'], r['max_score'])
"
```

Expected: le nombre d'analyses et les valeurs affichées correspondent exactement à ce que
`/historique` (sans filtre) a montré à l'étape précédente -- mêmes ids, même ordre (date
décroissante), mêmes scores.

- [ ] **Step 3: Mettre à jour le README**

Dans `README.md`, section 8, juste après le bloc `#### ✅ Recommandation de capsules par zone —
TERMINÉE` et avant `#### Reste à faire pour la suite de la Phase 2`, ajouter :

```markdown
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
```

Dans la liste de documents en haut de la section 8 ("Pour reprendre le projet plus tard"), ajouter
juste après la ligne `docs/superpowers/plans/2026-09-22-capsule-zone-recommendation-plan.md` :

```markdown
- `docs/superpowers/specs/2026-09-22-analysis-history-dashboard-design.md` — la spec du dashboard
  d'historique des analyses.
- `docs/superpowers/plans/2026-09-22-analysis-history-dashboard-plan.md` — le plan
  d'implémentation de ce sprint.
```

Dans la section 10 ("Lancer la capture web"), juste après le sous-titre "### Tester depuis un
iPhone (ou tout autre appareil hors du Mac)" -- donc juste avant lui, à la suite du paragraphe sur
l'import de vidéo -- ajouter :

```markdown
### Consulter l'historique des analyses

Le lien « Historique » en haut de la page d'accueil ouvre `/historique` : liste de toutes les
analyses déjà enregistrées, filtrable par salarié, poste et période (depuis/jusqu'à). Cliquer sur
« Voir » ouvre le détail complet d'une analyse passée (`/historique/{id}`), avec le même rendu
(vidéo annotée, avatar 3D, résumé, recommandation) que juste après l'avoir produite.
```

- [ ] **Step 4: Vérifier que le suffixe de section reste cohérent**

Run: `grep -n "^### " README.md | sed -n '1,40p'`
Expected: la nouvelle sous-section "### Consulter l'historique des analyses" apparaît bien avant
"### Tester depuis un iPhone (ou tout autre appareil hors du Mac)", sans doublon de titre.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: documente le dashboard d'historique des analyses dans le README"
```
