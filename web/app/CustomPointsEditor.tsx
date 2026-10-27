"use client";

import { useEffect, useRef, useState } from "react";

import { CustomPoint, MAX_CUSTOM_POINTS, clickToNormalized, defaultPointName } from "./poseModels";

type CustomPointsEditorProps = {
  file: File;
  points: CustomPoint[];
  referenceTime: number;
  onChange: (points: CustomPoint[], referenceTime: number) => void;
  disabled?: boolean;
};

// Durée d'un enregistrement de la caméra (MediaRecorder ne renseigne pas toujours la durée du fichier).
const FALLBACK_DURATION_SECONDS = 30;

/**
 * Pose de points personnalisés sur une image de la vidéo choisie : on règle l'instant avec le
 * curseur, puis on clique sur l'outil, la caisse, la zone... Tous les points appartiennent à la même
 * image de référence (le suivi part de là, vers la suite de la vidéo) : l'instant est donc figé dès
 * le premier point, jusqu'à ce qu'on les efface.
 */
export function CustomPointsEditor({ file, points, referenceTime, onChange, disabled }: CustomPointsEditorProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [duration, setDuration] = useState(FALLBACK_DURATION_SECONDS);
  const [time, setTime] = useState(referenceTime);
  const [loadError, setLoadError] = useState(false);
  const locked = points.length > 0;

  // La vidéo locale est lue depuis le fichier choisi : aucun envoi avant le clic sur « Analyser ».
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const url = URL.createObjectURL(file);
    video.src = url;
    return () => {
      URL.revokeObjectURL(url);
      video.removeAttribute("src");
      video.load();
    };
  }, [file]);

  function seek(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    setTime(seconds);
  }

  function handlePlace(event: React.MouseEvent<HTMLDivElement>) {
    if (disabled || points.length >= MAX_CUSTOM_POINTS) return;
    const position = clickToNormalized(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect());
    if (!position) return;
    // L'instant de référence est celui de l'image affichée au moment du premier clic. Le décodeur
    // affiche la dernière image dont l'instant ne dépasse pas celui demandé : le serveur démarre le
    // suivi sur cette image ou la suivante (au plus une image d'écart).
    const at = points.length === 0 ? (videoRef.current?.currentTime ?? time) : referenceTime;
    onChange([...points, { name: defaultPointName(points), ...position }], at);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative w-full overflow-hidden rounded-lg bg-black">
        <video
          ref={videoRef}
          muted
          playsInline
          preload="auto"
          className="block h-auto w-full"
          onLoadedMetadata={(event) => {
            const d = event.currentTarget.duration;
            setDuration(Number.isFinite(d) && d > 0 ? d : FALLBACK_DURATION_SECONDS);
            setLoadError(false);
          }}
          onError={() => setLoadError(true)}
        />
        <div
          role="button"
          tabIndex={0}
          aria-label="Image de référence : cliquez pour poser un point"
          onClick={handlePlace}
          className={`absolute inset-0 ${disabled ? "cursor-not-allowed" : "cursor-crosshair"}`}
        >
          {points.map((point, index) => (
            <span
              key={`${index}-${point.x}-${point.y}`}
              className="pointer-events-none absolute flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-yellow-300 bg-yellow-300/30 text-xs font-bold text-yellow-200"
              style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }}
            >
              {index + 1}
            </span>
          ))}
        </div>
      </div>

      {loadError && (
        <p className="text-sm text-red-600">
          Ce navigateur ne peut pas afficher cette vidéo : impossible de placer les points ici.
        </p>
      )}

      <label className="flex flex-col gap-1 text-sm">
        Image de référence : {time.toFixed(2).replace(".", ",")} s
        <input
          type="range"
          min={0}
          max={duration}
          step={0.05}
          value={Math.min(time, duration)}
          disabled={disabled || locked}
          onChange={(event) => seek(Number(event.target.value))}
        />
        {locked && (
          <span className="text-xs text-gray-600">
            L&apos;image est figée tant que des points sont posés : effacez-les pour en choisir une autre.
          </span>
        )}
      </label>

      <p className="text-xs text-gray-600">
        Cliquez sur l&apos;image pour poser un point (jusqu&apos;à {MAX_CUSTOM_POINTS}). Le suivi part de cette image et
        va vers la suite de la vidéo.
      </p>

      {points.length > 0 && (
        <ul className="flex flex-col gap-2">
          {points.map((point, index) => (
            <li key={index} className="flex items-center gap-2">
              <span className="w-5 text-sm text-gray-600">{index + 1}</span>
              <input
                type="text"
                value={point.name}
                maxLength={60}
                disabled={disabled}
                aria-label={`Nom du point ${index + 1}`}
                onChange={(event) =>
                  onChange(
                    points.map((p, i) => (i === index ? { ...p, name: event.target.value } : p)),
                    referenceTime,
                  )
                }
                className="min-w-0 flex-1 rounded border p-1 text-sm"
              />
              <button
                type="button"
                disabled={disabled}
                aria-label={`Supprimer le point ${index + 1}`}
                onClick={() => onChange(points.filter((_, i) => i !== index), referenceTime)}
                className="rounded border px-2 py-1 text-sm"
              >
                Supprimer
              </button>
            </li>
          ))}
          <li>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange([], referenceTime)}
              className="rounded border px-2 py-1 text-sm"
            >
              Effacer tous les points
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}
