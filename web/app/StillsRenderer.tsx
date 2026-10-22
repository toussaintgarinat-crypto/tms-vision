"use client";

import { Canvas } from "@react-three/fiber";
import { useCallback, useRef } from "react";

import { ExerciseAvatar, ExerciseAvatarApi } from "./ExerciseAvatar";
import { Exercise } from "./exercisePose";
import { StillStep, stillSteps } from "./exerciseStills";

export type Still = StillStep & { image: string };
export type ExerciseStills = Record<string, Still[]>;

// Rend, hors de l'écran, une image fixe par étape de chaque exercice (voir stillSteps) avec le
// mannequin 3D, puis les renvoie. Un seul canvas WebGL pour tous les exercices. À remonter (clé)
// quand la liste d'exercices change.
export function StillsRenderer({
  exercises,
  onDone,
}: {
  exercises: Exercise[];
  onDone: (stills: ExerciseStills) => void;
}) {
  const startedRef = useRef(false);

  const handleReady = useCallback(
    (api: ExerciseAvatarApi) => {
      if (startedRef.current) return;
      startedRef.current = true;
      const stills: ExerciseStills = {};
      for (const exercise of exercises) {
        stills[exercise.id] = stillSteps(exercise).map((step) => {
          api.renderAt(exercise, step.t);
          return { ...step, image: api.snapshot() };
        });
      }
      onDone(stills);
    },
    [exercises, onDone],
  );

  return (
    <div aria-hidden style={{ position: "fixed", left: -10000, top: 0, width: 480, height: 480 }}>
      <Canvas
        frameloop="never"
        dpr={1}
        camera={{ fov: 40, near: 0.1, far: 50 }}
        gl={{ antialias: true, preserveDrawingBuffer: true }}
        style={{ position: "absolute", inset: 0 }}
      >
        <ExerciseAvatar onReady={handleReady} />
      </Canvas>
    </div>
  );
}
