import { formatCycles, formatHours, formatSampleDuration } from "./recurrenceFormat";
import { BilanReport, ZONES, ZONE_LABELS } from "./types";

const ASSESSMENT_LABELS = {
  repetitive: "Répétitif",
  not_repetitive: "Non répétitif",
} as const;

export function RecurrenceReport({ report }: { report: BilanReport }) {
  const includedAnalyses = report.analyses.filter((analysis) => analysis.included);
  const includedSampleSeconds = includedAnalyses.reduce(
    (total, analysis) => total + analysis.sample_seconds,
    0,
  );

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">Récurrence et charge journalière</h2>

      {!report.thresholds_calibrated && (
        <p className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900">
          Seuils non calibrés : les chiffres ci-dessous sont des mesures brutes, aucune zone n&apos;est
          classée « répétitive » ou « acceptable ».
        </p>
      )}

      {report.warnings.map((warning) => (
        <p key={warning} className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900">
          {warning}
        </p>
      ))}

      <p className="text-sm">
        Journée de {formatHours(report.workday_hours)} : {formatHours(report.documented_hours)}{" "}
        documentées
        {report.undocumented_hours > 0 && (
          <>, {formatHours(report.undocumented_hours)} non documentées</>
        )}
        .
      </p>

      {includedAnalyses.length > 0 && (
        <>
          <p className="text-sm text-gray-600">
            Estimation basée sur des échantillons de {formatSampleDuration(includedSampleSeconds)} au
            total ({includedAnalyses.length} vidéo{includedAnalyses.length > 1 ? "s" : ""}{" "}
            confirmée{includedAnalyses.length > 1 ? "s" : ""} représentative
            {includedAnalyses.length > 1 ? "s" : ""}).
          </p>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="p-2">Zone</th>
                  <th className="p-2">Cycles estimés sur la journée</th>
                  <th className="p-2">Temps estimé en posture à risque</th>
                </tr>
              </thead>
              <tbody>
                {ZONES.map((zone) => (
                  <tr key={zone} className="border-b">
                    <td className="p-2">{ZONE_LABELS[zone]}</td>
                    <td className="p-2">{formatCycles(report.zones[zone].projected_cycles)}</td>
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

      <h3 className="text-lg font-semibold">Vidéos du bilan</h3>
      {report.analyses.length === 0 && (
        <p className="text-gray-600">Aucune vidéo rattachée à ce bilan.</p>
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
                {formatHours(analysis.activity_hours)} d&apos;activité · échantillon de{" "}
                {formatSampleDuration(analysis.sample_seconds)}
              </span>
            </div>
            {!analysis.included && (
              <p className="mt-1 text-gray-600">
                Non confirmée représentative : exclue de la projection, mesures brutes
                ci-dessous.
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
                  <th className="p-1">Zone</th>
                  <th className="p-1">Cycles/min</th>
                  <th className="p-1">Durée moyenne d&apos;un cycle</th>
                  <th className="p-1">Plus longue plage statique</th>
                  <th className="p-1">Lecture</th>
                </tr>
              </thead>
              <tbody>
                {ZONES.map((zone) => {
                  const zoneValues = analysis.recurrence.zones[zone];
                  return (
                    <tr key={zone} className="border-b">
                      <td className="p-1">{ZONE_LABELS[zone]}</td>
                      <td className="p-1">
                        {zoneValues.cycles_per_minute === null
                          ? "—"
                          : zoneValues.cycles_per_minute.toLocaleString("fr-FR", {
                              maximumFractionDigits: 1,
                            })}
                      </td>
                      <td className="p-1">
                        {zoneValues.mean_cycle_seconds === null
                          ? "—"
                          : formatSampleDuration(zoneValues.mean_cycle_seconds)}
                      </td>
                      <td className="p-1">
                        {formatSampleDuration(zoneValues.longest_static_seconds)}
                      </td>
                      <td className="p-1">
                        {zoneValues.assessment === null
                          ? "—"
                          : ASSESSMENT_LABELS[zoneValues.assessment]}
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
