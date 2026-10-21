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
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [workdayHours, setWorkdayHours] = useState("9");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/bilans`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<StoredBilan[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setBilans(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBilans(null);
          setError("Impossible de charger les bilans (problème réseau ou serveur).");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
      {bilans !== null && bilans.length === 0 && (
        <p className="text-gray-600">Aucun bilan enregistré.</p>
      )}
      {bilans !== null && bilans.length > 0 && (
        <ul className="flex flex-col gap-2">
          {bilans.map((bilan) => (
            <li key={bilan.id} className="flex items-center justify-between rounded border p-3 text-sm">
              <span>
                {bilan.label ?? "Sans libellé"} · {formatHours(bilan.workday_hours)} ·{" "}
                {new Date(bilan.created_at).toLocaleString("fr-FR")}
              </span>
              <a href={`/bilans/${encodeURIComponent(bilan.id)}`} className="text-blue-600 underline">
                Ouvrir
              </a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
