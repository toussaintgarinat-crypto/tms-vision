"use client";

import { useEffect, useRef, useState } from "react";

import { PostureAvatar3D, Side } from "./PostureAvatar3D";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AnalysisSummary = {
  frame_count: number;
  detected_frame_count: number;
  max_score: number;
  average_score: number;
  time_by_action_level: Record<string, number>;
};

type Capsule = {
  zone: string;
  title: string;
  description: string;
  video_url: string;
};

type Recommendation = {
  zone: string | null;
  capsule: Capsule | null;
};

const ZONE_LABELS: Record<string, string> = {
  neck: "cou",
  trunk: "tronc",
  upper_arm: "bras",
  lower_arm: "avant-bras",
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

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/analyses/${analysisId}/recommendation`)
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
  }, [analysisId]);

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
        <dd>{summary.max_score}</dd>
        <dt>Score RULA moyen</dt>
        <dd>{summary.average_score.toFixed(1)}</dd>
      </dl>
      <a href={`${API_URL}${csvUrl}`} className="text-blue-600 underline">
        Télécharger le CSV détaillé
      </a>
      {recommendation?.analysisId === analysisId && recommendation.data.capsule && (
        <div className="rounded border border-blue-200 bg-blue-50 p-3">
          <p className="text-sm font-semibold">
            Recommandation : zone{" "}
            {ZONE_LABELS[recommendation.data.zone ?? ""] ?? recommendation.data.zone}
          </p>
          <p className="font-medium">{recommendation.data.capsule.title}</p>
          <p className="text-sm text-gray-700">{recommendation.data.capsule.description}</p>
        </div>
      )}
    </section>
  );
}
