import Link from "next/link";
import { useState } from "react";

import { LiveExercise } from "./LiveExercise";
import { InfoTip } from "./ProgramInfoTip";
import { DRAFT_BADGE_TEXT, NO_PROGRAM_TEXT, capsuleVideoSrc } from "./programFormat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ProgramCapsule = {
  id: string;
  zone: string;
  kind: string;
  status: "draft" | "validated";
  title: string;
  description: string;
  video_url: string;
  // Vrai quand la vidéo a été générée (python -m tms_vision.capsule_build).
  video_available?: boolean;
};

export type ProgramItem = {
  rank: number;
  zone: string;
  capsule: ProgramCapsule;
  reason: string;
  load: number;
  // « declared » : recommandation tirée des tâches saisies, sans mesure vidéo ;
  // « manual » : exercice ajouté par le praticien.
  basis?: "measured" | "declared" | "manual";
  // Explication affichée dans la bulle ⓘ : le mouvement du poste, puis ce que travaille l'exercice.
  why?: string[];
};

// Exercice du catalogue que le praticien peut ajouter à la main.
export type AvailableExercise = { id: string; zone: string; title: string; position: string };

export const SIZE_OPTIONS = [3, 5, 10];

// Réglages du programme : nombre d'exercices et, si `onSelectionChange` est fourni, choix des
// exercices un par un (retirer, ajouter, revenir au programme automatique).
export type ProgramControls = {
  size: number;
  busy?: boolean;
  onSizeChange: (size: number) => void;
  // null : programme automatique ; une liste : exercices choisis par le praticien.
  selection?: string[] | null;
  available?: AvailableExercise[];
  onSelectionChange?: (exerciseIds: string[] | null) => void;
};

const REGION_LABELS: Record<string, string> = {
  neck: "Cou",
  trunk: "Tronc",
  upper_arm: "Épaule / bras",
  lower_arm: "Avant-bras / coude",
  hand: "Main / poignet",
  foot: "Pied / cheville",
  head: "Tête",
  shoulder: "Épaule",
  hip: "Hanche",
  thigh: "Cuisse",
  lower_leg: "Jambe",
};

// Réservé à la correction du geste : l'API renvoie toujours une liste vide
// pour l'instant, et rien n'est affiché tant qu'elle l'est.
export type GestureCorrection = { title?: string; description?: string };

