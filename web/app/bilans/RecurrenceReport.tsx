"use client";

import { useI18n } from "../i18n/I18nProvider";
import { formatCycles, formatHours, formatSampleDuration } from "./recurrenceFormat";
import { formatZoneCycles, sourceKey } from "./taskForm";
import { BilanReport, ZONES, zoneKey } from "./types";

export function RecurrenceReport({ report }: { report: BilanReport }) {
  const { t, tag } = useI18n();
  const includedAnalyses = report.analyses.filter((analysis) => analysis.included);
  const hasTasks = report.tasks.length > 0 || report.analyses.some((a) => a.declared.length > 0);
  const includedSampleSeconds = includedAnalyses.reduce(
    (total, analysis) => total + analysis.sample_seconds,
    0,
  );

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">{t("recurrence.title")}</h2>

      {!report.thresholds_calibrated && (
        <p className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900">
          {t("recurrence.uncalibrated")}
        </p>
      )}

      {report.warnings.map((warning) => (
        <p key={warning} className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900">
          {warning}
        </p>
      ))}

      <p className="text-sm">
        {t("recurrence.workday", {
          workday: formatHours(report.workday_hours),
          documented: formatHours(report.documented_hours),
        })}
        {report.undocumented_hours > 0 &&
          t("recurrence.undocumented", { hours: formatHours(report.undocumented_hours) })}
        .
      </p>

      {(includedAnalyses.length > 0 || hasTasks) && (
        <>
          {includedAnalyses.length > 0 && (
            <p className="text-sm text-gray-600">
              {t(includedAnalyses.length > 1 ? "recurrence.basis.other" : "recurrence.basis.one", {
                duration: formatSampleDuration(includedSampleSeconds, tag),
                count: includedAnalyses.length,
              })}
            </p>
          )}
          {hasTasks && (
            <p className="text-sm text-gray-600">
              {t("recurrence.cyclesNote")}
            </p>
          )}

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="p-2">{t("recurrence.col.zone")}</th>
                  <th className="p-2">{t("recurrence.col.cycles")}</th>
                  <th className="p-2">{t("recurrence.col.riskTime")}</th>
                </tr>
              </thead>
              <tbody>
                {ZONES.map((zone) => (
                  <tr key={zone} className="border-b">
                    <td className="p-2">{t(zoneKey(zone))}</td>
                    <td className="p-2">{formatCycles(report.zones[zone].projected_cycles, tag)}</td>
                    <td className="p-2">
                      {formatHours(report.zones[zone].projected_elevated_hours)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {report.tasks.length > 0 && (
        <>
          <h3 className="text-lg font-semibold">{t("recurrence.tasks")}</h3>
          <ul className="flex flex-col gap-3">
            {report.tasks.map((task) => (
              <li key={task.task_id} className="rounded border p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{task.name}</span>
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-900">
                    {t(sourceKey(task.source))}
                  </span>
                </div>
                <p className="text-gray-700">
                  {task.zones.map((zone) => t(zoneKey(zone))).join(", ")} ·{" "}
                  {formatHours(task.activity_hours)} ·{" "}
                  {formatZoneCycles(task.zone_cycles, t, tag)}
                </p>
                {task.warnings.map((warning) => (
                  <p key={warning} className="mt-1 text-amber-800">
                    {warning}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </>
      )}

      <h3 className="text-lg font-semibold">{t("recurrence.videos")}</h3>
      {report.analyses.length === 0 && (
        <p className="text-gray-600">{t("recurrence.noVideo")}</p>
      )}
      <ul className="flex flex-col gap-3">
        {report.analyses.map((analysis) => (
          <li key={analysis.analysis_id} className="rounded border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <a
                href={`/historique/${encodeURIComponent(analysis.analysis_id)}`}
                className="text-blue-600 underline"
              >
                {analysis.analysis_id}
              </a>
              <span>
                {t("recurrence.videoSummary", {
                  hours: formatHours(analysis.activity_hours),
                  sample: formatSampleDuration(analysis.sample_seconds, tag),
                })}
              </span>
            </div>
            {analysis.declared.map((declared) => (
              <p key={declared.task_id} className="mt-1 rounded bg-blue-50 p-2 text-blue-900">
                {t("recurrence.declaredReplaces", {
                  name: declared.name,
                  source: t(sourceKey(declared.source)),
                })}{" "}
                {declared.zones
                  .filter((zone) => declared.zone_cycles[zone] !== undefined)
                  .map((zone) => {
                    const measured = declared.measured_cycles_per_minute[zone];
                    const format = (value: number | null | undefined) =>
                      value == null
                        ? "—"
                        : value.toLocaleString(tag, { maximumFractionDigits: 1 });
                    return t("recurrence.declaredZone", {
                      zone: t(zoneKey(zone)),
                      declared: format(declared.zone_cycles[zone]),
                      measured: format(measured),
                    });
                  })
                  .join(" ; ")}
                .
              </p>
            ))}
            {!analysis.included && (
              <p className="mt-1 text-gray-600">
                {t("recurrence.excluded")}
              </p>
            )}
            {analysis.warnings.map((warning) => (
              <p key={warning} className="mt-1 text-amber-800">
                {warning}
              </p>
            ))}
            <table className="mt-2 w-full border-collapse text-xs">
              <thead>
                <tr className="border-b text-left">
                  <th className="p-1">{t("recurrence.col.zone")}</th>
                  <th className="p-1">{t("recurrence.col.cyclesPerMinute")}</th>
                  <th className="p-1">{t("recurrence.col.meanCycle")}</th>
                  <th className="p-1">{t("recurrence.col.longestStatic")}</th>
                  <th className="p-1">{t("recurrence.col.reading")}</th>
                </tr>
              </thead>
              <tbody>
                {ZONES.map((zone) => {
                  const zoneValues = analysis.recurrence.zones[zone];
                  return (
                    <tr key={zone} className="border-b">
                      <td className="p-1">{t(zoneKey(zone))}</td>
                      <td className="p-1">
                        {zoneValues.cycles_per_minute === null
                          ? "—"
                          : zoneValues.cycles_per_minute.toLocaleString(tag, {
                              maximumFractionDigits: 1,
                            })}
                      </td>
                      <td className="p-1">
                        {zoneValues.mean_cycle_seconds === null
                          ? "—"
                          : formatSampleDuration(zoneValues.mean_cycle_seconds, tag)}
                      </td>
                      <td className="p-1">
                        {formatSampleDuration(zoneValues.longest_static_seconds, tag)}
                      </td>
                      <td className="p-1">
                        {zoneValues.assessment === null
                          ? "—"
                          : t(`recurrence.assessment.${zoneValues.assessment}`)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </li>
        ))}
      </ul>
    </section>
  );
}
