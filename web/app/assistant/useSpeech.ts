"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { SpeechEngine } from "./assistantSettings";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Types minimaux : SpeechRecognition n'est pas dans lib.dom de TypeScript.
type RecognitionEvent = {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
};
type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
};
type RecognitionConstructor = new () => Recognition;

function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function noSubscription(): () => void {
  return () => {};
}

const BROWSER_ERRORS: Record<string, string> = {
  "not-allowed": "Le micro est refusé : autorisez-le dans le navigateur.",
  "service-not-allowed": "Le micro est refusé : autorisez-le dans le navigateur.",
  "no-speech": "Aucune parole détectée.",
  "audio-capture": "Aucun micro détecté.",
  network: "La reconnaissance vocale du navigateur est injoignable.",
};

/**
 * Écoute vocale avec deux moteurs : la dictée du navigateur, ou l'enregistrement envoyé à
 * POST /assistant/transcribe (transcription souveraine). `onText` reçoit le texte final.
 */
export function useSpeech(engine: SpeechEngine, onText: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<Recognition | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const onTextRef = useRef(onText);
  useEffect(() => {
    onTextRef.current = onText;
  }, [onText]);

  // Capacité du navigateur : lue côté client seulement (faux pendant le rendu serveur).
  const supported = useSyncExternalStore(
    noSubscription,
    () =>
      engine === "browser"
        ? recognitionConstructor() !== null
        : typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia,
    () => false,
  );

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
  }, []);

  const startBrowser = useCallback(() => {
    const Ctor = recognitionConstructor();
    if (!Ctor) return setError("Votre navigateur ne sait pas écouter. Essayez Chrome, Edge ou Safari.");
    const recognition = new Ctor();
    recognition.lang = "fr-FR";
    recognition.continuous = false;
    recognition.interimResults = true;
    let finalText = "";
    recognition.onresult = (event) => {
      let partial = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) finalText += `${result[0].transcript} `;
        else partial += result[0].transcript;
      }
      setInterim(partial);
    };
    recognition.onerror = (event) => setError(BROWSER_ERRORS[event.error] ?? "Erreur de dictée.");
    recognition.onend = () => {
      setListening(false);
      setInterim("");
      if (finalText.trim() !== "") onTextRef.current(finalText.trim());
    };
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }, []);

  const startServer = useCallback(async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return setError("Le micro est refusé : autorisez-le dans le navigateur.");
    }
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      setListening(false);
      setBusy(true);
      try {
        const form = new FormData();
        form.append("file", new Blob(chunks, { type: recorder.mimeType }), "dictee.webm");
        const response = await fetch(`${API_URL}/assistant/transcribe`, { method: "POST", body: form });
        if (!response.ok) {
          const body = (await response.json().catch(() => ({}))) as { detail?: string };
          return setError(body.detail ?? `Erreur ${response.status}`);
        }
        const result = (await response.json()) as { text: string; placeholder: boolean };
        if (result.placeholder) {
          setError("Aucun service de transcription n'est configuré sur ce serveur.");
        } else if (result.text !== "") {
          onTextRef.current(result.text);
        } else {
          setError("Aucune parole détectée.");
        }
      } catch {
        setError("Impossible de joindre le service de transcription.");
      } finally {
        setBusy(false);
      }
    };
    recorderRef.current = recorder;
    recorder.start();
    setListening(true);
  }, []);

  const start = useCallback(() => {
    setError(null);
    if (engine === "browser") startBrowser();
    else void startServer();
  }, [engine, startBrowser, startServer]);

  useEffect(() => stop, [stop]);

  return { supported, listening, busy, interim, error, start, stop };
}
