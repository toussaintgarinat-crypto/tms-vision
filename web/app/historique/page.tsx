"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useI18n } from "../i18n/I18nProvider";
import { formatDecimal } from "../poseInfoFormat";
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

export default function HistoriquePage() {
  const { t, tag } = useI18n();
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
    // toISOString() lève RangeError sur une date invalide/hors bornes -- <input
    // type="date"> l'empêche en pratique dans les navigateurs courants, mais
    // son champ année accepte jusqu'à 275760, qui déborde la valeur temporelle
    // maximale représentable une fois l'heure de fin de journée ajoutée.
    const sinceDate = since ? new Date(`${since}T00:00:00`) : null;
    if (sinceDate && !Number.isNaN(sinceDate.getTime())) {
      params.set("since", sinceDate.toISOString());
    }
    const untilDate = until ? new Date(`${until}T23:59:59.999`) : null;
    if (untilDate && !Number.isNaN(untilDate.getTime())) {
      params.set("until", untilDate.toISOString());
    }
    const query = params.toString();
    fetch(`${API_URL}/analyses${query ? `?${query}` : ""}`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
          setError("load");
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
        <h1 className="text-2xl font-semibold">{t("hist.title")}</h1>
        <Link href="/" className="text-sm text-blue-600 underline">
          {t("hist.newAnalysis")}
        </Link>
      </div>

      <section className="grid gap-4 rounded border p-4 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-sm">
          {t("hist.worker")}
          <input
            type="text"
            value={workerLabel}
            onChange={(event) => setWorkerLabel(event.target.value)}
            className="rounded border p-2"
          />
          <span className="text-xs text-gray-500">{t("hist.exactMatch")}</span>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("hist.position")}
          <input
            type="text"
            value={posteLabel}
            onChange={(event) => setPosteLabel(event.target.value)}
            className="rounded border p-2"
          />
          <span className="text-xs text-gray-500">{t("hist.exactMatch")}</span>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("hist.since")}
          <input
            type="date"
            value={since}
            onChange={(event) => setSince(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("hist.until")}
          <input
            type="date"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
            className="rounded border p-2"
          />
        </label>
      </section>

      {error && <p className="text-red-600">{t("hist.loadError")}</p>}

      {analyses === null && !error && <p>{t("common.loading")}</p>}

      {analyses !== null && analyses.length === 0 && (
        <p className="text-gray-600">
          {hasFilters ? t("hist.noMatch") : t("hist.none")}
        </p>
      )}

      {analyses !== null && analyses.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="p-2">{t("hist.col.date")}</th>
                <th className="p-2">{t("hist.worker")}</th>
                <th className="p-2">{t("hist.position")}</th>
                <th className="p-2">{t("hist.col.side")}</th>
                <th className="p-2">{t("hist.col.maxScore")}</th>
                <th className="p-2">{t("hist.col.avgScore")}</th>
                <th className="p-2">
                  <span className="sr-only">{t("hist.col.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {analyses.map((analysis) => (
                <tr key={analysis.id} className="border-b">
                  <td className="p-2">{new Date(analysis.created_at).toLocaleString(tag)}</td>
                  <td className="p-2">{analysis.worker_label ?? "—"}</td>
                  <td className="p-2">{analysis.poste_label ?? "—"}</td>
                  <td className="p-2">{t(`analysis.side.${analysis.side}`)}</td>
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
                  <td className="p-2">{formatDecimal(analysis.average_score, tag)}</td>
                  <td className="p-2">
                    <a
                      href={`/historique/${encodeURIComponent(analysis.id)}`}
                      className="text-blue-600 underline"
                    >
                      {t("hist.view")}
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
