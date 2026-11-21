"use client";

import { useEffect, useMemo, useState } from "react";
import type { Exercise } from "../exercisePose";
import { useI18n } from "../i18n/I18nProvider";
import { ExerciseStills, Still, StillsRenderer } from "../StillsRenderer";
import { ExercisePlayer } from "./ExercisePlayer";
import { API_URL } from "./library";

type Mode = "images" | "animation" | "video";
const MODES: Mode[] = ["images", "animation", "video"];

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
  const { t } = useI18n();
  const [position, setPosition] = useState(0);
  const count = steps.length;
  if (count === 0) return <p className="text-sm text-zinc-500">{t("media.noImages")}</p>;
  const step = steps[Math.min(position, count - 1)];
  const go = (delta: number) => setPosition((previous) => (previous + delta + count) % count);
  return (
    <div>
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-[#EEF1F4]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={step.image} alt={t("media.stillAlt", { title, step: position + 1 })} className="h-full w-full object-contain" />
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => go(-1)}
          aria-label={t("media.previousStep")}
          className="rounded-full border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
        >
          ←
        </button>
        <span className="text-xs tabular-nums text-zinc-500">
          {t("media.step", { step: position + 1, total: count })}
        </span>
        <button
          type="button"
          onClick={() => go(1)}
          aria-label={t("media.nextStep")}
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
  const { t } = useI18n();
  const [mode, setMode] = useState<Mode>("images");
  const [stills, setStills] = useState<ExerciseStills>({});
  const videoAvailable = useVideoAvailable(exercise.id);

  const modes = MODES.filter((value) => value !== "video" || videoAvailable);
  const active: Mode = modes.includes(mode) ? mode : "images";
  const toRender = useMemo(() => [exercise], [exercise]);
  const exerciseStills = stills[exercise.id];

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1" role="group" aria-label={t("media.group")}>
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
            {t(`media.mode.${value}`)}
          </button>
        ))}
      </div>

      {active === "images" &&
        (exerciseStills ? (
          <StillsCarousel key={exercise.id} steps={exerciseStills} title={exercise.title} />
        ) : (
          <>
            <p className="flex aspect-square w-full items-center justify-center rounded-lg bg-[#EEF1F4] text-sm text-zinc-500">
              {t("media.preparingImages")}
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