export function ProgramList({
  program,
  gestureCorrections = [],
  controls,
}: {
  program: ProgramItem[];
  gestureCorrections?: GestureCorrection[];
  controls?: ProgramControls;
}) {
  // Un seul mannequin 3D ouvert à la fois : les navigateurs limitent les contextes WebGL.
  const [openId, setOpenId] = useState<string | null>(null);

  const ids = program.map((item) => item.capsule.id);
  const customized = controls?.selection != null;
  const editable = controls?.onSelectionChange !== undefined;
  const addable = (controls?.available ?? []).filter((exercise) => !ids.includes(exercise.id));
  const addableByRegion = Object.entries(
    addable.reduce<Record<string, AvailableExercise[]>>((groups, exercise) => {
      (groups[exercise.zone] ??= []).push(exercise);
      return groups;
    }, {}),
  ).sort(([a], [b]) => (REGION_LABELS[a] ?? a).localeCompare(REGION_LABELS[b] ?? b, "fr"));

  if (program.length === 0 && gestureCorrections.length === 0 && !controls) {
    return (
      <p className="rounded border border-gray-300 bg-gray-50 p-3 text-sm text-gray-900">
        {NO_PROGRAM_TEXT}{" "}
        <Link href="/bibliotheque" className="text-blue-600 underline">
          Ouvrir la bibliothèque
        </Link>
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {(program.length > 0 || controls) && (
        <div className="rounded border border-blue-200 bg-blue-50 p-3 text-gray-900">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">
              Programme d&apos;étirements ({program.length} exercice{program.length > 1 ? "s" : ""}
              {customized ? ", sélection personnalisée" : ""})
            </h3>
            {controls && (
              <div className="flex flex-wrap items-center gap-1 text-xs" role="group" aria-label="Nombre d'exercices">
                <span className="mr-1">Nombre d&apos;exercices :</span>
                {SIZE_OPTIONS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    disabled={controls.busy || customized}
                    title={customized ? "Revenez au programme automatique pour changer le nombre." : undefined}
                    aria-pressed={!customized && controls.size === option}
                    onClick={() => controls.onSizeChange(option)}
                    className={`rounded border px-2 py-1 disabled:opacity-50 ${
                      !customized && controls.size === option
                        ? "border-blue-700 bg-blue-700 text-white"
                        : "border-blue-600 text-blue-800"
                    }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}
          </div>
          {program.length === 0 && (
            <p className="mt-2 text-sm">
              {customized ? "Aucun exercice sélectionné." : NO_PROGRAM_TEXT}
            </p>
          )}
          <ol className="mt-2 flex flex-col gap-3">
            {program.map((item) => {
              const videoSrc = capsuleVideoSrc(item.capsule, API_URL);
              return (
                <li key={item.capsule.id} className="flex gap-3">
                  <span className="font-semibold">{item.rank}.</span>
                  <div>
                    <p className="font-medium">
                      {item.capsule.title}
                      {item.why && item.why.length > 0 && <InfoTip lines={item.why} />}
                    </p>
                    {item.capsule.status === "draft" && (
                      <p className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
                        {DRAFT_BADGE_TEXT}
                      </p>
                    )}
                    <p className="text-sm text-gray-700">{item.capsule.description}</p>
                    <p className="text-xs text-gray-600">
                      {item.basis === "manual" && (
                        <span className="mr-1 rounded bg-violet-100 px-1.5 py-0.5 font-semibold text-violet-900">
                          Ajouté
                        </span>
                      )}
                      {item.basis === "declared" && (
                        <span className="mr-1 rounded bg-sky-100 px-1.5 py-0.5 font-semibold text-sky-900">
                          Sans vidéo
                        </span>
                      )}
                      {item.reason}
                    </p>
                    <button
                      type="button"
                      onClick={() => setOpenId(openId === item.capsule.id ? null : item.capsule.id)}
                      className="mt-2 rounded border border-blue-600 px-2 py-1 text-xs text-blue-800"
                    >
                      {openId === item.capsule.id ? "Masquer l'exercice" : "▶ Voir l'exercice"}
                    </button>
                    {editable && controls && (
                      <button
                        type="button"
                        disabled={controls.busy}
                        onClick={() =>
                          controls.onSelectionChange?.(ids.filter((id) => id !== item.capsule.id))
                        }
                        className="ml-2 mt-2 rounded border border-red-600 px-2 py-1 text-xs text-red-700 disabled:opacity-50"
                      >
                        Retirer
                      </button>
                    )}
                    {openId === item.capsule.id && <LiveExercise exerciseId={item.capsule.id} />}
                    {videoSrc && (
                      <video
                        controls
                        preload="metadata"
                        src={videoSrc}
                        className="mt-2 w-full max-w-sm rounded bg-black"
                      />
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          {editable && controls && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-blue-200 pt-3 text-sm">
              <label className="flex items-center gap-2">
                Ajouter un exercice
                <select
                  value=""
                  disabled={controls.busy}
                  onChange={(event) => {
                    if (event.target.value) controls.onSelectionChange?.([...ids, event.target.value]);
                  }}
                  className="rounded border p-1 text-sm"
                >
                  <option value="">Choisir...</option>
                  {addableByRegion.map(([region, exercises]) => (
                    <optgroup key={region} label={REGION_LABELS[region] ?? region}>
                      {exercises.map((exercise) => (
                        <option key={exercise.id} value={exercise.id}>
                          {exercise.title}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
              {customized && (
                <button
                  type="button"
                  disabled={controls.busy}
                  onClick={() => controls.onSelectionChange?.(null)}
                  className="rounded border border-blue-600 px-2 py-1 text-xs text-blue-800 disabled:opacity-50"
                >
                  Revenir au programme automatique
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {gestureCorrections.length > 0 && (
        <div className="rounded border border-green-200 bg-green-50 p-3 text-gray-900">
          <h3 className="text-sm font-semibold">Correction du geste</h3>
          <ul className="mt-2 flex flex-col gap-2">
            {gestureCorrections.map((correction, index) => (
              <li key={index}>
                <p className="font-medium">{correction.title}</p>
                <p className="text-sm text-gray-700">{correction.description}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
