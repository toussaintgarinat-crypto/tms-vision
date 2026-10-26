"use client";

import { FormEvent, useState } from "react";

import { formatHours } from "./recurrenceFormat";
import {
  BREAK_OPTIONS,
  FREQUENCY_UNIT_LABELS,
  FrequencyUnit,
  OTHER_OPTION,
  SOURCE_LABELS,
  TimeSlot,
  WORKSTATION_OPTIONS,
  choiceValue,
  formatSlots,
  formatZoneCycles,
  slotsTotalHours,
  toCyclesPerMinute,
} from "./taskForm";
import { AssistantPanel } from "../assistant/AssistantPanel";
import {
  AssistantTaskFields,
  FIELD_LABELS,
  FilledKey,
  TaskFormState,
  applyTaskFields,
  taskFormToCurrentValues,
} from "../assistant/taskFill";
import { videoTaskFields } from "./videoFill";
import { BilanItem, BilanReportAnalysis, BilanTask, ZONES, ZONE_LABELS, Zone } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // corps non JSON : message générique.
  }
  return fallback;
}

function optionalNumber(text: string): number | null {
  if (text.trim() === "") return null;
  const value = Number(text.replace(",", "."));
  return Number.isFinite(value) ? value : Number.NaN;
}

type Props = {
  bilanId: string;
  workdayHours: number;
  items: BilanItem[];
  tasks: BilanTask[];
  // Mesures des vidéos du bilan : servent à pré-remplir la fiche d'une vidéo choisie.
  analyses?: BilanReportAnalysis[];
  onChanged: () => void;
};

