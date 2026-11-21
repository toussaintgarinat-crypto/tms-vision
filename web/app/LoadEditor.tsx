"use client";

import { FormEvent, useState } from "react";

import { useI18n } from "./i18n/I18nProvider";
import { LoadInfo, LoadKind, buildLoadRequest } from "./loadFormat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const KINDS: LoadKind[] = ["none", "exact", "range"];

type LoadEditorProps<T> = {
  analysisId: string;
  load: LoadInfo;
  onUpdated: (updated: T) => void;
};

// Valeur affichée dans le champ, avec la virgule ou le point décimal de la langue ; la saisie des deux
// est acceptée (voir parseKg dans loadFormat.ts).
function initialText(value: number | null, tag: string): string {
  return value === null ? "" : value.toLocaleString(tag, { useGrouping: false, maximumFractionDigits: 3 });
}

// Le parent rend cet éditeur avec une `key` dérivée du poids enregistré : le
// formulaire repart alors des valeurs sauvegardées après chaque mise à jour,
// sans effet de synchronisation.
export function LoadEditor<T>({ analysisId, load, onUpdated }: LoadEditorProps<T>) {
  const { t, tag } = useI18n();
  const [kind, setKind] = useState<LoadKind>(load.kind);
  const [kgText, setKgText] = useState(initialText(load.kg, tag));
  const [minText, setMinText] = useState(initialText(load.kg_min, tag));
  const [maxText, setMaxText] = useState(initialText(load.kg_max, tag));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const built = buildLoadRequest(kind, kgText, minText, maxText);
    if (!built.ok) {
      setError(t(built.error.key, built.error.vars));
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
        let message = t("load.editor.httpError", { status: response.status });
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
      setError(t("load.editor.networkError"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded border p-3 text-sm">
      <fieldset className="flex flex-col gap-2">
        <legend className="font-semibold">{t("load.editor.title")}</legend>
        <p className="text-xs text-gray-600">
          {t("load.editor.hint")}
        </p>
        <div className="flex flex-wrap gap-4">
          {KINDS.map((option) => (
            <label key={option} className="flex items-center gap-2">
              <input
                type="radio"
                name={`load-kind-${analysisId}`}
                checked={kind === option}
                onChange={() => setKind(option)}
              />
              {t(`load.kind.${option}`)}
            </label>
          ))}
        </div>
      </fieldset>

      {kind === "exact" && (
        <label className="flex flex-col gap-1">
          {t("load.editor.weight")}
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
            {t("load.editor.from")}
            <input
              type="text"
              inputMode="decimal"
              value={minText}
              onChange={(event) => setMinText(event.target.value)}
              className="w-28 rounded border p-2"
            />
          </label>
          <label className="flex flex-col gap-1">
            {t("load.editor.to")}
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
          {t("load.editor.save")}
        </button>
        {error && <p className="mt-2 text-red-600">{error}</p>}
      </div>
    </form>
  );
}
