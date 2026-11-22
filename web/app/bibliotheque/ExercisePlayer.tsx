"use client";

import { Canvas } from "@react-three/fiber";
import { useCallback, useEffect, useRef, useState } from "react";
import { ExerciseAvatar, ExerciseAvatarApi } from "../ExerciseAvatar";
import { Exercise, activeInstruction } from "../exercisePose";
import { useI18n } from "../i18n/I18nProvider";

// Un seul canvas WebGL pour tout le carrousel : le mannequin rejoue l'exercice de la carte
// affichée en boucle, au rythme réel (les navigateurs limitent le nombre de contextes WebGL, un
// canvas par carte les épuiserait).
export function ExercisePlayer({
  exercise,
  onPlayedInFull,
}: {
  exercise: Exercise;
  // Appelé une fois, quand l'animation a été jouée en entier (écran de validation).
  onPlayedInFull?: () => void;
}) {
  const { t } = useI18n();
  const apiRef = useRef<ExerciseAvatarApi | null>(null);
  const timeRef = useRef(0);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(true);
  const [shownSecond, setShownSecond] = useState(0);
  const playedRef = useRef(0);
  const doneRef = useRef(false);

  const handleReady = useCallback((api: ExerciseAvatarApi) => {
    apiRef.current = api;
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    timeRef.current = 0;
    playedRef.current = 0;
    doneRef.current = false;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      if (playing) {
        const step = (now - last) / 1000;
        timeRef.current = (timeRef.current + step) % exercise.duration_seconds;
        playedRef.current += step;
        if (!doneRef.current && playedRef.current >= exercise.duration_seconds) {
          doneRef.current = true;
          onPlayedInFull?.();
        }
      }
      last = now;
      apiRef.current?.renderAt(exercise, timeRef.current);
      const second = Math.floor(timeRef.current);
      setShownSecond((previous) => (previous === second ? previous : second));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [exercise, ready, playing, onPlayedInFull]);

  const instruction = activeInstruction(exercise, shownSecond);
  const remaining = Math.max(0, Math.ceil(exercise.duration_seconds - shownSecond));

  return (
    <div>
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-[#EEF1F4]">
        <Canvas
          frameloop="never"
          dpr={[1, 2]}
          camera={{ fov: 40, near: 0.1, far: 50 }}
          gl={{ antialias: true }}
          style={{ position: "absolute", inset: 0 }}
        >
          <ExerciseAvatar onReady={handleReady} />
        </Canvas>
        {!ready && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">
            {t("player.loading")}
          </div>
        )}
        <button
          type="button"
          onClick={() => setPlaying((value) => !value)}
          aria-label={playing ? t("player.pauseLabel") : t("player.resumeLabel")}
          className="absolute right-2 top-2 rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-zinc-800 shadow hover:bg-white"
        >
          {playing ? t("player.pause") : t("player.play")}
        </button>
        <div className="absolute left-2 top-2 rounded-full bg-white/90 px-2 py-1 text-xs tabular-nums text-zinc-800 shadow">
          {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}
        </div>
      </div>
      <p className="mt-2 min-h-12 text-sm text-zinc-700 dark:text-zinc-300" aria-live="off">
        {instruction?.text ?? ""}
      </p>
      <p className="text-[10px] text-zinc-400">{t("muscle.credit")}</p>
    </div>
  );
}
