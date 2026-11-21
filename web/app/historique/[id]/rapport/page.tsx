"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AnalysisSummary } from "../../../AnalysisResult";
import { useI18n } from "../../../i18n/I18nProvider";
import { LoadInfo, formatLoad } from "../../../loadFormat";
import { formatDecimal } from "../../../poseInfoFormat";
import { ProgramItem } from "../../../ProgramList";
import { ReportFrame } from "../../../ReportFrame";
import { formatSampleDuration } from "../../../bilans/recurrenceFormat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Niveaux d'action connus : leur nom est traduit (clé `actionLevel.<niveau>`), un niveau inconnu
// s'affiche tel que le serveur le donne.
const ACTION_LEVELS = [
  "acceptable",
  "investigation_recommandee",
  "investigation_et_changement_bientot",
  "changement_immediat",
];

type Recommendation = { program?: ProgramItem[]; load?: LoadInfo };
type Loaded = { id: string; summary: AnalysisSummary; recommendation: Recommendation };

// Compte rendu ANONYME d'une analyse seule : ni identifiant, ni nom de salarié ou de poste, ni
// vidéo d'origine. Seuls les résultats chiffrés et le programme d'étirements.
export default function AnalysisReportPage() {
  const params = useParams<{ id: string }>();
  const { t, tag } = useI18n();
  const id = params.id;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failedFor, setFailedFor] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const encoded = encodeURIComponent(id);
    Promise.all([
      fetch(`${API_URL}/analyses/${encoded}`),
      fetch(`${API_URL}/analyses/${encoded}/recommendation`),
    ])
      .then(async ([analysisResponse, recommendationResponse]) => {
        if (!analysisResponse.ok || !recommendationResponse.ok) throw new Error(t("bilan.error.server"));
        const summary = (await analysisResponse.json()) as AnalysisSummary;
        const recommendation = (await recommendationResponse.json()) as Recommendation;
        if (!cancelled) setLoaded({ id, summary, recommendation });
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
        <h1 className="text-2xl font-semibold">{t("analysisReport.pageTitle")}</h1>
        <Link href={`/historique/${encodeURIComponent(id)}`} className="text-sm text-blue-600 underline">
          {t("analysisReport.back")}
        </Link>
      </div>

      {failedFor === id && <p className="text-red-600">{t("detail.loadError")}</p>}
      {!current && failedFor !== id && <p>{t("common.loading")}</p>}

      {current && (
        <ReportFrame title={t("analysisReport.title")} program={current.recommendation.program ?? []}>
          <h1>{t("analysisReport.title")}</h1>
          <p className="muted">{new Date().toLocaleDateString(tag)}</p>

          <h2>{t("analysisReport.result")}</h2>
          <table>
            <tbody>
              <tr>
                <td>{t("analysisReport.frames")}</td>
                <td>{current.summary.frame_count}</td>
              </tr>
              <tr>
                <td>{t("analysisReport.detected")}</td>
                <td>{current.summary.detected_frame_count}</td>
              </tr>
              <tr>
                <td>{t("analysisReport.maxScore")}</td>
                <td>{current.summary.max_score}</td>
              </tr>
              <tr>
                <td>{t("analysisReport.avgScore")}</td>
                <td>{formatDecimal(current.summary.average_score, tag)}</td>
              </tr>
              {current.recommendation.load && (
                <tr>
                  <td>{t("analysisReport.load")}</td>
                  <td>{formatLoad(current.recommendation.load, t, tag)}</td>
                </tr>
              )}
            </tbody>
          </table>

          <h3>{t("analysisReport.timeByLevel")}</h3>
          <table>
            <tbody>
              {Object.entries(current.summary.time_by_action_level).map(([level, seconds]) => (
                <tr key={level}>
                  <td>{ACTION_LEVELS.includes(level) ? t(`actionLevel.${level}`) : level}</td>
                  <td>{formatSampleDuration(seconds, tag)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            {t("analysisReport.sampleNote")}
          </p>
        </ReportFrame>
      )}
    </main>
  );
}
