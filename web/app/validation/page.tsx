"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../auth/AuthProvider";
import { useI18n } from "../i18n/I18nProvider";
import { ValidationPanel } from "../ValidationPanel";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type QueueItem = { id: string; title: string; zone: string; created_by: string; validated_by: string | null };

// File de relecture de l'ostéopathe : les fiches dont la version courante n'est pas validée par lui,
// l'une après l'autre. La règle ne change pas : chaque fiche se valide dans l'écran de validation
// (animation jouée en entier, case cochée) ; « Passer » laisse la fiche non validée.
export default function ValidationQueuePage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [fichesOnly, setFichesOnly] = useState(true);
  const [skipped, setSkipped] = useState<string[]>([]);
  const isOsteopath = user?.roles.includes("osteopathe") ?? false;

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/validation/queue?fiches_only=${fichesOnly}`);
      if (!response.ok) throw new Error(String(response.status));
      setItems(((await response.json()) as { items: QueueItem[] }).items);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [fichesOnly]);

  useEffect(() => {
    if (!isOsteopath) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load, isOsteopath]);

  if (!user) return null;
  if (!isOsteopath) {
    return <main className="mx-auto w-full max-w-3xl flex-1 p-6 text-sm">{t("queue.forbidden")}</main>;
  }

  const remaining = (items ?? []).filter((item) => !skipped.includes(item.id));
  const current = remaining[0] ?? null;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 p-4 sm:p-6">
      <h1 className="text-2xl font-bold">{t("queue.title")}</h1>
      <p className="text-sm text-gray-700">{t("queue.intro")}</p>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={fichesOnly}
          onChange={(event) => {
            setFichesOnly(event.target.checked);
            setSkipped([]);
          }}
        />
        {t("queue.fichesOnly")}
      </label>
      {failed && <p className="text-sm text-red-700">{t("queue.loadFailed")}</p>}
      {items !== null && (
        <p className="text-sm font-semibold" aria-live="polite">
          {t("queue.remaining", { count: remaining.length })}
          {skipped.length > 0 && ` ${t("queue.skippedCount", { count: skipped.length })}`}
        </p>
      )}
      {items !== null && current === null && (
        <p className="rounded border border-emerald-300 bg-emerald-50 p-3 text-sm">{t("queue.done")}</p>
      )}
      {current && (
        <div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">{current.title}</h2>
            <button
              type="button"
              onClick={() => setSkipped((previous) => [...previous, current.id])}
              className="rounded border px-3 py-1 text-sm"
            >
              {t("queue.skip")}
            </button>
          </div>
          {/* key : l'écran repart de zéro (animation à rejouer, case décochée) à chaque fiche. */}
          <ValidationPanel
            key={current.id}
            exerciseId={current.id}
            onClose={() => setSkipped((previous) => [...previous, current.id])}
            onChanged={() => void load()}
          />
        </div>
      )}
    </main>
  );
}
