"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { formatHours } from "./recurrenceFormat";
import { StoredBilan } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function BilansPage() {
  const router = useRouter();
  const [bilans, setBilans] = useState<StoredBilan[] | null>(null);
  const [archives, setArchives] = useState<StoredBilan[] | null>(null);
  const [showArchives, setShowArchives] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [workdayHours, setWorkdayHours] = useState("9");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = (archived: boolean) =>
      fetch(`${API_URL}/bilans?archived=${archived}`).then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<StoredBilan[]>;
      });
    Promise.all([load(false), load(true)])
      .then(([active, archived]) => {
        if (!cancelled) {
          setBilans(active);
          setArchives(archived);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBilans(null);
          setArchives(null);
          setError("Impossible de charger les bilans (problème réseau ou serveur).");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // Archive, restaure ou supprime un bilan, puis recharge les deux listes.
  async function handleAction(bilan: StoredBilan, action: "archive" | "unarchive" | "delete") {
    setBusyId(bilan.id);
    setActionError(null);
    try {
      const url = `${API_URL}/bilans/${encodeURIComponent(bilan.id)}`;
      const response =
        action === "delete"
          ? await fetch(url, { method: "DELETE" })
          : await fetch(`${url}/${action}`, { method: "POST" });
      if (!response.ok) throw new Error(`Erreur ${response.status}`);
      setConfirmDeleteId(null);
      setReloadToken((token) => token + 1);
    } catch {
      setActionError("L'action a échoué (problème réseau ou serveur). Réessayez.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    const hours = Number(workdayHours);
    if (!Number.isFinite(hours) || hours <= 0 || hours > 24) {
      setSubmitError("La durée de journée doit être comprise entre 0 et 24 heures.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await fetch(`${API_URL}/bilans`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: label.trim() || null, workday_hours: hours }),
      });
      if (!response.ok) throw new Error(`Erreur ${response.status}`);
      const created = (await response.json()) as StoredBilan;
      router.push(`/bilans/${encodeURIComponent(created.id)}`);
    } catch {
      setSubmitError("Impossible de créer le bilan (problème réseau ou serveur).");
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Bilans de poste</h1>
        <Link href="/" className="text-sm text-blue-600 underline">
          ← Nouvelle analyse
        </Link>
      </div>

      <form onSubmit={handleCreate} className="grid gap-4 rounded border p-4 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          Libellé du poste
          <input
            type="text"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Journée de travail (heures)
          <input
            type="number"
            min="0.5"
            max="24"
            step="0.5"
            value={workdayHours}
            onChange={(event) => setWorkdayHours(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <div className="sm:col-span-3">
          <button
            type="submit"
            disabled={submitting}
            className="rounded border border-black px-3 py-1 text-sm disabled:opacity-50"
          >
            Créer un bilan
          </button>
          {submitError && <p className="mt-2 text-red-600">{submitError}</p>}
        </div>
      </form>

      {error && <p className="text-red-600">{error}</p>}
      {bilans === null && !error && <p>Chargement...</p>}
      {bilans !== null && archives !== null && (
        <>
          <div className="flex gap-2 border-b" role="tablist" aria-label="Bilans">
            <button
              type="button"
              role="tab"
              aria-selected={!showArchives}
              onClick={() => setShowArchives(false)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${!showArchives ? "border-black font-semibold" : "border-transparent text-gray-600"}`}
            >
              Bilans ({bilans.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={showArchives}
              onClick={() => setShowArchives(true)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${showArchives ? "border-black font-semibold" : "border-transparent text-gray-600"}`}
            >
              Archives ({archives.length})
            </button>
          </div>

          {actionError && <p className="text-red-600">{actionError}</p>}
          {(showArchives ? archives : bilans).length === 0 && (
            <p className="text-gray-600">
              {showArchives
                ? "Aucun bilan archivé. Archivez un bilan pour le ranger sans le perdre."
                : "Aucun bilan enregistré."}
            </p>
          )}
          <ul className="flex flex-col gap-2">
            {(showArchives ? archives : bilans).map((bilan) => (
              <li
                key={bilan.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border p-3 text-sm"
              >
                <span>
                  {bilan.label ?? "Sans libellé"} · {formatHours(bilan.workday_hours)} ·{" "}
                  {new Date(bilan.created_at).toLocaleString("fr-FR")}
                  {bilan.archived_at && (
                    <span className="text-gray-500">
                      {" "}
                      · archivé le {new Date(bilan.archived_at).toLocaleDateString("fr-FR")}
                    </span>
                  )}
                </span>
                <span className="flex flex-wrap items-center gap-3">
                  <a href={`/bilans/${encodeURIComponent(bilan.id)}`} className="text-blue-600 underline">
                    Ouvrir
                  </a>
                  <button
                    type="button"
                    disabled={busyId === bilan.id}
                    onClick={() => handleAction(bilan, showArchives ? "unarchive" : "archive")}
                    className="text-blue-600 underline disabled:opacity-50"
                  >
                    {showArchives ? "Restaurer" : "Archiver"}
                  </button>
                  {confirmDeleteId === bilan.id ? (
                    <span className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={busyId === bilan.id}
                        onClick={() => handleAction(bilan, "delete")}
                        className="rounded border border-red-600 px-2 py-0.5 text-red-600 disabled:opacity-50"
                      >
                        Supprimer définitivement
                      </button>
                      <button type="button" onClick={() => setConfirmDeleteId(null)} className="underline">
                        Annuler
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmDeleteId(bilan.id)}
                      className="text-red-600 underline"
                    >
                      Supprimer
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
