"use client";

import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_RECORDING_MS = 30_000;

type Side = "left" | "right";
type WristTwist = "normal" | "extreme";

type AnalysisSummary = {
  frame_count: number;
  detected_frame_count: number;
  max_score: number;
  average_score: number;
  time_by_action_level: Record<string, number>;
};

type AnalysisResponse = {
  summary: AnalysisSummary;
  annotated_video_url: string;
  csv_url: string;
};

export default function Home() {
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [cameraReady, setCameraReady] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordedFile, setRecordedFile] = useState<File | null>(null);
  const [side, setSide] = useState<Side>("right");
  const [loadKg, setLoadKg] = useState("0");
  const [wristTwist, setWristTwist] = useState<WristTwist>("normal");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);

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
    } catch {
      setError(
        "Impossible d'accéder à la caméra. Vérifiez les permissions du navigateur et que la page est servie en HTTPS ou localhost."
      );
    }
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

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold">TMS Vision — Vérification RULA</h1>

      <video
        ref={videoPreviewRef}
        autoPlay
        muted
        playsInline
        className="w-full rounded-lg bg-black"
      />

      {!cameraReady && (
        <button onClick={startCamera} className="rounded bg-black px-4 py-2 text-white">
          Démarrer la caméra
        </button>
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
            {analyzing ? "Analyse en cours..." : "Analyser"}
          </button>
        </section>
      )}

      {error && <p className="text-red-600">{error}</p>}

      {result && (
        <section className="flex flex-col gap-4 rounded border p-4">
          <h2 className="text-lg font-semibold">Résultat</h2>
          <video
            src={`${API_URL}${result.annotated_video_url}`}
            controls
            className="w-full rounded-lg bg-black"
          />
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt>Frames analysées</dt>
            <dd>{result.summary.frame_count}</dd>
            <dt>Frames avec pose détectée</dt>
            <dd>{result.summary.detected_frame_count}</dd>
            <dt>Score RULA max</dt>
            <dd>{result.summary.max_score}</dd>
            <dt>Score RULA moyen</dt>
            <dd>{result.summary.average_score.toFixed(1)}</dd>
          </dl>
          <a href={`${API_URL}${result.csv_url}`} className="text-blue-600 underline">
            Télécharger le CSV détaillé
          </a>
        </section>
      )}
    </main>
  );
}
