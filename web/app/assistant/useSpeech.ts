"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { useI18n } from "../i18n/I18nProvider";
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

// Clé de message de chaque erreur de la dictée du navigateur.
const BROWSER_ERRORS: Record<string, string> = {
  "not-allowed": "speech.error.micDenied",
  "service-not-allowed": "speech.error.micDenied",
  "no-speech": "speech.error.noSpeech",
  "audio-capture": "speech.error.noMic",
  network: "speech.error.network",
};

/**
 * Écoute vocale avec deux moteurs : la dictée du navigateur, ou l'enregistrement envoyé à
 * POST /assistant/transcribe (transcription souveraine). `onText` reçoit le texte final.
 */
export function useSpeech(engine: SpeechEngine, onText: (text: string) => void) {
  const { t, tag } = useI18n();
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
    if (!Ctor) return setError(t("speech.error.unsupported"));
    const recognition = new Ctor();
    recognition.lang = tag;
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
    recognition.onerror = (event) => setError(t(BROWSER_ERRORS[event.error] ?? "speech.error.generic"));
    recognition.onend = () => {
      setListening(false);
      setInterim("");
      if (finalText.trim() !== "") onTextRef.current(finalText.trim());
    };
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }, [t, tag]);

  const startServer = useCallback(async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return setError(t("speech.error.micDenied"));
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
          return setError(body.detail ?? t("bilans.error.httpStatus", { status: response.status }));
        }
        const result = (await response.json()) as { text: string; placeholder: boolean };
        if (result.placeholder) {
          setError(t("speech.error.noTranscription"));
        } else if (result.text !== "") {
          onTextRef.current(result.text);
        } else {
          setError(t("speech.error.noSpeech"));
        }
      } catch {
        setError(t("speech.error.transcriptionUnreachable"));
      } finally {
        setBusy(false);
      }
    };
    recorderRef.current = recorder;
    recorder.start();
    setListening(true);
  }, [t]);

  const start = useCallback(() => {
    setError(null);
    if (engine === "browser") startBrowser();
    else void startServer();
  }, [engine, startBrowser, startServer]);

  useEffect(() => stop, [stop]);

  return { supported, listening, busy, interim, error, start, stop };
}