export function TaskSection({ bilanId, workdayHours, items, tasks, analyses = [], onChanged }: Props) {
  const [name, setName] = useState("");
  const [zones, setZones] = useState<Zone[]>([]);
  const [useSlots, setUseSlots] = useState(false);
  const [slots, setSlots] = useState<TimeSlot[]>([{ start: "", end: "" }]);
  const [hours, setHours] = useState("");
  const [frequencies, setFrequencies] = useState<Partial<Record<Zone, string>>>({});
  const [unit, setUnit] = useState<FrequencyUnit>("minute");
  const [cycleSeconds, setCycleSeconds] = useState("");
  const [staticSeconds, setStaticSeconds] = useState("");
  const [loadKg, setLoadKg] = useState("");
  const [daysPerWeek, setDaysPerWeek] = useState("");
  const [notes, setNotes] = useState("");
  const [analysisId, setAnalysisId] = useState("");
  const [workstation, setWorkstation] = useState("");
  const [workstationOther, setWorkstationOther] = useState("");
  const [breaks, setBreaks] = useState("");
  const [breaksOther, setBreaksOther] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [aiFilled, setAiFilled] = useState<Set<FilledKey>>(new Set());
  const [videoNote, setVideoNote] = useState<string | null>(null);

  function formState(): TaskFormState {
    return {
      name, zones, useSlots, slots, hours, frequencies, unit, cycleSeconds, staticSeconds,
      loadKg, daysPerWeek, notes, workstation, workstationOther, breaks, breaksOther,
    };
  }

  function showForm(next: TaskFormState) {
    setName(next.name);
    setZones(next.zones);
    setUseSlots(next.useSlots);
    setSlots(next.slots);
    setHours(next.hours);
    setFrequencies(next.frequencies);
    setUnit(next.unit);
    setCycleSeconds(next.cycleSeconds);
    setStaticSeconds(next.staticSeconds);
    setLoadKg(next.loadKg);
    setDaysPerWeek(next.daysPerWeek);
    setNotes(next.notes);
    setWorkstation(next.workstation);
    setWorkstationOther(next.workstationOther);
    setBreaks(next.breaks);
    setBreaksOther(next.breaksOther);
  }

  function handleAssistantFields(fields: AssistantTaskFields, overwrite: boolean) {
    const result = applyTaskFields(formState(), fields, overwrite);
    showForm(result.state);
    setAiFilled((current) => new Set([...current, ...result.filled]));
    return result;
  }

  /** Choisir une vidéo à compléter pré-remplit la fiche d'après sa mesure (champs surlignés, à
   *  relire). Ce que le praticien a saisi lui-même est gardé ; ce qu'une vidéo précédente avait
   *  rempli est remplacé. */
  function handleChooseVideo(id: string) {
    setAnalysisId(id);
    setVideoNote(null);
    const analysis = analyses.find((candidate) => candidate.analysis_id === id);
    const item = items.find((candidate) => candidate.analysis_id === id);
    if (!analysis || !item) return;

    const base = formState();
    const cleared: TaskFormState = { ...base, frequencies: { ...base.frequencies } };
    if (aiFilled.has("zones")) cleared.zones = [];
    if (aiFilled.has("hours") || aiFilled.has("useSlots") || aiFilled.has("slots")) {
      cleared.hours = "";
      cleared.useSlots = false;
      cleared.slots = [{ start: "", end: "" }];
    }
    if (aiFilled.has("frequencies")) cleared.frequencies = {};
    if (aiFilled.has("cycleSeconds")) cleared.cycleSeconds = "";
    if (aiFilled.has("staticSeconds")) cleared.staticSeconds = "";

    const fields = videoTaskFields(analysis, item.activity_hours);
    const result = applyTaskFields(cleared, fields, false);
    showForm(result.state);
    setAiFilled((current) => {
      const next = new Set(current);
      for (const key of ["zones", "hours", "useSlots", "slots", "frequencies", "cycleSeconds", "staticSeconds"] as FilledKey[]) {
        next.delete(key);
      }
      return new Set([...next, ...result.filled]);
    });

    const parts = ["Rempli d'après la mesure de la vidéo : à relire (champs surlignés)."];
    if (fields.zones && fields.zones.length === 0) {
      parts.push("Aucune zone n'atteint une posture à risque sur cette vidéo : cochez les zones vous-même.");
    }
    if (result.kept.length > 0) {
      parts.push(`Gardé tel que vous l'aviez saisi : ${[...new Set(result.kept.map((key) => FIELD_LABELS[key]))].join(", ")}.`);
    }
    setVideoNote(parts.join(" "));
  }

  /** Surligne un champ rempli par l'assistant, jusqu'à l'envoi de la fiche. */
  function ai(...keys: FilledKey[]): string {
    return keys.some((key) => aiFilled.has(key)) ? " bg-yellow-50 ring-2 ring-yellow-400" : "";
  }

  function toggleZone(zone: Zone) {
    setZones((current) =>
      current.includes(zone) ? current.filter((z) => z !== zone) : [...current, zone],
    );
  }

  function updateSlot(index: number, field: keyof TimeSlot, value: string) {
    setSlots((current) =>
      current.map((slot, i) => (i === index ? { ...slot, [field]: value } : slot)),
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (name.trim() === "") return setError("Donnez un nom à la tâche.");
    if (zones.length === 0) return setError("Cochez au moins une zone concernée.");

    let activityHours: number | null = null;
    let timeSlots: TimeSlot[] | null = null;
    if (useSlots) {
      activityHours = slotsTotalHours(slots);
      if (activityHours === null) {
        return setError(
          "Plages horaires invalides : renseignez début et fin (la fin après le début, sans chevauchement).",
        );
      }
      timeSlots = slots;
    } else if (hours.trim() !== "") {
      activityHours = Number(hours.replace(",", "."));
      if (!Number.isFinite(activityHours) || activityHours <= 0) {
        return setError("La durée doit être supérieure à 0.");
      }
    } else if (!analysisId) {
      return setError("Indiquez la durée de la tâche ou ses plages horaires.");
    }

    const linkedHours = items.find((item) => item.analysis_id === analysisId)?.activity_hours;
    const zoneCycles: Partial<Record<Zone, number>> = {};
    for (const zone of zones) {
      const frequencyValue = optionalNumber(frequencies[zone] ?? "");
      if (frequencyValue === null) continue;
      const perMinute = toCyclesPerMinute(frequencyValue, unit, activityHours ?? linkedHours ?? null);
      if (perMinute === null) {
        return setError(
          `Répétitions invalides pour « ${ZONE_LABELS[zone]} » (valeur positive, et durée connue si « par jour »).`,
        );
      }
      zoneCycles[zone] = perMinute;
    }

    const cycle = optionalNumber(cycleSeconds);
    const held = optionalNumber(staticSeconds);
    const load = optionalNumber(loadKg);
    const days = optionalNumber(daysPerWeek);
    if ([cycle, held, load, days].some((value) => value !== null && Number.isNaN(value))) {
      return setError("Un des champs numériques n'est pas un nombre.");
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/bilans/${encodeURIComponent(bilanId)}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          zones,
          activity_hours: useSlots ? null : activityHours,
          time_slots: timeSlots,
          zone_cycles_per_minute: zoneCycles,
          workstation: choiceValue(workstation, workstationOther),
          breaks: choiceValue(breaks, breaksOther),
          cycle_seconds: cycle,
          static_seconds: held,
          load_kg: load,
          days_per_week: days,
          notes: notes.trim() === "" ? null : notes,
          analysis_id: analysisId || null,
          source: "practitioner",
        }),
      });
      if (!response.ok) {
        setError(await errorMessage(response, `Erreur ${response.status}`));
        return;
      }
      setName("");
      setZones([]);
      setUseSlots(false);
      setSlots([{ start: "", end: "" }]);
      setHours("");
      setFrequencies({});
      setWorkstation("");
      setWorkstationOther("");
      setBreaks("");
      setBreaksOther("");
      setCycleSeconds("");
      setStaticSeconds("");
      setLoadKg("");
      setDaysPerWeek("");
      setNotes("");
      setAnalysisId("");
      setAiFilled(new Set());
      setVideoNote(null);
      onChanged();
    } catch {
      setError("Impossible d'ajouter la tâche (problème réseau ou serveur).");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(task: BilanTask) {
    if (!window.confirm(`Supprimer la tâche « ${task.name} » ?`)) return;
    try {
      const response = await fetch(
        `${API_URL}/bilans/${encodeURIComponent(bilanId)}/tasks/${encodeURIComponent(task.id)}`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        setError(await errorMessage(response, `Erreur ${response.status}`));
        return;
      }
      onChanged();
    } catch {
      setError("Impossible de supprimer la tâche (problème réseau ou serveur).");
    }
  }

  const input = "rounded border p-2";

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">Tâches du poste</h2>

      <ul className="flex flex-col gap-2 text-sm">
        {items.map((item) => (
          <li key={item.analysis_id} className="flex flex-wrap justify-between gap-2 rounded border p-3">
            <span>
              Vidéo <span className="text-gray-600">{item.analysis_id}</span>
              {tasks.filter((task) => task.analysis_id === item.analysis_id).map((task) => (
                <span key={task.id} className="ml-2 rounded bg-blue-50 px-2 py-0.5 text-xs text-gray-900">
                  complétée par « {task.name} »
                </span>
              ))}
            </span>
            <span>
              {formatHours(item.activity_hours)} · {SOURCE_LABELS.measured}
            </span>
          </li>
        ))}
        {tasks.map((task) => (
          <li key={task.id} className="flex flex-col gap-1 rounded border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{task.name}</span>
              <span className="flex items-center gap-2">
                <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-900">
                  {SOURCE_LABELS[task.source]}
                </span>
                <button
                  onClick={() => handleDelete(task)}
                  className="rounded border border-red-600 px-2 py-0.5 text-xs text-red-600"
                >
                  Supprimer
                </button>
              </span>
            </div>
            <span className="text-gray-700">
              {task.zones.map((zone) => ZONE_LABELS[zone]).join(", ")} · {formatHours(task.activity_hours)}
              {task.time_slots && <> ({formatSlots(task.time_slots)})</>}
              {" · "}
              {formatZoneCycles(task.zone_cycles)}
              {task.analysis_id && <> · complète la vidéo {task.analysis_id}</>}
            </span>
            {(task.workstation || task.breaks) && (
              <span className="text-gray-600">
                {[task.workstation, task.breaks].filter(Boolean).join(" · ")}
              </span>
            )}
            {task.notes && <span className="text-gray-600">{task.notes}</span>}
          </li>
        ))}
        {items.length === 0 && tasks.length === 0 && (
          <li className="text-gray-600">Aucune tâche pour l&apos;instant.</li>
        )}
      </ul>

      <form onSubmit={handleSubmit} className="grid gap-4 rounded border p-4 sm:grid-cols-2">
        <h3 className="text-lg font-semibold sm:col-span-2">Ajouter une tâche</h3>
        <AssistantPanel
          values={taskFormToCurrentValues(formState())}
          onFields={handleAssistantFields}
        />
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          Nom de la tâche
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Peindre un plafond, saisie…"
            className={`${input}${ai("name")}`}
          />
        </label>

        <fieldset className={`flex flex-wrap gap-x-4 gap-y-1 rounded text-sm sm:col-span-2${ai("zones")}`}>
          <legend className="mb-1">Zones concernées</legend>
          {ZONES.map((zone) => (
            <label key={zone} className="flex items-center gap-1">
              <input type="checkbox" checked={zones.includes(zone)} onChange={() => toggleZone(zone)} />
              {ZONE_LABELS[zone]}
            </label>
          ))}
        </fieldset>

        <div className={`flex flex-col gap-2 rounded text-sm sm:col-span-2${ai("slots", "useSlots", "hours")}`}>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={useSlots} onChange={(e) => setUseSlots(e.target.checked)} />
            Je connais les horaires (plages) de cette tâche
          </label>
          {useSlots ? (
            <div className="flex flex-col gap-2">
              {slots.map((slot, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input type="time" value={slot.start} onChange={(e) => updateSlot(index, "start", e.target.value)} className={input} aria-label="Début" />
                  <span>à</span>
                  <input type="time" value={slot.end} onChange={(e) => updateSlot(index, "end", e.target.value)} className={input} aria-label="Fin" />
                  {slots.length > 1 && (
                    <button type="button" onClick={() => setSlots((c) => c.filter((_, i) => i !== index))} className="text-xs text-red-600 underline">
                      Retirer
                    </button>
                  )}
                </div>
              ))}
              <div className="flex items-center gap-3">
                <button type="button" onClick={() => setSlots((c) => [...c, { start: "", end: "" }])} className="self-start text-xs text-blue-600 underline">
                  Ajouter une plage
                </button>
                {slotsTotalHours(slots) !== null && (
                  <span className="text-xs text-gray-600">
                    Total : {formatHours(slotsTotalHours(slots) as number)} (journée de {formatHours(workdayHours)})
                  </span>
                )}
              </div>
            </div>
          ) : (
            <label className="flex flex-col gap-1">
              Durée de la tâche dans la journée (heures)
              <input type="number" min="0.25" step="0.25" value={hours} onChange={(e) => setHours(e.target.value)} className={input} />
            </label>
          )}
        </div>

        <fieldset className={`flex flex-col gap-2 rounded text-sm sm:col-span-2${ai("frequencies")}`}>
          <legend className="mb-1">Répétitions (une valeur par zone cochée)</legend>
          <select value={unit} onChange={(e) => setUnit(e.target.value as FrequencyUnit)} className={`${input} self-start`} aria-label="Unité des répétitions">
            {(Object.keys(FREQUENCY_UNIT_LABELS) as FrequencyUnit[]).map((key) => (
              <option key={key} value={key}>{FREQUENCY_UNIT_LABELS[key]}</option>
            ))}
          </select>
          {zones.length === 0 && <span className="text-gray-500">Cochez d&apos;abord les zones concernées.</span>}
          {ZONES.filter((zone) => zones.includes(zone)).map((zone) => (
            <label key={zone} className="flex items-center gap-2">
              <span className="w-44">{ZONE_LABELS[zone]}</span>
              <input
                type="number" min="0" step="any"
                value={frequencies[zone] ?? ""}
                onChange={(e) => setFrequencies((current) => ({ ...current, [zone]: e.target.value }))}
                className={`${input} w-28`}
              />
            </label>
          ))}
        </fieldset>
        <label className="flex flex-col gap-1 text-sm">
          Durée d&apos;un cycle (secondes)
          <input type="number" min="0" step="any" value={cycleSeconds} onChange={(e) => setCycleSeconds(e.target.value)} className={`${input}${ai("cycleSeconds")}`} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Plus longue tenue statique (secondes)
          <input type="number" min="0" step="any" value={staticSeconds} onChange={(e) => setStaticSeconds(e.target.value)} className={`${input}${ai("staticSeconds")}`} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Charge manipulée (kg)
          <input type="number" min="0" step="any" value={loadKg} onChange={(e) => setLoadKg(e.target.value)} className={`${input}${ai("loadKg")}`} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Jours par semaine
          <input type="number" min="1" max="7" step="any" value={daysPerWeek} onChange={(e) => setDaysPerWeek(e.target.value)} className={`${input}${ai("daysPerWeek")}`} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Compléter une vidéo du bilan (facultatif)
          <select value={analysisId} onChange={(e) => handleChooseVideo(e.target.value)} className={input}>
            <option value="">— Tâche sans vidéo —</option>
            {items.map((item) => (
              <option key={item.analysis_id} value={item.analysis_id}>
                {item.analysis_id} ({formatHours(item.activity_hours)})
              </option>
            ))}
          </select>
          <span className="text-xs text-gray-500">
            Choisir une vidéo pré-remplit la fiche d&apos;après sa mesure. Les répétitions saisies remplacent
            la mesure de la vidéo pour les zones où une valeur est donnée.
          </span>
          {videoNote && <span className="text-xs text-amber-800">{videoNote}</span>}
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Poste de travail
          <select value={workstation} onChange={(e) => setWorkstation(e.target.value)} className={`${input}${ai("workstation")}`}>
            <option value="">— Non précisé —</option>
            {WORKSTATION_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
            <option value={OTHER_OPTION}>{OTHER_OPTION}…</option>
          </select>
          {workstation === OTHER_OPTION && (
            <input value={workstationOther} onChange={(e) => setWorkstationOther(e.target.value)} className={input} aria-label="Poste de travail (précision)" />
          )}
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Pauses
          <select value={breaks} onChange={(e) => setBreaks(e.target.value)} className={`${input}${ai("breaks")}`}>
            <option value="">— Non précisé —</option>
            {BREAK_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
            <option value={OTHER_OPTION}>{OTHER_OPTION}…</option>
          </select>
          {breaks === OTHER_OPTION && (
            <input value={breaksOther} onChange={(e) => setBreaksOther(e.target.value)} className={input} aria-label="Pauses (précision)" />
          )}
        </label>
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className={`${input}${ai("notes")}`} />
        </label>

        <div className="sm:col-span-2">
          <button type="submit" disabled={submitting} className="rounded border border-black px-3 py-1 text-sm disabled:opacity-50">
            Ajouter la tâche
          </button>
          {error && <p className="mt-2 text-red-600">{error}</p>}
        </div>
      </form>
    </section>
  );
}
