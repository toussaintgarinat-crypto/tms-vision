"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "../../i18n/I18nProvider";
import {
  AvailableExercise,
  GestureCorrection,
  ProgramItem,
  ProgramList,
} from "../../ProgramList";
import { RecurrenceReport } from "../RecurrenceReport";
import { formatHours } from "../recurrenceFormat";
import { TaskSection } from "../TaskSection";
import { folderOptions } from "../folderTree";
import { BilanFolder, BilanReport, StoredBilan } from "../types";

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
  size: number;
  // null : programme automatique ; une liste : exercices choisis par le praticien.
  selection: string[] | null;
  available: AvailableExercise[];
  gesture_corrections: GestureCorrection[];
  warnings: string[];
  position?: "seated" | null;
  position_note?: string | null;
};

type LoadedBilan = { id: string; bilan: StoredBilan; report: BilanReport; program: BilanProgram };

export default function BilanDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t, tag } = useI18n();
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
  const [copyLabel, setCopyLabel] = useState("");
  const [copying, setCopying] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const [modelTitle, setModelTitle] = useState("");
  const [savingModel, setSavingModel] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const [savedModelTitle, setSavedModelTitle] = useState<string | null>(null);
  const [folders, setFolders] = useState<BilanFolder[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [filing, setFiling] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [programBusy, setProgramBusy] = useState(false);
  const [programError, setProgramError] = useState<string | null>(null);

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
          throw new Error(t("bilan.error.server"));
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
  }, [id, reloadToken, t]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/analyses`)
      .then((response) => {
        if (!response.ok) throw new Error(t("bilans.error.httpStatus", { status: response.status }));
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
  }, [t]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/bilan-folders`)
      .then((response) => (response.ok ? (response.json() as Promise<BilanFolder[]>) : []))
      .then((data) => {
        if (!cancelled) setFolders(data);
      })
      .catch(() => {
        if (!cancelled) setFolders([]);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

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
      setSubmitError(t("bilan.error.chooseAnalysis"));
      return;
    }
    if (!Number.isFinite(hours) || hours <= 0) {
      setSubmitError(t("bilan.error.activityHours"));
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
        let message = t("bilans.error.httpStatus", { status: response.status });
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
      setSubmitError(t("bilan.error.attach"));
    } finally {
      setSubmitting(false);
    }
  }

  // Copie le bilan (fiches d'activité, durée de la journée) pour le reprendre avec une autre
  // personne, puis ouvre la copie. Les vidéos de la personne d'origine ne sont pas copiées.
  async function handleDuplicate(event: FormEvent) {
    event.preventDefault();
    setCopying(true);
    setCopyError(null);
    try {
      const response = await fetch(`${API_URL}/bilans/${encodeURIComponent(id)}/duplicate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: copyLabel.trim() || null }),
      });
      if (!response.ok) {
        let message = t("bilans.error.httpStatus", { status: response.status });
        try {
          const body = (await response.json()) as { detail?: unknown };
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          // corps non JSON : on garde le message générique.
        }
        setCopyError(message);
        return;
      }
      const copy = (await response.json()) as StoredBilan;
      setCopyLabel("");
      router.push(`/bilans/${encodeURIComponent(copy.id)}`);
    } catch {
      setCopyError(t("bilan.error.duplicate"));
    } finally {
      setCopying(false);
    }
  }

  // Garde les fiches d'activité de ce bilan comme modèle de métier réutilisable (page
  // « Bibliothèque de métiers »). Les vidéos et les mesures ne sont pas conservées.
  async function handleSaveModel(event: FormEvent) {
    event.preventDefault();
    const title = modelTitle.trim();
    if (!title) {
      setModelError(t("bilan.error.modelName"));
      return;
    }
    setSavingModel(true);
    setModelError(null);
    setSavedModelTitle(null);
    try {
      const response = await fetch(`${API_URL}/bilans/${encodeURIComponent(id)}/metier`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      if (!response.ok) {
        let message = t("bilans.error.httpStatus", { status: response.status });
        try {
          const body = (await response.json()) as { detail?: unknown };
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          // corps non JSON : on garde le message générique.
        }
        setModelError(message);
        return;
      }
      setSavedModelTitle(title);
      setModelTitle("");
    } catch {
      setModelError(t("bilan.error.saveModel"));
    } finally {
      setSavingModel(false);
    }
  }

  // Enregistre le nombre d'exercices et la sélection du praticien (null : programme automatique).
  async function saveProgram(size: number, exerciseIds: string[] | null) {
    setProgramBusy(true);
    setProgramError(null);
    try {
      const response = await fetch(`${API_URL}/bilans/${encodeURIComponent(id)}/program`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ size, exercise_ids: exerciseIds }),
      });
      if (!response.ok) throw new Error(t("bilans.error.httpStatus", { status: response.status }));
      setReloadToken((token) => token + 1);
    } catch {
      setProgramError(t("bilan.error.saveProgram"));
    } finally {
      setProgramBusy(false);
    }
  }

  // Range ce bilan dans un dossier (chaîne vide : sans dossier).
  async function handleMove(folderId: string) {
    setFiling(true);
    setFileError(null);
    try {
      const response = await fetch(`${API_URL}/bilans/${encodeURIComponent(id)}/folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_id: folderId || null }),
      });
      if (!response.ok) throw new Error(t("bilans.error.httpStatus", { status: response.status }));
      setReloadToken((token) => token + 1);
    } catch {
      setFileError(t("bilan.error.move"));
    } finally {
      setFiling(false);
    }
  }

  // Archive, restaure ou supprime ce bilan. Archiver ou supprimer ramène à la liste.
  async function handleFile(action: "archive" | "unarchive" | "delete") {
    setFiling(true);
    setFileError(null);
    try {
      const url = `${API_URL}/bilans/${encodeURIComponent(id)}`;
      const response =
        action === "delete"
          ? await fetch(url, { method: "DELETE" })
          : await fetch(`${url}/${action}`, { method: "POST" });
      if (!response.ok) throw new Error(t("bilans.error.httpStatus", { status: response.status }));
      if (action === "unarchive") {
        setReloadToken((token) => token + 1);
      } else {
        router.push("/bilans");
      }
    } catch {
      setFileError(t("bilans.error.action"));
    } finally {
      setFiling(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {isLoaded ? (loaded.bilan.label ?? t("bilan.untitled")) : t("bilan.title")}
        </h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {isLoaded && (
            <Link href={`/bilans/${encodeURIComponent(id)}/rapport`} className="text-sm text-blue-600 underline">
              {t("detail.report")}
            </Link>
          )}
          <Link href="/bilans" className="text-sm text-blue-600 underline">
            {t("bilan.back")}
          </Link>
        </div>
      </div>

      {isLoaded && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {loaded.bilan.archived_at ? (
            <>
              <span className="rounded bg-amber-100 px-2 py-1 font-semibold text-amber-900">
                {t("bilan.archivedOn", { date: new Date(loaded.bilan.archived_at).toLocaleDateString(tag) })}
              </span>
              <button
                type="button"
                disabled={filing}
                onClick={() => handleFile("unarchive")}
                className="rounded border border-black px-3 py-1 disabled:opacity-50"
              >
                {t("bilans.restore")}
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={filing}
              onClick={() => handleFile("archive")}
              className="rounded border border-black px-3 py-1 disabled:opacity-50"
            >
              {t("bilan.archiveThis")}
            </button>
          )}
          <label className="flex items-center gap-2">
            {t("bilan.folder")}
            <select
              value={
                loaded.bilan.folder_id && folders.some((folder) => folder.id === loaded.bilan.folder_id)
                  ? loaded.bilan.folder_id
                  : ""
              }
              disabled={filing}
              onChange={(event) => handleMove(event.target.value)}
              className="rounded border p-1"
            >
              <option value="">{t("bilans.noFolder")}</option>
              {folderOptions(folders).map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {confirmDelete ? (
            <span className="flex items-center gap-2">
              <button
                type="button"
                disabled={filing}
                onClick={() => handleFile("delete")}
                className="rounded border border-red-600 px-3 py-1 text-red-600 disabled:opacity-50"
              >
                {t("bilans.deleteForever")}
              </button>
              <button type="button" onClick={() => setConfirmDelete(false)} className="underline">
                {t("common.cancel")}
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="rounded border px-3 py-1 text-red-600"
            >
              {t("bilans.delete")}
            </button>
          )}
          {fileError && <span className="text-red-600">{fileError}</span>}
        </div>
      )}

      {isNotFound && <p className="text-red-600">{t("bilan.notFound")}</p>}

      {isFetchError && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-red-600">
            {t("bilan.error.load")}
          </p>
          <button
            onClick={() => setReloadToken((token) => token + 1)}
            className="rounded border border-black px-3 py-1 text-sm"
          >
            {t("common.retry")}
          </button>
        </div>
      )}

      {!isNotFound && !isFetchError && !isLoaded && <p>{t("common.loading")}</p>}

      {loaded && loaded.id === id && (
        <>
          <form onSubmit={handleDuplicate} className="flex flex-col gap-2 rounded border p-4">
            <h2 className="text-lg font-semibold">{t("bilan.copy.title")}</h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {t("bilan.copy.help")}
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-sm">
                {t("bilan.copy.name")}
                <input
                  value={copyLabel}
                  onChange={(event) => setCopyLabel(event.target.value)}
                  placeholder={t("bilan.copy.placeholder", { name: loaded.bilan.label ?? t("bilan.copy.defaultName") })}
                  className="rounded border p-2"
                />
              </label>
              <button
                type="submit"
                disabled={copying}
                className="rounded border border-black px-3 py-2 text-sm disabled:opacity-50"
              >
                {copying ? t("bilan.copy.busy") : t("bilan.copy.button")}
              </button>
            </div>
            {copyError && <p className="text-sm text-red-600">{copyError}</p>}
          </form>

          {(loaded.bilan.tasks ?? []).length > 0 && (
            <form onSubmit={handleSaveModel} className="flex flex-col gap-2 rounded border p-4">
              <h2 className="text-lg font-semibold">{t("bilan.model.title")}</h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                {t("bilan.model.help")}
              </p>
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-sm">
                  {t("bilan.model.name")}
                  <input
                    value={modelTitle}
                    onChange={(event) => setModelTitle(event.target.value)}
                    placeholder={t("bilan.model.placeholder")}
                    className="rounded border p-2"
                  />
                </label>
                <button
                  type="submit"
                  disabled={savingModel}
                  className="rounded border border-black px-3 py-2 text-sm disabled:opacity-50"
                >
                  {savingModel ? t("bilan.model.busy") : t("bilan.model.button")}
                </button>
              </div>
              {modelError && <p className="text-sm text-red-600">{modelError}</p>}
              {savedModelTitle && (
                <p className="text-sm text-green-700 dark:text-green-400">
                  {t("bilan.model.saved", { title: savedModelTitle })}{" "}
                  <Link href="/metiers" className="underline">
                    {t("bilan.model.open")}
                  </Link>
                </p>
              )}
            </form>
          )}

          <form onSubmit={handleAttach} className="grid gap-4 rounded border p-4 sm:grid-cols-3">
            <h2 className="text-lg font-semibold sm:col-span-3">{t("bilan.attach.title")}</h2>
            <label className="flex flex-col gap-1 text-sm sm:col-span-2">
              {t("bilan.attach.analysis")}
              <select
                value={selectedAnalysisId}
                onChange={(event) => setSelectedAnalysisId(event.target.value)}
                className="rounded border p-2"
              >
                <option value="">{t("bilan.attach.choose")}</option>
                {availableOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {new Date(option.created_at).toLocaleString(tag)} ·{" "}
                    {option.poste_label ?? t("bilan.attach.unknownPost")} /{" "}
                    {option.worker_label ?? t("bilan.attach.unknownWorker")} ·{" "}
                    {t("bilan.attach.maxScore", { score: option.max_score })}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              {t("bilan.attach.hours")}
              <input
                type="number"
                min="0.25"
                step="0.25"
                value={activityHours}
                onChange={(event) => setActivityHours(event.target.value)}
                className="rounded border p-2"
              />
              <span className="text-xs text-gray-500">
                {t("bilan.attach.workday", { hours: formatHours(loaded.bilan.workday_hours) })}
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm sm:col-span-3">
              <input
                type="checkbox"
                checked={representative}
                onChange={(event) => setRepresentative(event.target.checked)}
              />
              {t("bilan.attach.representative")}
            </label>
            <div className="sm:col-span-3">
              <button
                type="submit"
                disabled={submitting}
                className="rounded border border-black px-3 py-1 text-sm disabled:opacity-50"
              >
                {t("bilan.attach.button")}
              </button>
              {submitError && <p className="mt-2 text-red-600">{submitError}</p>}
            </div>
          </form>

          <TaskSection
            bilanId={id}
            workdayHours={loaded.bilan.workday_hours}
            items={loaded.bilan.items ?? []}
            tasks={loaded.bilan.tasks ?? []}
            analyses={loaded.report.analyses}
            onChanged={() => setReloadToken((token) => token + 1)}
          />

          <RecurrenceReport report={loaded.report} />

          {(loaded.program.program.length > 0 ||
            loaded.program.gesture_corrections.length > 0 ||
            loaded.program.selection !== null) && (
            <section className="flex flex-col gap-3">
              <h2 className="text-xl font-semibold">{t("bilan.program.title")}</h2>
              {loaded.program.position_note && (
                <p className="text-sm text-gray-600">{loaded.program.position_note}</p>
              )}
              <ProgramList
                program={loaded.program.program}
                gestureCorrections={loaded.program.gesture_corrections}
                controls={{
                  size: loaded.program.size,
                  busy: programBusy,
                  selection: loaded.program.selection,
                  available: loaded.program.available,
                  onSizeChange: (size) => saveProgram(size, null),
                  onSelectionChange: (ids) => saveProgram(loaded.program.size, ids),
                }}
              />
              {programError && <p className="text-sm text-red-600">{programError}</p>}
            </section>
          )}
        </>
      )}
    </main>
  );
}
