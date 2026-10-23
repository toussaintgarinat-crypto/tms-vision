"use client";

import { useEffect, useMemo, useState } from "react";
import type { Exercise } from "../exercisePose";
import { ExerciseStills, Still, StillsRenderer } from "../StillsRenderer";
import { ExercisePlayer } from "./ExercisePlayer";
import { API_URL } from "./library";

type Mode = "images" | "animation" | "video";
const MODE_LABELS: Record<Mode, string> = {
  images: "Images",
  animation: "Animation 3D",
  video: "Vidéo",
};

// La vidéo d'un exercice n'existe que si elle a été générée (capsule_build) : on sonde le premier
// octet pour savoir s'il faut proposer l'onglet « Vidéo ».
function useVideoAvailable(exerciseId: string): boolean {
  const [known, setKnown] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (exerciseId in known) return;
    let cancelled = false;
    fetch(`${API_URL}/capsules/${encodeURIComponent(exerciseId)}/video`, { headers: { Range: "bytes=0-0" } })
      .then((response) => response.ok)
      .catch(() => false)
      .then((available) => {
        if (!cancelled) setKnown((previous) => ({ ...previous, [exerciseId]: available }));
      });
    return () => {
      cancelled = true;
    };
  }, [exerciseId, known]);
  return known[exerciseId] ?? false;
}

function StillsCarousel({ steps, title }: { steps: Still[]; title: string }) {
  const [position, setPosition] = useState(0);
  const count = steps.length;
  if (count === 0) return <p className="text-sm text-zinc-500">Aucune image pour cet exercice.</p>;
  const step = steps[Math.min(position, count - 1)];
  const go = (delta: number) => setPosition((previous) => (previous + delta + count) % count);
  return (
    <div>
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-[#EEF1F4]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={step.image} alt={`${title}, étape ${position + 1}`} className="h-full w-full object-contain" />
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => go(-1)}
          aria-label="Étape précédente"
          className="rounded-full border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
        >
          ←
        </button>
        <span className="text-xs tabular-nums text-zinc-500">
          Étape {position + 1} / {count}
        </span>
        <button
          type="button"
          onClick={() => go(1)}
          aria-label="Étape suivante"
          className="rounded-full border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
        >
          →
        </button>
      </div>
      <p className="mt-2 min-h-12 text-sm text-zinc-700 dark:text-zinc-300">{step.text}</p>
    </div>
  );
}

// Média d'un exercice, au choix : images fixes par étape (par défaut, plus rapide à contrôler),
// animation 3D en boucle ou vidéo générée quand elle existe.
export function ExerciseMedia({ exercise }: { exercise: Exercise }) {
  const [mode, setMode] = useState<Mode>("images");
  const [stills, setStills] = useState<ExerciseStills>({});
  const videoAvailable = useVideoAvailable(exercise.id);

  const modes = (Object.keys(MODE_LABELS) as Mode[]).filter((value) => value !== "video" || videoAvailable);
  const active: Mode = modes.includes(mode) ? mode : "images";
  const toRender = useMemo(() => [exercise], [exercise]);
  const exerciseStills = stills[exercise.id];

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1" role="group" aria-label="Affichage de l'exercice">
        {modes.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setMode(value)}
            aria-pressed={active === value}
            className={`rounded-full border px-3 py-1 text-xs ${
              active === value ? "border-blue-600 bg-blue-600 text-white" : "border-zinc-300 dark:border-zinc-600"
            }`}
          >
            {MODE_LABELS[value]}
          </button>
        ))}
      </div>

      {active === "images" &&
        (exerciseStills ? (
          <StillsCarousel key={exercise.id} steps={exerciseStills} title={exercise.title} />
        ) : (
          <>
            <p className="flex aspect-square w-full items-center justify-center rounded-lg bg-[#EEF1F4] text-sm text-zinc-500">
              Préparation des images…
            </p>
            <StillsRenderer
              key={exercise.id}
              exercises={toRender}
              onDone={(result) => setStills((previous) => ({ ...previous, ...result }))}
            />
          </>
        ))}
      {active === "animation" && <ExercisePlayer exercise={exercise} />}
      {active === "video" && (
        <video
          key={exercise.id}
          controls
          preload="metadata"
          src={`${API_URL}/capsules/${encodeURIComponent(exercise.id)}/video`}
          className="aspect-square w-full rounded-lg bg-black"
        />
      )}
    </div>
  );
}
