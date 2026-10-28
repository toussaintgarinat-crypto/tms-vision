"use client";

import { WholebodyState, WholebodyStatus } from "./poseModels";

type WholebodySetupProps = {
  status: WholebodyStatus | null;
  state: WholebodyState;
  busy: boolean;
  onInstall: () => void;
  onModeChange: (mode: string) => void;
};

/** Préparation et réglage du modèle whole-body, directement sur le site (rien à faire dans `.env`). */
export function WholebodySetup({ status, state, busy, onInstall, onModeChange }: WholebodySetupProps) {
  if (state === "loading") return null;

  const approxMb = status?.approx_download_mb ?? 330;

  return (
    <div className="ml-6 flex flex-col gap-2 rounded border border-dashed p-2 text-sm" aria-live="polite">
      <span className="font-medium">Modèle whole-body</span>

      {state === "unavailable" && (
        <p className="text-amber-800">
          Ce modèle n&apos;est pas installé sur cette installation (l&apos;application de bureau ne l&apos;inclut pas).
          Voir <code>docs/POSE-MODELES.md</code>.
        </p>
      )}

      {(state === "needs_download" || state === "error") && (
        <>
          {state === "error" && status?.download.message && <p className="text-red-600">{status.download.message}</p>}
          <p className="text-gray-700">
            À préparer une seule fois : téléchargement d&apos;environ {approxMb} Mo, puis le modèle reste disponible.
          </p>
          <button
            type="button"
            onClick={onInstall}
            disabled={busy}
            className="w-fit rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
          >
            {state === "error" ? "Réessayer" : "Préparer le modèle"}
          </button>
        </>
      )}

      {state === "downloading" && (
        <p className="text-gray-700">
          Préparation en cours… {status?.download.message ?? ""} Vous pouvez continuer à utiliser le site ; le
          modèle sera sélectionnable ensuite.
        </p>
      )}

      {state === "ready" && status && (
        <label className="flex flex-col gap-1">
          <span className="text-green-800">Prêt. Vitesse d&apos;analyse :</span>
          <select
            value={status.mode}
            onChange={(event) => onModeChange(event.target.value)}
            disabled={busy}
            className="rounded border p-1"
          >
            {status.modes.map((mode) => (
              <option key={mode.id} value={mode.id}>
                {mode.label}
              </option>
            ))}
          </select>
          <span className="text-xs text-gray-600">{status.modes.find((m) => m.id === status.mode)?.hint}</span>
        </label>
      )}
    </div>
  );
}
