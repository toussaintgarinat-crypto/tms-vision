"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { scoreBadgeColor, scoreBadgeTextColor } from "./scoreBadge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type StoredAnalysis = {
  id: string;
  created_at: string;
  side: "left" | "right";
  load_kg: number;
  wrist_twist: "normal" | "extreme";
  worker_label: string | null;
  poste_label: string | null;
  frame_count: number;
  detected_frame_count: number;
  max_score: number;
  average_score: number;
  time_by_action_level: Record<string, number>;
};

const SIDE_LABELS: Record<"left" | "right", string> = { right: "Droit", left: "Gauche" };

export default function HistoriquePage() {
  const [analyses, setAnalyses] = useState<StoredAnalysis[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [workerLabel, setWorkerLabel] = useState("");
  const [posteLabel, setPosteLabel] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  // Contrairement à AnalysisResult.tsx et historique/[id]/page.tsx, cet état
  // n'a pas besoin d'être porté par une clé (analysisId / id) : `cancelled`
  // suffit à empêcher une réponse obsolète d'écraser un résultat plus récent,
  // et rien ici n'a besoin d'associer une ligne affichée à la combinaison de
  // filtres exacte qui l'a produite.
  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams();
    if (workerLabel.trim()) params.set("worker_label", workerLabel.trim());
    if (posteLabel.trim()) params.set("poste_label", posteLabel.trim());
    // Construit les bornes en heure LOCALE puis les convertit en UTC (ISO avec
    // suffixe Z) avant l'envoi : `created_at` est stocké en UTC naïf côté
    // backend et affiché en heure locale côté table ci-dessous
    // (toLocaleString) -- envoyer une date/heure locale sans suffixe de fuseau
    // décalerait la fenêtre de filtre par rapport à ce que l'utilisateur voit.
    if (since) params.set("since", new Date(`${since}T00:00:00`).toISOString());
    if (until) params.set("until", new Date(`${until}T23:59:59.999`).toISOString());
    const query = params.toString();
    fetch(`${API_URL}/analyses${query ? `?${query}` : ""}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<StoredAnalysis[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setAnalyses(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Impossible de charger l'historique des analyses.");
          setAnalyses(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workerLabel, posteLabel, since, until]);

  const hasFilters = Boolean(workerLabel || posteLabel || since || until);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Historique des analyses</h1>
        <Link href="/" className="text-sm text-blue-600 underline">
          ← Nouvelle analyse
        </Link>
      </div>

      <section className="grid gap-4 rounded border p-4 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-sm">
          Salarié
          <input
            type="text"
            value={workerLabel}
            onChange={(event) => setWorkerLabel(event.target.value)}
            className="rounded border p-2"
          />
          <span className="text-xs text-gray-500">Correspondance exacte</span>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Poste
          <input
            type="text"
            value={posteLabel}
            onChange={(event) => setPosteLabel(event.target.value)}
            className="rounded border p-2"
          />
          <span className="text-xs text-gray-500">Correspondance exacte</span>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Depuis
          <input
            type="date"
            value={since}
            onChange={(event) => setSince(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Jusqu&apos;à
          <input
            type="date"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
            className="rounded border p-2"
          />
        </label>
      </section>

      {error && <p className="text-red-600">{error}</p>}

      {analyses === null && !error && <p>Chargement...</p>}

      {analyses !== null && analyses.length === 0 && (
        <p className="text-gray-600">
          {hasFilters
            ? "Aucune analyse ne correspond à ces filtres."
            : "Aucune analyse enregistrée."}
        </p>
      )}

      {analyses !== null && analyses.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="p-2">Date</th>
                <th className="p-2">Salarié</th>
                <th className="p-2">Poste</th>
                <th className="p-2">Côté</th>
                <th className="p-2">Score max</th>
                <th className="p-2">Score moyen</th>
                <th className="p-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {analyses.map((analysis) => (
                <tr key={analysis.id} className="border-b">
                  <td className="p-2">{new Date(analysis.created_at).toLocaleString("fr-FR")}</td>
                  <td className="p-2">{analysis.worker_label ?? "—"}</td>
                  <td className="p-2">{analysis.poste_label ?? "—"}</td>
                  <td className="p-2">{SIDE_LABELS[analysis.side]}</td>
                  <td className="p-2">
                    <span
                      className="rounded px-2 py-1"
                      style={{
                        backgroundColor: scoreBadgeColor(analysis.max_score),
                        color: scoreBadgeTextColor(analysis.max_score),
                      }}
                    >
                      {analysis.max_score}
                    </span>
                  </td>
                  <td className="p-2">{analysis.average_score.toFixed(1)}</td>
                  <td className="p-2">
                    <a
                      href={`/historique/${encodeURIComponent(analysis.id)}`}
                      className="text-blue-600 underline"
                    >
                      Voir
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
