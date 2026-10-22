"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { Exercise } from "../exercisePose";
import { BodyMap, BodyView } from "./BodyMap";
import { ExerciseCarousel } from "./ExerciseCarousel";
import {
  ALL_PATHOLOGIES,
  API_URL,
  BasketItem,
  Library,
  ShareResult,
  buildSharePayload,
  exerciseIdsFor,
  isInBasket,
  isValidEmail,
  setBasketNote,
  toggleInBasket,
} from "./library";

const EMAIL_STATUS_MESSAGE: Record<ShareResult["email_status"], string> = {
  sent: "Email envoyé au patient.",
  not_configured:
    "L'envoi d'email n'est pas encore branché : copiez le lien ci-dessous et transmettez-le au patient.",
  failed: "L'email n'a pas pu partir. Le lien ci-dessous reste valable : transmettez-le au patient.",
};

export default function LibraryPage() {
  const [library, setLibrary] = useState<Library | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<BodyView>("front");
  const [zoneId, setZoneId] = useState<string | null>(null);
  const [pathologyId, setPathologyId] = useState(ALL_PATHOLOGIES);
  const [index, setIndex] = useState(0);
  const [catalog, setCatalog] = useState<Record<string, Exercise>>({});
  const [basket, setBasket] = useState<BasketItem[]>([]);
  const [form, setForm] = useState({ email: "", practitioner: "", message: "" });
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [result, setResult] = useState<ShareResult | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/library`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<Library>;
      })
      .then((data) => {
        if (!cancelled) setLibrary(data);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Impossible de charger la bibliothèque. Le serveur est-il lancé ?");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const zone = library?.zones.find((candidate) => candidate.id === zoneId) ?? null;
  const exerciseIds = useMemo(() => (zone ? exerciseIdsFor(zone, pathologyId) : []), [zone, pathologyId]);
  // Les exercices du panier doivent aussi être connus pour afficher leur titre.
  const neededIds = useMemo(
    () => [...new Set([...exerciseIds, ...basket.map((item) => item.exerciseId)])],
    [exerciseIds, basket],
  );

  useEffect(() => {
    const missing = neededIds.filter((id) => !catalog[id]);
    if (missing.length === 0) return;
    let cancelled = false;
    missing.forEach((id) => {
      fetch(`${API_URL}/exercises/${encodeURIComponent(id)}`)
        .then((response) => {
          if (!response.ok) throw new Error(`Erreur ${response.status}`);
          return response.json() as Promise<Exercise>;
        })
        .then((exercise) => {
          if (!cancelled) setCatalog((previous) => ({ ...previous, [id]: exercise }));
        })
        .catch(() => {
          if (!cancelled) setLoadError("Impossible de charger un exercice.");
        });
    });
    return () => {
      cancelled = true;
    };
  }, [neededIds, catalog]);

  const exercises = exerciseIds.map((id) => catalog[id]).filter((exercise): exercise is Exercise => !!exercise);

  const selectZone = (id: string) => {
    setZoneId(id);
    setPathologyId(ALL_PATHOLOGIES);
    setIndex(0);
  };
  const selectPathology = (id: string) => {
    setPathologyId(id);
    setIndex(0);
  };

  const updateBasket = (next: BasketItem[]) => {
    setBasket(next);
    setResult(null);
    setSendError(null);
  };

  const canSend = basket.length > 0 && isValidEmail(form.email) && !sending;

  const send = async () => {
    setSending(true);
    setSendError(null);
    try {
      const response = await fetch(`${API_URL}/library/shares`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildSharePayload(basket, form)),
      });
      if (!response.ok) {
        const detail = await response.json().then((body) => body.detail).catch(() => null);
        throw new Error(typeof detail === "string" ? detail : `Erreur ${response.status}`);
      }
      setResult((await response.json()) as ShareResult);
    } catch (error) {
      setSendError(error instanceof Error ? error.message : "Envoi impossible.");
    } finally {
      setSending(false);
    }
  };

  const shareUrl = result ? `${window.location.origin}${result.share_path}` : null;
  const copyLink = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const zoneChips = library?.zones ?? [];

  return (
    <main className="mx-auto w-full max-w-7xl flex-1 p-4 sm:p-6">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Bibliothèque d&apos;exercices</h1>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Cliquez sur la zone douloureuse, choisissez la pathologie, sélectionnez les exercices à envoyer.
          </p>
        </div>
        <Link href="/" className="text-sm text-blue-700 underline dark:text-blue-400">
          Retour à l&apos;analyse
        </Link>
      </header>

      {library?.status === "draft" && (
        <p className="mb-4 rounded-lg bg-amber-100 px-3 py-2 text-sm text-amber-950">
          Contenu en brouillon : le rattachement zone → pathologie → exercices est un premier jet à
          relire et valider par un professionnel de santé avant tout usage auprès de patients.
        </p>
      )}
      {loadError && <p role="alert" className="mb-4 text-sm text-red-700">{loadError}</p>}

      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
        <div className="space-y-3">
          <div className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-700">
            <div className="mb-2 flex justify-center gap-1" role="group" aria-label="Vue du corps">
              {(["front", "back"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setView(option)}
                  aria-pressed={view === option}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    view === option
                      ? "border-blue-600 bg-blue-600 text-white"
                      : "border-zinc-300 dark:border-zinc-600"
                  }`}
                >
                  {option === "front" ? "Face" : "Dos"}
                </button>
              ))}
            </div>
            <BodyMap view={view} selectedZone={zoneId} zones={zoneChips} onSelect={selectZone} />
          </div>

          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Zones du corps">
            {zoneChips.map((candidate) => (
              <button
                key={candidate.id}
                type="button"
                onClick={() => selectZone(candidate.id)}
                aria-pressed={candidate.id === zoneId}
                className={`rounded-full border px-2.5 py-1 text-xs ${
                  candidate.id === zoneId
                    ? "border-blue-600 bg-blue-600 text-white"
                    : "border-zinc-300 hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
                }`}
              >
                {candidate.label}
              </button>
            ))}
          </div>

          {zone && (
            <div className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-700">
              <h2 className="mb-2 text-sm font-semibold">{zone.label} : quelle pathologie ?</h2>
              <ul className="space-y-1">
                {[{ id: ALL_PATHOLOGIES, label: "Tous les exercices de la zone" }, ...zone.pathologies].map(
                  (pathology) => (
                    <li key={pathology.id}>
                      <button
                        type="button"
                        onClick={() => selectPathology(pathology.id)}
                        aria-pressed={pathology.id === pathologyId}
                        className={`w-full rounded-lg px-2.5 py-1.5 text-left text-sm ${
                          pathology.id === pathologyId
                            ? "bg-blue-600 text-white"
                            : "hover:bg-zinc-100 dark:hover:bg-zinc-800"
                        }`}
                      >
                        {pathology.label}
                      </button>
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}
        </div>

        <div>
          {!zone && (
            <p className="rounded-xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-600">
              Choisissez une zone du corps pour voir les exercices.
            </p>
          )}
          {zone && exercises.length === 0 && !loadError && (
            <p className="p-8 text-center text-sm text-zinc-500">Chargement des exercices…</p>
          )}
          {zone && exercises.length > 0 && (
            <ExerciseCarousel
              exercises={exercises}
              index={index}
              onIndexChange={setIndex}
              footer={(exercise) => (
                <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={isInBasket(basket, exercise.id)}
                    onChange={() => updateBasket(toggleInBasket(basket, exercise.id))}
                  />
                  Ajouter à l&apos;envoi
                </label>
              )}
            />
          )}
        </div>

        <aside className="h-fit rounded-xl border border-zinc-200 p-4 dark:border-zinc-700" aria-label="Envoi au patient">
          <h2 className="mb-2 font-semibold">Envoi au patient ({basket.length})</h2>
          {basket.length === 0 ? (
            <p className="text-sm text-zinc-500">Cochez « Ajouter à l&apos;envoi » sur les exercices choisis.</p>
          ) : (
            <ul className="space-y-3">
              {basket.map((item) => (
                <li key={item.exerciseId} className="text-sm">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium">{catalog[item.exerciseId]?.title ?? item.exerciseId}</span>
                    <button
                      type="button"
                      onClick={() => updateBasket(toggleInBasket(basket, item.exerciseId))}
                      aria-label={`Retirer ${catalog[item.exerciseId]?.title ?? item.exerciseId}`}
                      className="text-zinc-500 hover:text-red-700"
                    >
                      ✕
                    </button>
                  </div>
                  <input
                    type="text"
                    value={item.note}
                    maxLength={500}
                    onChange={(event) => updateBasket(setBasketNote(basket, item.exerciseId, event.target.value))}
                    placeholder="Note : 2 fois par jour, 10 répétitions…"
                    className="mt-1 w-full rounded border border-zinc-300 bg-transparent px-2 py-1 text-xs dark:border-zinc-600"
                  />
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 space-y-2 border-t border-zinc-200 pt-3 dark:border-zinc-700">
            <input
              type="email"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
              placeholder="Email du patient"
              aria-label="Email du patient"
              className="w-full rounded border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-600"
            />
            <input
              type="text"
              value={form.practitioner}
              maxLength={120}
              onChange={(event) => setForm({ ...form, practitioner: event.target.value })}
              placeholder="Votre nom (facultatif)"
              aria-label="Votre nom"
              className="w-full rounded border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-600"
            />
            <textarea
              value={form.message}
              maxLength={2000}
              onChange={(event) => setForm({ ...form, message: event.target.value })}
              placeholder="Message au patient (facultatif)"
              aria-label="Message au patient"
              rows={3}
              className="w-full rounded border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-600"
            />
            <button
              type="button"
              onClick={send}
              disabled={!canSend}
              className="w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sending ? "Envoi…" : "Envoyer au patient"}
            </button>
            {sendError && <p role="alert" className="text-sm text-red-700">{sendError}</p>}
            {result && shareUrl && (
              <div className="space-y-2 rounded-lg bg-zinc-100 p-3 text-sm dark:bg-zinc-800" role="status">
                <p>{EMAIL_STATUS_MESSAGE[result.email_status]}</p>
                <input
                  readOnly
                  value={shareUrl}
                  aria-label="Lien de la page du patient"
                  onFocus={(event) => event.currentTarget.select()}
                  className="w-full rounded border border-zinc-300 bg-transparent px-2 py-1 text-xs dark:border-zinc-600"
                />
                <div className="flex gap-3">
                  <button type="button" onClick={copyLink} className="text-blue-700 underline dark:text-blue-400">
                    {copied ? "Copié" : "Copier le lien"}
                  </button>
                  <Link href={result.share_path} className="text-blue-700 underline dark:text-blue-400">
                    Voir la page patient
                  </Link>
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
