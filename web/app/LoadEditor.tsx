"use client";

import { FormEvent, useState } from "react";

import { LoadInfo, LoadKind, buildLoadRequest } from "./loadFormat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const KIND_LABELS: Record<LoadKind, string> = {
  none: "Aucun poids",
  exact: "Poids précis",
  range: "Fourchette",
};

type LoadEditorProps<T> = {
  analysisId: string;
  load: LoadInfo;
  onUpdated: (updated: T) => void;
};

function initialText(value: number | null): string {
  return value === null ? "" : String(value).replace(".", ",");
}

// Le parent rend cet éditeur avec une `key` dérivée du poids enregistré : le
// formulaire repart alors des valeurs sauvegardées après chaque mise à jour,
// sans effet de synchronisation.
export function LoadEditor<T>({ analysisId, load, onUpdated }: LoadEditorProps<T>) {
  const [kind, setKind] = useState<LoadKind>(load.kind);
  const [kgText, setKgText] = useState(initialText(load.kg));
  const [minText, setMinText] = useState(initialText(load.kg_min));
  const [maxText, setMaxText] = useState(initialText(load.kg_max));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const built = buildLoadRequest(kind, kgText, minText, maxText);
    if (!built.ok) {
      setError(built.error);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/analyses/${encodeURIComponent(analysisId)}/load`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(built.request),
      });
      if (!response.ok) {
        // 404 et 422 portent un `detail` lisible ; les 422 de validation de
        // schéma ont un `detail` en liste, donc pas de texte à afficher.
        let message = `Erreur ${response.status}`;
        try {
          const body = (await response.json()) as { detail?: unknown };
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          // corps non JSON : on garde le message générique.
        }
        setError(message);
        return;
      }
      onUpdated((await response.json()) as T);
    } catch {
      setError("Impossible d'enregistrer le poids (problème réseau ou serveur).");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded border p-3 text-sm">
      <fieldset className="flex flex-col gap-2">
        <legend className="font-semibold">Poids manipulé</legend>
        <p className="text-xs text-gray-600">
          La vidéo ne peut pas deviner le poids : saisissez-le pour recalculer le score.
        </p>
        <div className="flex flex-wrap gap-4">
          {(Object.keys(KIND_LABELS) as LoadKind[]).map((option) => (
            <label key={option} className="flex items-center gap-2">
              <input
                type="radio"
                name={`load-kind-${analysisId}`}
                checked={kind === option}
                onChange={() => setKind(option)}
              />
              {KIND_LABELS[option]}
            </label>
          ))}
        </div>
      </fieldset>

      {kind === "exact" && (
        <label className="flex flex-col gap-1">
          Poids (kg)
          <input
            type="text"
            inputMode="decimal"
            value={kgText}
            onChange={(event) => setKgText(event.target.value)}
            className="w-32 rounded border p-2"
          />
        </label>
      )}

      {kind === "range" && (
        <div className="flex flex-wrap gap-4">
          <label className="flex flex-col gap-1">
            De (kg)
            <input
              type="text"
              inputMode="decimal"
              value={minText}
              onChange={(event) => setMinText(event.target.value)}
              className="w-28 rounded border p-2"
            />
          </label>
          <label className="flex flex-col gap-1">
            À (kg)
            <input
              type="text"
              inputMode="decimal"
              value={maxText}
              onChange={(event) => setMaxText(event.target.value)}
              className="w-28 rounded border p-2"
            />
          </label>
        </div>
      )}

      <div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded border border-black px-3 py-1 disabled:opacity-50"
        >
          Enregistrer le poids
        </button>
        {error && <p className="mt-2 text-red-600">{error}</p>}
      </div>
    </form>
  );
}
