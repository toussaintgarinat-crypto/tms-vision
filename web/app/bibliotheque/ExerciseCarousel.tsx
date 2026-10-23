"use client";

import type { KeyboardEvent, ReactNode } from "react";
import { POSITION_LABELS, type Exercise } from "../exercisePose";
import { ExerciseMedia } from "./ExerciseMedia";

type Props = {
  exercises: Exercise[];
  index: number;
  onIndexChange: (index: number) => void;
  // Contenu propre à l'écran (case « ajouter à l'envoi », note du praticien…), sous la carte.
  footer?: (exercise: Exercise) => ReactNode;
};

export function ExerciseCarousel({ exercises, index, onIndexChange, footer }: Props) {
  if (exercises.length === 0) return null;
  const current = Math.min(index, exercises.length - 1);
  const exercise = exercises[current];
  const go = (delta: number) =>
    onIndexChange((current + delta + exercises.length) % exercises.length);

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "ArrowLeft") go(-1);
    if (event.key === "ArrowRight") go(1);
  };

  return (
    <section
      aria-roledescription="carrousel"
      aria-label="Exercices"
      onKeyDown={onKeyDown}
      className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-700 dark:bg-zinc-900"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => go(-1)}
          aria-label="Exercice précédent"
          className="rounded-full border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
        >
          ←
        </button>
        <span className="text-sm tabular-nums text-zinc-500">
          {current + 1} / {exercises.length}
        </span>
        <button
          type="button"
          onClick={() => go(1)}
          aria-label="Exercice suivant"
          className="rounded-full border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
        >
          →
        </button>
      </div>

      <h2 className="text-lg font-semibold">{exercise.title}</h2>
      {exercise.position && exercise.position !== "standing" && (
        <span className="mr-2 mt-1 inline-block rounded bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-950">
          {POSITION_LABELS[exercise.position]}
        </span>
      )}
      {exercise.status === "draft" && (
        <span className="mt-1 inline-block rounded bg-amber-200 px-2 py-0.5 text-xs font-semibold text-amber-950">
          Brouillon — à valider par un professionnel de santé
        </span>
      )}
      <p className="mb-3 mt-2 text-sm text-zinc-600 dark:text-zinc-400">{exercise.description}</p>

      <ExerciseMedia exercise={exercise} />

      {footer && <div className="mt-3 border-t border-zinc-200 pt-3 dark:border-zinc-700">{footer(exercise)}</div>}

      <ol className="mt-3 flex flex-wrap gap-1.5" aria-label="Choisir un exercice">
        {exercises.map((item, position) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onIndexChange(position)}
              aria-current={position === current}
              className={`rounded-full border px-2.5 py-1 text-xs ${
                position === current
                  ? "border-blue-600 bg-blue-600 text-white"
                  : "border-zinc-300 hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
              }`}
            >
              {item.title}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
