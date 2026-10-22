"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AnalysisSummary } from "../../../AnalysisResult";
import { LoadInfo, formatLoad } from "../../../loadFormat";
import { ProgramItem } from "../../../ProgramList";
import { ReportFrame } from "../../../ReportFrame";
import { formatSampleDuration } from "../../../bilans/recurrenceFormat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ACTION_LEVEL_LABELS: Record<string, string> = {
  acceptable: "Acceptable",
  investigation_recommandee: "Investigation recommandée",
  investigation_et_changement_bientot: "Investigation et changement bientôt",
  changement_immediat: "Changement immédiat",
};

type Recommendation = { program?: ProgramItem[]; load?: LoadInfo };
type Loaded = { id: string; summary: AnalysisSummary; recommendation: Recommendation };

// Compte rendu ANONYME d'une analyse seule : ni identifiant, ni nom de salarié ou de poste, ni
// vidéo d'origine. Seuls les résultats chiffrés et le programme d'étirements.
export default function AnalysisReportPage() {
  const params = useParams<{ id: string }>();
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
        if (!analysisResponse.ok || !recommendationResponse.ok) throw new Error("Erreur serveur");
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
  }, [id]);

  const current = loaded && loaded.id === id ? loaded : null;

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-8">
      <div className="tms-toolbar flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Compte rendu de l&apos;analyse</h1>
        <Link href={`/historique/${encodeURIComponent(id)}`} className="text-sm text-blue-600 underline">
          ← Retour à l&apos;analyse
        </Link>
      </div>

      {failedFor === id && <p className="text-red-600">Impossible de charger cette analyse.</p>}
      {!current && failedFor !== id && <p>Chargement...</p>}

      {current && (
        <ReportFrame title="Compte rendu d'analyse de posture" program={current.recommendation.program ?? []}>
          <h1>Compte rendu d&apos;analyse de posture</h1>
          <p className="muted">{new Date().toLocaleDateString("fr-FR")}</p>

          <h2>Résultat</h2>
          <table>
            <tbody>
              <tr>
                <td>Images analysées</td>
                <td>{current.summary.frame_count}</td>
              </tr>
              <tr>
                <td>Images avec posture détectée</td>
                <td>{current.summary.detected_frame_count}</td>
              </tr>
              <tr>
                <td>Score RULA maximal</td>
                <td>{current.summary.max_score}</td>
              </tr>
              <tr>
                <td>Score RULA moyen</td>
                <td>{current.summary.average_score.toFixed(1)}</td>
              </tr>
              {current.recommendation.load && (
                <tr>
                  <td>Poids manipulé</td>
                  <td>{formatLoad(current.recommendation.load)}</td>
                </tr>
              )}
            </tbody>
          </table>

          <h3>Temps passé par niveau d&apos;action</h3>
          <table>
            <tbody>
              {Object.entries(current.summary.time_by_action_level).map(([level, seconds]) => (
                <tr key={level}>
                  <td>{ACTION_LEVEL_LABELS[level] ?? level}</td>
                  <td>{formatSampleDuration(seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            Mesures sur un échantillon vidéo : elles ne représentent pas à elles seules une journée de
            travail (voir le compte rendu d&apos;un bilan de poste).
          </p>
        </ReportFrame>
      )}
    </main>
  );
}
