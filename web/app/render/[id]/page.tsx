"use client";

import { Canvas } from "@react-three/fiber";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { ExerciseAvatar, ExerciseAvatarApi } from "../../ExerciseAvatar";
import { Exercise, activeInstruction } from "../../exercisePose";
import { MUSCLE_MODEL_CREDIT } from "../../muscleModel";

// Page de rendu des vidéos d'exercice, pilotée par scripts/render-exercise.mjs :
// elle n'est pas destinée à être ouverte par un utilisateur. Contrat :
//   window.__tmsRender.load(exercise)  -> Promise<void>  (modèle chargé, prêt à rendre)
//   window.__tmsRender.setTime(t)      -> Promise<void>  (pose + rendu synchrones à l'instant t)
//   window.__tmsRender.duration        -> number
// Rien ne dépend de l'horloge : chaque image est rendue à la demande, à l'instant demandé.

export const STAGE_SIZE = 640;

declare global {
  interface Window {
    __tmsRender?: {
      load: (exercise: Exercise) => Promise<void>;
      setTime: (t: number) => Promise<void>;
      readonly duration: number;
    };
  }
}

function formatRemaining(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

const OVERLAY_TEXT = "#111827";

export default function RenderPage() {
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [time, setTime] = useState(0);
  const exerciseRef = useRef<Exercise | null>(null);
  const apiRef = useRef<ExerciseAvatarApi | null>(null);
  const waitingForApi = useRef<(() => void)[]>([]);

  const handleReady = useCallback((api: ExerciseAvatarApi) => {
    apiRef.current = api;
    waitingForApi.current.splice(0).forEach((resolve) => resolve());
  }, []);

  useEffect(() => {
    window.__tmsRender = {
      async load(next) {
        exerciseRef.current = next;
        flushSync(() => {
          setExercise(next);
          setTime(0);
        });
        if (!apiRef.current) {
          await new Promise<void>((resolve) => waitingForApi.current.push(resolve));
        }
      },
      async setTime(t) {
        const current = exerciseRef.current;
        if (!current || !apiRef.current) {
          throw new Error("setTime appelé avant load().");
        }
        flushSync(() => setTime(t));
        apiRef.current.renderAt(current, t);
      },
      get duration() {
        return exerciseRef.current?.duration_seconds ?? 0;
      },
    };
    return () => {
      delete window.__tmsRender;
    };
  }, []);

  const instruction = exercise ? activeInstruction(exercise, time) : null;

  return (
    <div
      id="stage"
      style={{
        position: "relative",
        width: STAGE_SIZE,
        height: STAGE_SIZE,
        overflow: "hidden",
        background: "#EEF1F4",
        color: OVERLAY_TEXT,
        fontFamily: "Arial, Helvetica, sans-serif",
      }}
    >
      <Canvas
        frameloop="never"
        dpr={1}
        camera={{ fov: 40, near: 0.1, far: 50 }}
        gl={{ antialias: true }}
        style={{ position: "absolute", inset: 0 }}
      >
        <ExerciseAvatar onReady={handleReady} />
      </Canvas>

      {exercise && (
        <>
          <div style={{ position: "absolute", top: 16, left: 20, right: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div style={{ fontSize: 26, fontWeight: 700 }}>{exercise.title}</div>
              <div style={{ fontSize: 22, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                {formatRemaining(exercise.duration_seconds - time)}
              </div>
            </div>
            {exercise.status === "draft" && (
              <div
                style={{
                  display: "inline-block",
                  marginTop: 6,
                  padding: "2px 10px",
                  borderRadius: 4,
                  background: "#FDE68A",
                  fontSize: 14,
                  fontWeight: 600,
                }}
              >
                Brouillon — à valider par l&apos;ostéopathe
              </div>
            )}
          </div>

          {instruction && (
            <div
              style={{
                position: "absolute",
                left: 20,
                right: 20,
                bottom: 40,
                padding: "10px 14px",
                borderRadius: 8,
                background: "rgba(255, 255, 255, 0.88)",
                fontSize: 21,
                lineHeight: 1.3,
              }}
            >
              {instruction.text}
            </div>
          )}

          <div
            style={{
              position: "absolute",
              left: 20,
              right: 20,
              bottom: 12,
              fontSize: 11,
              color: "#4B5563",
            }}
          >
            {MUSCLE_MODEL_CREDIT}
          </div>
        </>
      )}
    </div>
  );
}
