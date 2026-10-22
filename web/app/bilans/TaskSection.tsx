"use client";

import { FormEvent, useState } from "react";

import { formatHours } from "./recurrenceFormat";
import {
  FREQUENCY_UNIT_LABELS,
  FrequencyUnit,
  SOURCE_LABELS,
  TimeSlot,
  formatSlots,
  slotsTotalHours,
  toCyclesPerMinute,
} from "./taskForm";
import { BilanItem, BilanTask, ZONES, ZONE_LABELS, Zone } from "./types";

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
  onChanged: () => void;
};

export function TaskSection({ bilanId, workdayHours, items, tasks, onChanged }: Props) {
  const [name, setName] = useState("");
  const [zones, setZones] = useState<Zone[]>([]);
  const [useSlots, setUseSlots] = useState(false);
  const [slots, setSlots] = useState<TimeSlot[]>([{ start: "", end: "" }]);
  const [hours, setHours] = useState("");
  const [frequency, setFrequency] = useState("");
  const [unit, setUnit] = useState<FrequencyUnit>("minute");
  const [cycleSeconds, setCycleSeconds] = useState("");
  const [staticSeconds, setStaticSeconds] = useState("");
  const [loadKg, setLoadKg] = useState("");
  const [daysPerWeek, setDaysPerWeek] = useState("");
  const [notes, setNotes] = useState("");
  const [analysisId, setAnalysisId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

    let cyclesPerMinute: number | null = null;
    const frequencyValue = optionalNumber(frequency);
    if (frequencyValue !== null) {
      const linkedHours = items.find((item) => item.analysis_id === analysisId)?.activity_hours;
      cyclesPerMinute = toCyclesPerMinute(frequencyValue, unit, activityHours ?? linkedHours ?? null);
      if (cyclesPerMinute === null) {
        return setError("Répétitions invalides (valeur positive, et durée connue si « par jour »).");
      }
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
          cycles_per_minute: cyclesPerMinute,
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
      setFrequency("");
      setCycleSeconds("");
      setStaticSeconds("");
      setLoadKg("");
      setDaysPerWeek("");
      setNotes("");
      setAnalysisId("");
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
                <span key={task.id} className="ml-2 rounded bg-blue-50 px-2 py-0.5 text-xs">
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
                <span className="rounded bg-gray-100 px-2 py-0.5 text-xs">
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
              {task.cycles_per_minute !== null && (
                <> · {task.cycles_per_minute.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} cycles/min</>
              )}
              {task.analysis_id && <> · complète la vidéo {task.analysis_id}</>}
            </span>
            {task.notes && <span className="text-gray-600">{task.notes}</span>}
          </li>
        ))}
        {items.length === 0 && tasks.length === 0 && (
          <li className="text-gray-600">Aucune tâche pour l&apos;instant.</li>
        )}
      </ul>

      <form onSubmit={handleSubmit} className="grid gap-4 rounded border p-4 sm:grid-cols-2">
        <h3 className="text-lg font-semibold sm:col-span-2">Ajouter une tâche</h3>
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          Nom de la tâche
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Peindre un plafond, saisie…"
            className={input}
          />
        </label>

        <fieldset className="flex flex-wrap gap-x-4 gap-y-1 text-sm sm:col-span-2">
          <legend className="mb-1">Zones concernées</legend>
          {ZONES.map((zone) => (
            <label key={zone} className="flex items-center gap-1">
              <input type="checkbox" checked={zones.includes(zone)} onChange={() => toggleZone(zone)} />
              {ZONE_LABELS[zone]}
            </label>
          ))}
        </fieldset>

        <div className="flex flex-col gap-2 text-sm sm:col-span-2">
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

        <label className="flex flex-col gap-1 text-sm">
          Répétitions
          <div className="flex gap-2">
            <input type="number" min="0" step="any" value={frequency} onChange={(e) => setFrequency(e.target.value)} className={`${input} w-28`} />
            <select value={unit} onChange={(e) => setUnit(e.target.value as FrequencyUnit)} className={input}>
              {(Object.keys(FREQUENCY_UNIT_LABELS) as FrequencyUnit[]).map((key) => (
                <option key={key} value={key}>{FREQUENCY_UNIT_LABELS[key]}</option>
              ))}
            </select>
          </div>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Durée d&apos;un cycle (secondes)
          <input type="number" min="0" step="any" value={cycleSeconds} onChange={(e) => setCycleSeconds(e.target.value)} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Plus longue tenue statique (secondes)
          <input type="number" min="0" step="any" value={staticSeconds} onChange={(e) => setStaticSeconds(e.target.value)} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Charge manipulée (kg)
          <input type="number" min="0" step="any" value={loadKg} onChange={(e) => setLoadKg(e.target.value)} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Jours par semaine
          <input type="number" min="1" max="7" step="any" value={daysPerWeek} onChange={(e) => setDaysPerWeek(e.target.value)} className={input} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Compléter une vidéo du bilan (facultatif)
          <select value={analysisId} onChange={(e) => setAnalysisId(e.target.value)} className={input}>
            <option value="">— Tâche sans vidéo —</option>
            {items.map((item) => (
              <option key={item.analysis_id} value={item.analysis_id}>
                {item.analysis_id} ({formatHours(item.activity_hours)})
              </option>
            ))}
          </select>
          <span className="text-xs text-gray-500">
            Les répétitions saisies remplacent la mesure de la vidéo pour les zones cochées.
          </span>
        </label>
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className={input} />
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
