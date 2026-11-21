"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "../../../i18n/I18nProvider";
import { ProgramItem } from "../../../ProgramList";
import { ReportFrame } from "../../../ReportFrame";
import { formatCycles, formatHours } from "../../recurrenceFormat";
import { choiceLabel, formatSlots, formatZoneCycles, sourceKey } from "../../taskForm";
import { BilanReport, StoredBilan, ZONES, zoneKey } from "../../types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type BilanProgram = { program: ProgramItem[]; warnings: string[]; position_note?: string | null };
type Loaded = { id: string; bilan: StoredBilan; report: BilanReport; program: BilanProgram };

// Compte rendu ANONYME d'un bilan de poste : ni identifiant d'analyse, ni nom de salarié, ni
// notes libres. Le libellé du bilan (souvent un nom de lieu ou de poste) n'apparaît que si on
// le demande.
export default function BilanReportPage() {
  const params = useParams<{ id: string }>();
  const { t } = useI18n();
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
          throw new Error(t("bilan.error.server"));
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
  }, [id, t]);

  const current = loaded && loaded.id === id ? loaded : null;

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-8">
      <div className="tms-toolbar flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("bilanReport.pageTitle")}</h1>
        <Link href={`/bilans/${encodeURIComponent(id)}`} className="text-sm text-blue-600 underline">
          {t("bilanReport.back")}
        </Link>
      </div>

      {failedFor === id && <p className="text-red-600">{t("bilanReport.loadError")}</p>}
      {!current && failedFor !== id && <p>{t("common.loading")}</p>}

      {current && (
        <>
          <label className="tms-toolbar flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeLabel} onChange={(e) => setIncludeLabel(e.target.checked)} />
            {t("bilanReport.includeLabel", { label: current.bilan.label ?? t("bilanReport.noLabel") })}
          </label>
          <ReportFrame title={t("bilanReport.title")} program={current.program.program}>
            <BilanReportBody loaded={current} includeLabel={includeLabel} />
          </ReportFrame>
        </>
      )}
    </main>
  );
}

function BilanReportBody({ loaded, includeLabel }: { loaded: Loaded; includeLabel: boolean }) {
  const { t, tag } = useI18n();
  const { bilan, report, program } = loaded;
  const tasks = bilan.tasks ?? [];
  const warnings = [...report.warnings, ...program.warnings.filter((w) => !report.warnings.includes(w))];
  return (
    <>
      <h1>{t("bilanReport.title")}</h1>
      <p className="muted">
        {new Date().toLocaleDateString(tag)}
        {includeLabel && bilan.label ? ` · ${bilan.label}` : ""}
      </p>

      <h2>{t("bilanReport.workday")}</h2>
      <p>
        {t("recurrence.workday", {
          workday: formatHours(report.workday_hours),
          documented: formatHours(report.documented_hours),
        })}
        {report.undocumented_hours > 0 &&
          t("recurrence.undocumented", { hours: formatHours(report.undocumented_hours) })}
        .
      </p>
      {!report.thresholds_calibrated && (
        <p className="warn">
          {t("bilanReport.uncalibrated")}
        </p>
      )}
      {warnings.map((warning) => (
        <p key={warning} className="warn">
          {warning}
        </p>
      ))}

      <h2>{t("bilanReport.tasks")}</h2>
      <table>
        <thead>
          <tr>
            <th>{t("bilanReport.col.task")}</th>
            <th>{t("bilanReport.col.source")}</th>
            <th>{t("bilanReport.col.duration")}</th>
            <th>{t("bilanReport.col.repetitions")}</th>
          </tr>
        </thead>
        <tbody>
          {report.analyses.map((analysis, index) => (
            <tr key={analysis.analysis_id}>
              <td>{t("bilanReport.filmedActivity", { index: index + 1 })}</td>
              <td>{t(sourceKey("measured"))}</td>
              <td>{formatHours(analysis.activity_hours)}</td>
              <td>
                {analysis.declared.length > 0
                  ? analysis.declared
                      .map((declared) => `${declared.name} (${t(sourceKey(declared.source))}) : ${formatZoneCycles(declared.zone_cycles, t, tag)}`)
                      .join(" ; ")
                  : t("bilanReport.measuredOnVideo")}
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
                    <div className="muted">{[
                        task.workstation && choiceLabel(t, "workstation", task.workstation),
                        task.breaks && choiceLabel(t, "breaks", task.breaks),
                      ]
                        .filter(Boolean)
                        .join(" · ")}</div>
                  )}
                </td>
                <td>{t(sourceKey(task.source))}</td>
                <td>
                  {formatHours(task.activity_hours)}
                  {task.time_slots && <div className="muted">{formatSlots(task.time_slots)}</div>}
                </td>
                <td>
                  {Object.keys(task.zone_cycles).length > 0
                    ? formatZoneCycles(task.zone_cycles, t, tag)
                    : t("bilanReport.cyclesMissing", { zones: task.zones.map((zone) => t(zoneKey(zone))).join(", ") })}
                </td>
              </tr>
            ))}
        </tbody>
      </table>

      <h2>{t("bilanReport.cyclesTitle")}</h2>
      <table>
        <thead>
          <tr>
            <th>{t("recurrence.col.zone")}</th>
            <th>{t("recurrence.col.cycles")}</th>
            <th>{t("recurrence.col.riskTime")}</th>
          </tr>
        </thead>
        <tbody>
          {ZONES.map((zone) => (
            <tr key={zone}>
              <td>{t(zoneKey(zone))}</td>
              <td>{formatCycles(report.zones[zone].projected_cycles, tag)}</td>
              <td>{formatHours(report.zones[zone].projected_elevated_hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        {t("bilanReport.noVideoNote")}
      </p>
      {program.position_note && <p className="muted">{program.position_note}</p>}
    </>
  );
}
