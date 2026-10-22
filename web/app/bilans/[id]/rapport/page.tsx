"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ProgramItem } from "../../../ProgramList";
import { ReportFrame } from "../../../ReportFrame";
import { formatCycles, formatHours } from "../../recurrenceFormat";
import { SOURCE_LABELS, formatSlots, formatZoneCycles } from "../../taskForm";
import { BilanReport, StoredBilan, ZONES, ZONE_LABELS } from "../../types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type BilanProgram = { program: ProgramItem[]; warnings: string[]; position_note?: string | null };
type Loaded = { id: string; bilan: StoredBilan; report: BilanReport; program: BilanProgram };

// Compte rendu ANONYME d'un bilan de poste : ni identifiant d'analyse, ni nom de salarié, ni
// notes libres. Le libellé du bilan (souvent un nom de lieu ou de poste) n'apparaît que si on
// le demande.
export default function BilanReportPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failedFor, setFailedFor] = useState<string | null>(null);
  const [includeLabel, setIncludeLabel] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const encoded = encodeURIComponent(id);
    Promise.all([
      fetch(`${API_URL}/bilans/${encoded}`),
      fetch(`${API_URL}/bilans/${encoded}/recurrence`),
      fetch(`${API_URL}/bilans/${encoded}/program`),
    ])
      .then(async ([bilanResponse, reportResponse, programResponse]) => {
        if (!bilanResponse.ok || !reportResponse.ok || !programResponse.ok) {
          throw new Error("Erreur serveur");
        }
        const bilan = (await bilanResponse.json()) as StoredBilan;
        const report = (await reportResponse.json()) as BilanReport;
        const program = (await programResponse.json()) as BilanProgram;
        if (!cancelled) setLoaded({ id, bilan, report, program });
      })
      .catch(() => {
        if (!cancelled) setFailedFor(id);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const current = loaded && loaded.id === id ? loaded : null;

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-8">
      <div className="tms-toolbar flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Compte rendu du bilan</h1>
        <Link href={`/bilans/${encodeURIComponent(id)}`} className="text-sm text-blue-600 underline">
          ← Retour au bilan
        </Link>
      </div>

      {failedFor === id && <p className="text-red-600">Impossible de charger ce bilan.</p>}
      {!current && failedFor !== id && <p>Chargement...</p>}

      {current && (
        <>
          <label className="tms-toolbar flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeLabel} onChange={(e) => setIncludeLabel(e.target.checked)} />
            Inclure le libellé du bilan (« {current.bilan.label ?? "sans libellé"} ») dans le compte rendu
          </label>
          <ReportFrame title="Compte rendu de bilan de poste" program={current.program.program}>
            <BilanReportBody loaded={current} includeLabel={includeLabel} />
          </ReportFrame>
        </>
      )}
    </main>
  );
}

function BilanReportBody({ loaded, includeLabel }: { loaded: Loaded; includeLabel: boolean }) {
  const { bilan, report, program } = loaded;
  const tasks = bilan.tasks ?? [];
  const warnings = [...report.warnings, ...program.warnings.filter((w) => !report.warnings.includes(w))];
  return (
    <>
      <h1>Compte rendu de bilan de poste</h1>
      <p className="muted">
        {new Date().toLocaleDateString("fr-FR")}
        {includeLabel && bilan.label ? ` · ${bilan.label}` : ""}
      </p>

      <h2>Journée de travail</h2>
      <p>
        Journée de {formatHours(report.workday_hours)} : {formatHours(report.documented_hours)} documentées
        {report.undocumented_hours > 0 && <>, {formatHours(report.undocumented_hours)} non documentées</>}.
      </p>
      {!report.thresholds_calibrated && (
        <p className="warn">
          Seuils non calibrés : les chiffres sont des mesures brutes, aucune zone n&apos;est classée
          « répétitive » ou « acceptable ».
        </p>
      )}
      {warnings.map((warning) => (
        <p key={warning} className="warn">
          {warning}
        </p>
      ))}

      <h2>Tâches du poste</h2>
      <table>
        <thead>
          <tr>
            <th>Tâche</th>
            <th>Origine</th>
            <th>Durée</th>
            <th>Répétitions</th>
          </tr>
        </thead>
        <tbody>
          {report.analyses.map((analysis, index) => (
            <tr key={analysis.analysis_id}>
              <td>Activité filmée {index + 1}</td>
              <td>{SOURCE_LABELS.measured}</td>
              <td>{formatHours(analysis.activity_hours)}</td>
              <td>
                {analysis.declared.length > 0
                  ? analysis.declared
                      .map((declared) => `${declared.name} (${SOURCE_LABELS[declared.source]}) : ${formatZoneCycles(declared.zone_cycles)}`)
                      .join(" ; ")
                  : "mesurées sur la vidéo"}
              </td>
            </tr>
          ))}
          {tasks
            .filter((task) => task.analysis_id === null)
            .map((task) => (
              <tr key={task.id}>
                <td>
                  {task.name}
                  {(task.workstation || task.breaks) && (
                    <div className="muted">{[task.workstation, task.breaks].filter(Boolean).join(" · ")}</div>
                  )}
                </td>
                <td>{SOURCE_LABELS[task.source]}</td>
                <td>
                  {formatHours(task.activity_hours)}
                  {task.time_slots && <div className="muted">{formatSlots(task.time_slots)}</div>}
                </td>
                <td>
                  {Object.keys(task.zone_cycles).length > 0
                    ? formatZoneCycles(task.zone_cycles)
                    : `${task.zones.map((zone) => ZONE_LABELS[zone]).join(", ")} : répétitions non renseignées`}
                </td>
              </tr>
            ))}
        </tbody>
      </table>

      <h2>Cycles et temps en posture à risque</h2>
      <table>
        <thead>
          <tr>
            <th>Zone</th>
            <th>Cycles estimés sur la journée</th>
            <th>Temps estimé en posture à risque</th>
          </tr>
        </thead>
        <tbody>
          {ZONES.map((zone) => (
            <tr key={zone}>
              <td>{ZONE_LABELS[zone]}</td>
              <td>{formatCycles(report.zones[zone].projected_cycles)}</td>
              <td>{formatHours(report.zones[zone].projected_elevated_hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        Les tâches saisies sans vidéo n&apos;ont ni score RULA ni temps en posture à risque mesurés.
      </p>
      {program.position_note && <p className="muted">{program.position_note}</p>}
    </>
  );
}
