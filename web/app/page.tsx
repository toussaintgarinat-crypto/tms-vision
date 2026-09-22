"use client";

import Link from "next/link";
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
        <Link href="/historique" className="text-sm text-blue-600 underline">
          Historique
        </Link>
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
