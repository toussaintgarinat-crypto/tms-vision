"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { formatHours } from "../bilans/recurrenceFormat";
import { DOMAIN_LABELS, MetierDomain, MetierModel } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // corps non JSON : message générique.
  }
  return `Erreur ${response.status}`;
}

function statusLabel(model: MetierModel): string {
  if (model.status === "validated") return `Validé par ${model.validated_by ?? "un professionnel"}`;
  if (model.origin === "custom") return "Modèle du praticien";
  return model.source === "ai" ? "Brouillon généré par IA, à valider" : "Brouillon, à valider";
}

export default function MetiersPage() {
  const router = useRouter();
  const [models, setModels] = useState<MetierModel[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ id: string; message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/metiers`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<MetierModel[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setModels(data);
          setLoadError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError("Impossible de charger la bibliothèque (problème réseau ou serveur).");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // Crée un bilan prérempli avec les fiches du métier, puis l'ouvre pour l'adapter à la personne.
  async function handleCreate(event: FormEvent, model: MetierModel) {
    event.preventDefault();
    setBusyId(model.id);
    setActionError(null);
    try {
      const response = await fetch(`${API_URL}/metiers/${encodeURIComponent(model.id)}/bilan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: (labels[model.id] ?? "").trim() || null }),
      });
      if (!response.ok) {
        setActionError({ id: model.id, message: await errorMessage(response) });
        return;
      }
      const bilan = (await response.json()) as { id: string };
      router.push(`/bilans/${encodeURIComponent(bilan.id)}`);
    } catch {
      setActionError({ id: model.id, message: "Impossible de créer le bilan (problème réseau ou serveur)." });
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(model: MetierModel) {
    setBusyId(model.id);
    setActionError(null);
    try {
      const response = await fetch(`${API_URL}/metiers/${encodeURIComponent(model.id)}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        setActionError({ id: model.id, message: await errorMessage(response) });
        return;
      }
      setConfirmDeleteId(null);
      setReloadToken((token) => token + 1);
    } catch {
      setActionError({ id: model.id, message: "Impossible de supprimer le modèle (problème réseau ou serveur)." });
    } finally {
      setBusyId(null);
    }
  }

  const custom = (models ?? []).filter((model) => model.origin === "custom");
  const library = (models ?? []).filter((model) => model.origin === "library");
  const domains = (Object.keys(DOMAIN_LABELS) as MetierDomain[])
    .map((domain) => ({ domain, items: library.filter((model) => model.domain === domain) }))
    .filter(({ items }) => items.length > 0);

  function renderCard(model: MetierModel) {
    const total = model.tasks.reduce((sum, task) => sum + task.activity_hours, 0);
    const error = actionError?.id === model.id ? actionError.message : null;
    return (
      <li key={model.id} className="flex flex-col gap-3 rounded border p-4">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h4 className="text-lg font-semibold">{model.title}</h4>
            <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800">
              {statusLabel(model)}
            </span>
          </div>
          {model.description && (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">{model.description}</p>
          )}
        </div>
        <ul className="flex flex-col gap-1 text-sm">
          {model.tasks.map((task) => (
            <li key={task.name} className="flex flex-wrap justify-between gap-x-3">
              <span>
                {task.name}
                {task.workstation && (
                  <span className="text-zinc-500"> · {task.workstation}</span>
                )}
              </span>
              <span className="tabular-nums text-zinc-500">{formatHours(task.activity_hours)}</span>
            </li>
          ))}
          <li className="flex justify-between gap-3 border-t pt-1 font-medium">
            <span>Journée de {formatHours(model.workday_hours)}</span>
            <span className="tabular-nums">{formatHours(total)} documentées</span>
          </li>
        </ul>
        <form onSubmit={(event) => handleCreate(event, model)} className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-sm">
            Nom du bilan ou de la personne
            <input
              value={labels[model.id] ?? ""}
              onChange={(event) => setLabels((current) => ({ ...current, [model.id]: event.target.value }))}
              placeholder={model.title}
              className="rounded border p-2"
            />
          </label>
          <button
            type="submit"
            disabled={busyId === model.id}
            className="rounded border border-black px-3 py-2 text-sm disabled:opacity-50"
          >
            {busyId === model.id ? "Création..." : "Créer un bilan à partir de ce métier"}
          </button>
          {model.origin === "custom" &&
            (confirmDeleteId === model.id ? (
              <span className="flex items-center gap-2 text-sm">
                <button
                  type="button"
                  onClick={() => handleDelete(model)}
                  disabled={busyId === model.id}
                  className="rounded border border-red-600 px-3 py-2 text-red-600 disabled:opacity-50"
                >
                  Confirmer la suppression
                </button>
                <button type="button" onClick={() => setConfirmDeleteId(null)} className="underline">
                  Annuler
                </button>
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmDeleteId(model.id)}
                className="rounded border px-3 py-2 text-sm text-red-600"
              >
                Supprimer ce modèle
              </button>
            ))}
        </form>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </li>
    );
  }

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Bibliothèque de métiers</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Partez d&apos;un métier : le bilan est créé avec ses fiches d&apos;activité types, que vous
          adaptez ensuite à la personne. Les valeurs sont indicatives. Les scores viennent des
          vidéos analysées, jamais du modèle.
        </p>
      </div>

      {loadError && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-red-600">{loadError}</p>
          <button
            onClick={() => setReloadToken((token) => token + 1)}
            className="rounded border border-black px-3 py-1 text-sm"
          >
            Réessayer
          </button>
        </div>
      )}
      {!loadError && models === null && <p>Chargement...</p>}

      {custom.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">Mes modèles</h2>
          <ul className="flex flex-col gap-4">{custom.map(renderCard)}</ul>
        </section>
      )}
      {library.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">Métiers de la bibliothèque</h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Contenu en brouillon : à relire et valider par un professionnel de santé avant tout
            usage auprès de salariés.
          </p>
          <nav aria-label="Domaines d'activité" className="flex flex-wrap gap-2 text-sm">
            {domains.map(({ domain, items }) => (
              <a key={domain} href={`#domaine-${domain}`} className="rounded border px-3 py-1">
                {DOMAIN_LABELS[domain]} ({items.length})
              </a>
            ))}
          </nav>
          {domains.map(({ domain, items }) => (
            <section key={domain} id={`domaine-${domain}`} className="flex flex-col gap-3 pt-2">
              <h3 className="text-base font-semibold text-zinc-700 dark:text-zinc-300">
                {DOMAIN_LABELS[domain]}
              </h3>
              <ul className="flex flex-col gap-4">{items.map(renderCard)}</ul>
            </section>
          ))}
        </section>
      )}
    </main>
  );
}
