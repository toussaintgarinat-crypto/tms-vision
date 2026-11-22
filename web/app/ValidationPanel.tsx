"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ExercisePlayer } from "./bibliotheque/ExercisePlayer";
import { Exercise } from "./exercisePose";
import { useI18n } from "./i18n/I18nProvider";
import { ValidationBadge, ValidationLabel } from "./ValidationBadge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SPEEDS = [1, 2, 3, 4];

type HistoryRow = {
  version: number;
  osteo_name: string;
  kind: "validate" | "withdraw";
  recorded_at: string;
};

type ValidationState = ValidationLabel & {
  formulas: Record<string, string>;
  max_playback_speed: number;
  can_validate: boolean;
  can_withdraw: boolean;
  history: HistoryRow[];
};

// Écran de validation : l'animation et le texte côte à côte. La case n'est cochable qu'après avoir
// lancé l'animation en entier ; la formule cochée est envoyée et enregistrée avec la validation.
// Le serveur refuse de toute façon un compte sans le rôle ostéopathe.
export function ValidationPanel({
  exerciseId,
  onClose,
  onChanged,
}: {
  exerciseId: string;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const { t, locale, tag } = useI18n();
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [state, setState] = useState<ValidationState | null>(null);
  const [failed, setFailed] = useState(false);
  const [played, setPlayed] = useState(false);
  const [speed, setSpeed] = useState(1);
  // Vitesse la plus haute utilisée pendant la lecture : c'est elle qui est enregistrée.
  const topSpeedRef = useRef(1);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [exerciseResponse, stateResponse] = await Promise.all([
        fetch(`${API_URL}/exercises/${encodeURIComponent(exerciseId)}`),
        fetch(`${API_URL}/exercises/${encodeURIComponent(exerciseId)}/validation`),
      ]);
      if (!exerciseResponse.ok || !stateResponse.ok) throw new Error("load");
      setExercise((await exerciseResponse.json()) as Exercise);
      setState((await stateResponse.json()) as ValidationState);
    } catch {
      setFailed(true);
    }
  }, [exerciseId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const handlePlayed = useCallback(() => setPlayed(true), []);
  const chooseSpeed = (value: number) => {
    setSpeed(value);
    if (!played) topSpeedRef.current = Math.max(topSpeedRef.current, value);
  };

  async function send(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/exercises/${encodeURIComponent(exerciseId)}/${path}`, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(typeof problem?.detail === "string" ? problem.detail : t("validation.error"));
        return;
      }
      setChecked(false);
      await load();
      onChanged?.();
    } catch {
      setError(t("validation.error"));
    } finally {
      setBusy(false);
    }
  }

  if (failed) return <p className="mt-2 text-sm text-red-700">{t("validation.loadFailed")}</p>;
  if (!exercise || !state) return <p className="mt-2 text-sm text-gray-600">{t("live.loading")}</p>;

  const formula = state.formulas[locale] ?? Object.values(state.formulas)[0];
  const canConfirm = played && checked && !busy;

  return (
    <section className="mt-3 rounded border border-emerald-300 bg-white p-3 text-gray-900" aria-label={t("validation.title")}>
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold">{t("validation.title")}</h4>
        <button type="button" onClick={onClose} className="rounded border px-2 py-0.5 text-xs">
          {t("validation.close")}
        </button>
      </div>
      <p className="mt-1 text-xs">
        <ValidationBadge label={state} />
      </p>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <ExercisePlayer exercise={exercise} onPlayedInFull={handlePlayed} speed={speed} />
          <div className="mt-1 flex items-center gap-1 text-xs" role="group" aria-label={t("validation.speed")}>
            <span className="mr-1">{t("validation.speed")}</span>
            {SPEEDS.filter((value) => value <= state.max_playback_speed).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={speed === value}
                onClick={() => chooseSpeed(value)}
                className={`rounded border px-2 py-0.5 ${
                  speed === value ? "border-emerald-700 bg-emerald-700 text-white" : "border-emerald-700 text-emerald-800"
                }`}
              >
                {value}x
              </button>
            ))}
          </div>
          <p className={`mt-1 text-xs ${played ? "text-emerald-800" : "text-gray-600"}`}>
            {played
              ? t("validation.playedDone")
              : t("validation.playedTodo", { seconds: Math.ceil(exercise.duration_seconds / speed) })}
          </p>
        </div>
        <div className="text-sm">
          <h5 className="font-semibold">{exercise.title}</h5>
          <p className="mt-1">{exercise.description}</p>
          {(exercise as Exercise & { benefit?: string }).benefit && (
            <p className="mt-1 text-gray-700">{(exercise as Exercise & { benefit?: string }).benefit}</p>
          )}
          <ol className="mt-2 flex list-decimal flex-col gap-1 pl-5">
            {exercise.instructions.map((instruction) => (
              <li key={instruction.t}>{instruction.text}</li>
            ))}
          </ol>
        </div>
      </div>

      {state.can_validate && (
        <div className="mt-3 flex flex-col gap-2 border-t pt-3">
          <label className={`flex items-start gap-2 text-sm ${played ? "" : "opacity-50"}`}>
            <input
              type="checkbox"
              checked={checked}
              disabled={!played || busy}
              onChange={(event) => setChecked(event.target.checked)}
              className="mt-1"
            />
            {formula}
          </label>
          <button
            type="button"
            disabled={!canConfirm}
            onClick={() =>
              send("validate", {
                fingerprint: state.fingerprint,
                formula,
                animation_completed: played,
                playback_speed: topSpeedRef.current,
              })
            }
            className="self-start rounded bg-emerald-700 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
          >
            {t("validation.confirm")}
          </button>
        </div>
      )}
      {state.can_withdraw && (
        <button
          type="button"
          disabled={busy}
          onClick={() => send("withdraw-validation")}
          className="mt-3 rounded border border-red-600 px-3 py-1 text-sm text-red-700 disabled:opacity-50"
        >
          {t("validation.withdraw")}
        </button>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
      {state.history.length > 0 && (
        <details className="mt-3 text-xs text-gray-700">
          <summary className="cursor-pointer font-semibold">{t("validation.history")}</summary>
          <ul className="mt-1 flex flex-col gap-0.5">
            {state.history.map((row, index) => (
              <li key={index}>
                {t(row.kind === "validate" ? "validation.history.validate" : "validation.history.withdraw", {
                  name: row.osteo_name,
                  version: row.version,
                  date: new Date(row.recorded_at).toLocaleString(tag),
                })}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
