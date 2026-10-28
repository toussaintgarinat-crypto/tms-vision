"use client";

import { useEffect, useState } from "react";

import { CustomPointsEditor } from "./CustomPointsEditor";
import { WholebodySetup } from "./WholebodySetup";
import {
  POSE_CHOICES,
  PoseChoice,
  PoseSettings,
  WHOLEBODY_POLL_MS,
  WholebodyStatus,
  applyChoice,
  expectedKeypointCount,
  isWholebody,
  wholebodySelectable,
  wholebodyState,
} from "./poseModels";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type PoseModelPickerProps = {
  settings: PoseSettings;
  onChange: (settings: PoseSettings) => void;
  /** Vidéo choisie : sert d'image de référence pour les points personnalisés. */
  file: File;
  disabled?: boolean;
};

export function PoseModelPicker({ settings, onChange, file, disabled }: PoseModelPickerProps) {
  const [status, setStatus] = useState<WholebodyStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const state = wholebodyState(status);

  // État du modèle whole-body (paquets, poids téléchargés, mode). Illisible : rien n'est bloqué,
  // le serveur refusera proprement (422, message en français) une option indisponible.
  async function refreshStatus() {
    try {
      const response = await fetch(`${API_URL}/pose-models/wholebody`);
      if (response.ok) setStatus((await response.json()) as WholebodyStatus);
    } catch {
      // réseau indisponible : on garde l'état précédent
    }
  }

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/pose-models/wholebody`)
      .then((response) => (response.ok ? (response.json() as Promise<WholebodyStatus>) : null))
      .then((data) => {
        if (!cancelled && data) setStatus(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Pendant le téléchargement des poids (plusieurs minutes), on relit l'état régulièrement.
  useEffect(() => {
    if (state !== "downloading") return;
    const timer = setInterval(() => void refreshStatus(), WHOLEBODY_POLL_MS);
    return () => clearInterval(timer);
  }, [state]);

  async function send(path: string, init: RequestInit) {
    setBusy(true);
    try {
      const response = await fetch(`${API_URL}${path}`, init);
      if (response.ok) setStatus((await response.json()) as WholebodyStatus);
      else await refreshStatus();
    } catch {
      await refreshStatus();
    } finally {
      setBusy(false);
    }
  }

  const install = () => send("/pose-models/wholebody/install", { method: "POST" });
  const changeMode = (mode: string) =>
    send("/pose-models/wholebody", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });

  const wholebody = isWholebody(settings);

  function choose(choice: PoseChoice) {
    onChange(applyChoice(settings, choice));
  }

  return (
    <fieldset className="flex flex-col gap-3" disabled={disabled}>
      <legend className="mb-1 font-medium">Modèle de pose</legend>

      <div className="flex flex-col gap-2">
        {POSE_CHOICES.map((choice) => {
          const isWholebodyChoice = choice.value === "rtmpose_wholebody";
          const unavailable = isWholebodyChoice && !wholebodySelectable(state);
          return (
            <div key={choice.value} className="flex flex-col gap-2">
              <label
                className={`flex items-start gap-2 rounded border p-2 text-sm ${
                  settings.choice === choice.value ? "border-blue-600 bg-blue-50 text-gray-900" : ""
                } ${unavailable ? "opacity-60" : ""}`}
              >
                <input
                  type="radio"
                  name="pose-model"
                  value={choice.value}
                  checked={settings.choice === choice.value}
                  disabled={unavailable}
                  onChange={() => choose(choice.value)}
                  className="mt-1"
                />
                <span className="flex flex-col">
                  <span className="font-medium">{choice.label}</span>
                  <span className={settings.choice === choice.value ? "text-gray-700" : "text-gray-600"}>
                    {choice.description}
                  </span>
                  {unavailable && <span className="text-amber-800">À préparer avant de pouvoir le choisir (ci-dessous).</span>}
                </span>
              </label>
              {isWholebodyChoice && (
                <WholebodySetup status={status} state={state} busy={busy} onInstall={install} onModeChange={changeMode} />
              )}
            </div>
          );
        })}
      </div>

      <div className="flex flex-col gap-1 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={settings.hands}
            onChange={(event) => onChange({ ...settings, hands: event.target.checked })}
          />
          Analyser les mains (préhensions, flexion des doigts)
        </label>
        {wholebody && (
          <>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={settings.feet}
                onChange={(event) => onChange({ ...settings, feet: event.target.checked })}
              />
              Analyser les pieds
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={settings.face}
                onChange={(event) => onChange({ ...settings, face: event.target.checked })}
              />
              Analyser le visage (68 points)
            </label>
          </>
        )}
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={settings.customEnabled}
            onChange={(event) => onChange({ ...settings, customEnabled: event.target.checked })}
          />
          Suivre des points personnalisés (outil, caisse, zone...)
        </label>
      </div>

      {wholebody && (
        <p className="text-xs text-gray-600">
          Le whole-body est nettement plus lent (plusieurs fois la durée de la vidéo sur un ordinateur sans carte
          graphique).
        </p>
      )}

      {settings.customEnabled && (
        <CustomPointsEditor
          file={file}
          points={settings.customPoints}
          referenceTime={settings.customReferenceTime}
          onChange={(customPoints, customReferenceTime) => onChange({ ...settings, customPoints, customReferenceTime })}
          disabled={disabled}
        />
      )}

      <p className="text-xs text-gray-600" aria-live="polite">
        Points suivis par personne : {expectedKeypointCount(settings)}
      </p>
    </fieldset>
  );
}
