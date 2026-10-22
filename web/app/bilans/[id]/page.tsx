"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { GestureCorrection, ProgramItem, ProgramList } from "../../ProgramList";
import { RecurrenceReport } from "../RecurrenceReport";
import { formatHours } from "../recurrenceFormat";
import { TaskSection } from "../TaskSection";
import { BilanReport, StoredBilan } from "../types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type AnalysisOption = {
  id: string;
  created_at: string;
  worker_label: string | null;
  poste_label: string | null;
  max_score: number;
};

type BilanProgram = {
  program: ProgramItem[];
  gesture_corrections: GestureCorrection[];
  warnings: string[];
  position?: "seated" | null;
  position_note?: string | null;
};

type LoadedBilan = { id: string; bilan: StoredBilan; report: BilanReport; program: BilanProgram };

export default function BilanDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  // État porteur de l'id auquel il correspond, comparé à `id` au rendu (même
  // motif que historique/[id]/page.tsx, pour satisfaire
  // react-hooks/set-state-in-effect).
  const [loaded, setLoaded] = useState<LoadedBilan | null>(null);
  const [notFoundFor, setNotFoundFor] = useState<string | null>(null);
  const [fetchErrorFor, setFetchErrorFor] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [analysisOptions, setAnalysisOptions] = useState<AnalysisOption[]>([]);

  const [selectedAnalysisId, setSelectedAnalysisId] = useState("");
  const [activityHours, setActivityHours] = useState("");
  const [representative, setRepresentative] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const encodedId = encodeURIComponent(id);
    Promise.all([
      fetch(`${API_URL}/bilans/${encodedId}`),
      fetch(`${API_URL}/bilans/${encodedId}/recurrence`),
      fetch(`${API_URL}/bilans/${encodedId}/program`),
    ])
      .then(async ([bilanResponse, reportResponse, programResponse]) => {
        if (
          bilanResponse.status === 404 ||
          reportResponse.status === 404 ||
          programResponse.status === 404
        ) {
          if (!cancelled) {
            setNotFoundFor(id);
            setFetchErrorFor(null);
          }
          return;
        }
        if (!bilanResponse.ok || !reportResponse.ok || !programResponse.ok) {
          throw new Error("Erreur serveur");
        }
        const bilan = (await bilanResponse.json()) as StoredBilan;
        const report = (await reportResponse.json()) as BilanReport;
        const program = (await programResponse.json()) as BilanProgram;
        if (!cancelled) {
          setLoaded({ id, bilan, report, program });
          setNotFoundFor(null);
          setFetchErrorFor(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFetchErrorFor(id);
          setNotFoundFor(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id, reloadToken]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/analyses`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<AnalysisOption[]>;
      })
      .then((data) => {
        if (!cancelled) setAnalysisOptions(data);
      })
      .catch(() => {
        if (!cancelled) setAnalysisOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isNotFound = notFoundFor === id;
  const isFetchError = fetchErrorFor === id;
  const isLoaded = loaded !== null && loaded.id === id;

  const attachedIds = new Set(
    loaded && loaded.id === id ? (loaded.bilan.items ?? []).map((item) => item.analysis_id) : [],
  );
  const availableOptions = analysisOptions.filter((option) => !attachedIds.has(option.id));

  async function handleAttach(event: FormEvent) {
    event.preventDefault();
    const hours = Number(activityHours);
    if (!selectedAnalysisId) {
      setSubmitError("Choisissez une analyse.");
      return;
    }
    if (!Number.isFinite(hours) || hours <= 0) {
      setSubmitError("La durée d'activité doit être supérieure à 0.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await fetch(`${API_URL}/bilans/${encodeURIComponent(id)}/analyses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          analysis_id: selectedAnalysisId,
          activity_hours: hours,
          representative,
        }),
      });
      if (!response.ok) {
        // 404, 409 et 422 portent un `detail` lisible en français ; les 422 de
        // validation Pydantic ont un `detail` en liste, donc pas de texte à afficher.
        let message = `Erreur ${response.status}`;
        try {
          const body = (await response.json()) as { detail?: unknown };
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          // corps non JSON : on garde le message générique.
        }
        setSubmitError(message);
        return;
      }
      setSelectedAnalysisId("");
      setActivityHours("");
      setRepresentative(false);
      setReloadToken((token) => token + 1);
    } catch {
      setSubmitError("Impossible d'ajouter l'analyse (problème réseau ou serveur).");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {isLoaded ? (loaded.bilan.label ?? "Bilan sans libellé") : "Bilan de poste"}
        </h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {isLoaded && (
            <Link href={`/bilans/${encodeURIComponent(id)}/rapport`} className="text-sm text-blue-600 underline">
              Compte rendu (PDF / HTML)
            </Link>
          )}
          <Link href="/bilans" className="text-sm text-blue-600 underline">
            ← Retour aux bilans
          </Link>
        </div>
      </div>

      {isNotFound && <p className="text-red-600">Bilan introuvable.</p>}

      {isFetchError && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-red-600">
            Impossible de charger ce bilan (problème réseau ou serveur).
          </p>
          <button
            onClick={() => setReloadToken((token) => token + 1)}
            className="rounded border border-black px-3 py-1 text-sm"
          >
            Réessayer
          </button>
        </div>
      )}

      {!isNotFound && !isFetchError && !isLoaded && <p>Chargement...</p>}

      {loaded && loaded.id === id && (
        <>
          <form onSubmit={handleAttach} className="grid gap-4 rounded border p-4 sm:grid-cols-3">
            <h2 className="text-lg font-semibold sm:col-span-3">Ajouter une vidéo au bilan</h2>
            <label className="flex flex-col gap-1 text-sm sm:col-span-2">
              Analyse
              <select
                value={selectedAnalysisId}
                onChange={(event) => setSelectedAnalysisId(event.target.value)}
                className="rounded border p-2"
              >
                <option value="">— Choisir —</option>
                {availableOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {new Date(option.created_at).toLocaleString("fr-FR")} ·{" "}
                    {option.poste_label ?? "poste ?"} / {option.worker_label ?? "salarié ?"} · score
                    max {option.max_score}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Durée de cette activité dans la journée (heures)
              <input
                type="number"
                min="0.25"
                step="0.25"
                value={activityHours}
                onChange={(event) => setActivityHours(event.target.value)}
                className="rounded border p-2"
              />
              <span className="text-xs text-gray-500">
                Journée de {formatHours(loaded.bilan.workday_hours)}
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm sm:col-span-3">
              <input
                type="checkbox"
                checked={representative}
                onChange={(event) => setRepresentative(event.target.checked)}
              />
              Cette séquence est représentative de cette activité
            </label>
            <div className="sm:col-span-3">
              <button
                type="submit"
                disabled={submitting}
                className="rounded border border-black px-3 py-1 text-sm disabled:opacity-50"
              >
                Ajouter au bilan
              </button>
              {submitError && <p className="mt-2 text-red-600">{submitError}</p>}
            </div>
          </form>

          <TaskSection
            bilanId={id}
            workdayHours={loaded.bilan.workday_hours}
            items={loaded.bilan.items ?? []}
            tasks={loaded.bilan.tasks ?? []}
            onChanged={() => setReloadToken((token) => token + 1)}
          />

          <RecurrenceReport report={loaded.report} />

          {(loaded.program.program.length > 0 || loaded.program.gesture_corrections.length > 0) && (
            <section className="flex flex-col gap-3">
              <h2 className="text-xl font-semibold">Programme d&apos;étirements du poste</h2>
              {loaded.program.position_note && (
                <p className="text-sm text-gray-600">{loaded.program.position_note}</p>
              )}
              <ProgramList
                program={loaded.program.program}
                gestureCorrections={loaded.program.gesture_corrections}
              />
            </section>
          )}
        </>
      )}
    </main>
  );
}
