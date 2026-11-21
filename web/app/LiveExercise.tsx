"use client";

import { useEffect, useState } from "react";

import { ExercisePlayer } from "./bibliotheque/ExercisePlayer";
import { useI18n } from "./i18n/I18nProvider";
import { Exercise } from "./exercisePose";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Loaded = { id: string; exercise: Exercise | null };

// Joue l'exercice en direct dans le navigateur (même mannequin 3D que la bibliothèque) : rien à
// générer ni à stocker, contrairement aux vidéos de capsule_build.
export function LiveExercise({ exerciseId }: { exerciseId: string }) {
  const { t } = useI18n();
  // État porteur de l'id auquel il correspond (même motif que AnalysisResult.tsx).
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/exercises/${encodeURIComponent(exerciseId)}`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Exercise>;
      })
      .then((exercise) => {
        if (!cancelled) setLoaded({ id: exerciseId, exercise });
      })
      .catch(() => {
        if (!cancelled) setLoaded({ id: exerciseId, exercise: null });
      });
    return () => {
      cancelled = true;
    };
  }, [exerciseId]);

  if (loaded === null || loaded.id !== exerciseId) {
    return <p className="mt-2 text-xs text-gray-600">{t("live.loading")}</p>;
  }
  if (loaded.exercise === null) {
    return <p className="mt-2 text-xs text-red-700">{t("live.error")}</p>;
  }
  return (
    <div className="mt-2 w-full max-w-sm">
      <ExercisePlayer exercise={loaded.exercise} />
    </div>
  );
}
