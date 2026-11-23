"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ZONES, Zone, zoneKey } from "../bilans/types";
import { useI18n } from "../i18n/I18nProvider";
import type { MetierModel, MetierTask } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Valeurs saisies pour une fiche type : les champs que le formulaire ne montre pas (fréquences par
// zone, durée de cycle…) sont conservés tels quels à la modification.
type TaskDraft = { base: Partial<MetierTask>; name: string; zones: Zone[]; hours: string; workstation: string; notes: string };

function toDraft(task?: MetierTask): TaskDraft {
  return {
    base: task ?? {},
    name: task?.name ?? "",
    zones: (task?.zones as Zone[] | undefined) ?? [],
    hours: task ? String(task.activity_hours) : "",
    workstation: task?.workstation ?? "",
    notes: task?.notes ?? "",
  };
}

function toTask(draft: TaskDraft): Record<string, unknown> {
  const task: Record<string, unknown> = {
    ...draft.base,
    name: draft.name.trim(),
    zones: draft.zones,
    activity_hours: Number(draft.hours.replace(",", ".")),
  };
  for (const key of ["workstation", "notes"] as const) {
    const value = draft[key].trim();
    if (value) task[key] = value;
    else delete task[key];
  }
  // Une fréquence par zone ne vaut que pour les zones restées cochées.
  const cycles = task.zone_cycles as Record<string, number> | undefined;
  if (cycles) task.zone_cycles = Object.fromEntries(Object.entries(cycles).filter(([zone]) => draft.zones.includes(zone as Zone)));
  return task;
}

// Formulaire de création ou de modification d'un modèle de métier du praticien. Le serveur revalide
// tout : ces contrôles ne servent qu'à guider la saisie.
export function MetierForm({ model }: { model?: MetierModel }) {
  const { t } = useI18n();
  const router = useRouter();
  const [title, setTitle] = useState(model?.title ?? "");
  const [description, setDescription] = useState(model?.description ?? "");
  const [workday, setWorkday] = useState(model ? String(model.workday_hours) : "8");
  const [tasks, setTasks] = useState<TaskDraft[]>(model?.tasks.length ? model.tasks.map(toDraft) : [toDraft()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const change = (index: number, patch: Partial<TaskDraft>) =>
    setTasks((current) => current.map((task, i) => (i === index ? { ...task, ...patch } : task)));
  const total = tasks.reduce((sum, task) => sum + (Number(task.hours.replace(",", ".")) || 0), 0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (tasks.some((task) => !task.name.trim() || task.zones.length === 0 || !(Number(task.hours.replace(",", ".")) > 0))) {
      setError(t("metiers.form.incomplete"));
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(model ? `${API_URL}/metiers/${encodeURIComponent(model.id)}` : `${API_URL}/metiers`, {
        method: model ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim() || null,
          workday_hours: Number(workday.replace(",", ".")),
          tasks: tasks.map(toTask),
        }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof body.detail === "string" ? body.detail : t("metiers.form.saveFailed"));
        return;
      }
      router.push("/metiers");
    } catch {
      setError(t("metiers.form.saveFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-5 p-6 sm:p-8">
      <Link href="/metiers" className="text-sm underline">{t("metiers.form.back")}</Link>
      <h1 className="text-2xl font-semibold">{model ? t("metiers.form.editTitle") : t("metiers.form.newTitle")}</h1>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">{t("metiers.form.help")}</p>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t("metiers.form.title")}
          <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} required className="rounded border p-2" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("metiers.form.description")}
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={2} className="rounded border p-2" />
        </label>
        <label className="flex flex-col gap-1 text-sm sm:w-48">
          {t("metiers.form.workday")}
          <input value={workday} onChange={(event) => setWorkday(event.target.value)} inputMode="decimal" required className="rounded border p-2" />
        </label>

        <h2 className="font-semibold">{t("metiers.form.tasks")}</h2>
        {tasks.map((task, index) => (
          <fieldset key={index} className="flex flex-col gap-3 rounded border p-3">
            <legend className="px-1 text-sm font-medium">{t("metiers.form.taskN", { number: index + 1 })}</legend>
            <label className="flex flex-col gap-1 text-sm">
              {t("metiers.form.taskName")}
              <input value={task.name} onChange={(event) => change(index, { name: event.target.value })} className="rounded border p-2" />
            </label>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <span className="w-full">{t("metiers.form.zones")}</span>
              {ZONES.map((zone) => (
                <label key={zone} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={task.zones.includes(zone)}
                    onChange={(event) => change(index, { zones: event.target.checked ? [...task.zones, zone] : task.zones.filter((z) => z !== zone) })}
                  />
                  {t(zoneKey(zone))}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap gap-3">
              <label className="flex flex-col gap-1 text-sm">
                {t("metiers.form.hours")}
                <input value={task.hours} onChange={(event) => change(index, { hours: event.target.value })} inputMode="decimal" className="w-28 rounded border p-2" />
              </label>
              <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-sm">
                {t("metiers.form.workstation")}
                <input value={task.workstation} onChange={(event) => change(index, { workstation: event.target.value })} className="rounded border p-2" />
              </label>
            </div>
            <label className="flex flex-col gap-1 text-sm">
              {t("metiers.form.notes")}
              <textarea value={task.notes} onChange={(event) => change(index, { notes: event.target.value })} rows={2} className="rounded border p-2" />
            </label>
            {tasks.length > 1 && (
              <button type="button" onClick={() => setTasks((current) => current.filter((_, i) => i !== index))} className="self-start text-sm text-red-600 underline">
                {t("metiers.form.removeTask")}
              </button>
            )}
          </fieldset>
        ))}
        <button type="button" onClick={() => setTasks((current) => [...current, toDraft()])} className="self-start rounded border px-3 py-2 text-sm">
          {t("metiers.form.addTask")}
        </button>
        <p className="text-sm text-zinc-600">{t("metiers.form.total", { total: total.toFixed(1), workday })}</p>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button type="submit" disabled={busy} className="self-start rounded border border-black px-4 py-2 text-sm disabled:opacity-50">
          {busy ? t("metiers.form.saving") : t("metiers.form.save")}
        </button>
      </form>
    </main>
  );
}
