"use client";

import { useEffect, useRef, useState } from "react";

import { LoadEditor } from "./LoadEditor";
import { LoadInfo, formatLoad, formatScoreRange, isVideoBadgeStale } from "./loadFormat";
import { PostureAvatar3D, Side } from "./PostureAvatar3D";
import { GestureCorrection, ProgramItem, ProgramList } from "./ProgramList";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AnalysisSummary = {
  frame_count: number;
  detected_frame_count: number;
  max_score: number;
  average_score: number;
  time_by_action_level: Record<string, number>;
};

type Recommendation = {
  zone: string | null;
  capsule: ProgramItem["capsule"] | null;
  program?: ProgramItem[];
  gesture_corrections?: GestureCorrection[];
  load?: LoadInfo;
};

// Réponse de PUT /analyses/{id}/load : l'analyse mise à jour.
type UpdatedAnalysis = AnalysisSummary & { load: LoadInfo };

const ZONE_LABELS: Record<string, string> = {
  neck: "cou",
  trunk: "tronc",
  upper_arm: "bras",
  lower_arm: "avant-bras",
  hand: "main",
  foot: "pied",
};

type AnalysisResultProps = {
  analysisId: string;
  side: Side;
  summary: AnalysisSummary;
  videoUrl: string;
  csvUrl: string;
  pose3dUrl: string;
};

export function AnalysisResult({
  analysisId,
  side,
  summary,
  videoUrl,
  csvUrl,
  pose3dUrl,
}: AnalysisResultProps) {
  const resultVideoRef = useRef<HTMLVideoElement | null>(null);
  const [recommendation, setRecommendation] = useState<{
    analysisId: string;
    data: Recommendation;
  } | null>(null);
  // Résumé et poids après une saisie de poids, portés par l'analyse à laquelle
  // ils correspondent (même motif que `recommendation`).
  const [updated, setUpdated] = useState<{
    analysisId: string;
    summary: AnalysisSummary;
    load: LoadInfo;
  } | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/analyses/${encodeURIComponent(analysisId)}/recommendation`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<Recommendation>;
      })
      .then((data) => {
        if (!cancelled) setRecommendation({ analysisId, data });
      })
      .catch(() => {
        // Erreur réseau ou analyse introuvable : on ne montre rien plutôt que
        // de bloquer l'affichage du résultat principal -- silence volontaire,
        // pas un oubli (voir revue finale de la tranche capsules).
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, refreshToken]);

  const currentRecommendation =
    recommendation?.analysisId === analysisId ? recommendation.data : null;
  const currentUpdate = updated?.analysisId === analysisId ? updated : null;
  const shownSummary = currentUpdate ? currentUpdate.summary : summary;
  const load = currentUpdate ? currentUpdate.load : (currentRecommendation?.load ?? null);

  function handleLoadUpdated(response: UpdatedAnalysis) {
    setUpdated({
      analysisId,
      summary: {
        frame_count: response.frame_count,
        detected_frame_count: response.detected_frame_count,
        max_score: response.max_score,
        average_score: response.average_score,
        time_by_action_level: response.time_by_action_level,
      },
      load: response.load,
    });
    // Les motifs du programme mentionnent le poids : on relit la recommandation.
    setRefreshToken((token) => token + 1);
  }

  return (
    <section className="flex flex-col gap-4 rounded border p-4">
      <h2 className="text-lg font-semibold">Résultat</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <video
          ref={resultVideoRef}
          src={`${API_URL}${videoUrl}`}
          controls
          className="w-full rounded-lg bg-black"
        />
        <PostureAvatar3D pose3dUrl={pose3dUrl} videoRef={resultVideoRef} side={side} />
      </div>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt>Frames analysées</dt>
        <dd>{summary.frame_count}</dd>
        <dt>Frames avec pose détectée</dt>
        <dd>{summary.detected_frame_count}</dd>
        <dt>Score RULA max</dt>
        <dd>{load ? formatScoreRange(shownSummary.max_score, load) : shownSummary.max_score}</dd>
        <dt>Score RULA moyen</dt>
        <dd>{shownSummary.average_score.toFixed(1)}</dd>
        {load && (
          <>
            <dt>Poids manipulé</dt>
            <dd>{formatLoad(load)}</dd>
          </>
        )}
      </dl>
      {load?.score_range && (
        <p className="text-xs text-gray-600">
          Les valeurs stockées (CSV, score moyen) correspondent au cas défavorable de la fourchette.
        </p>
      )}
      {load && isVideoBadgeStale(load) && (
        <p className="rounded border border-amber-400 bg-amber-50 p-2 text-sm text-amber-900">
          La vidéo annotée affiche le score calculé avec {load.original_load_kg} kg, le poids
          saisi à l&apos;analyse ; le résumé ci-dessus tient compte de {formatLoad(load)}.
        </p>
      )}
      {load && (
        <LoadEditor
          key={`${analysisId}:${load.kind}:${load.kg}:${load.kg_min}:${load.kg_max}`}
          analysisId={analysisId}
          load={load}
          onUpdated={handleLoadUpdated}
        />
      )}
      <a href={`${API_URL}${csvUrl}`} className="text-blue-600 underline">
        Télécharger le CSV détaillé
      </a>
      {currentRecommendation && currentRecommendation.program && (
        <ProgramList
          program={currentRecommendation.program}
          gestureCorrections={currentRecommendation.gesture_corrections}
        />
      )}
      {currentRecommendation && !currentRecommendation.program && currentRecommendation.capsule && (
        <div className="rounded border border-blue-200 bg-blue-50 p-3">
          <p className="text-sm font-semibold">
            Recommandation : zone{" "}
            {ZONE_LABELS[currentRecommendation.zone ?? ""] ?? currentRecommendation.zone}
          </p>
          <p className="font-medium">{currentRecommendation.capsule.title}</p>
          <p className="text-sm text-gray-700">{currentRecommendation.capsule.description}</p>
        </div>
      )}
    </section>
  );
}
