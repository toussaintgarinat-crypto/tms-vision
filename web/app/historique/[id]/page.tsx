"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AnalysisResult, AnalysisSummary } from "../../AnalysisResult";
import { Side } from "../../PostureAvatar3D";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type StoredAnalysis = AnalysisSummary & {
  id: string;
  created_at: string;
  side: Side;
  load_kg: number;
  wrist_twist: "normal" | "extreme";
  worker_label: string | null;
  poste_label: string | null;
};

export default function AnalysisDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  // État porteur de l'id auquel il correspond, comparé à `id` au rendu plutôt
  // que réinitialisé de façon synchrone en tête de l'effet -- même motif que
  // `recommendation` dans AnalysisResult.tsx, pour satisfaire
  // react-hooks/set-state-in-effect (voir Global Constraints).
  const [analysis, setAnalysis] = useState<{ id: string; data: StoredAnalysis } | null>(null);
  const [notFoundFor, setNotFoundFor] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/analyses/${id}`)
      .then((response) => {
        if (response.status === 404) {
          if (!cancelled) setNotFoundFor(id);
          return null;
        }
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<StoredAnalysis>;
      })
      .then((data) => {
        if (!cancelled && data) setAnalysis({ id, data });
      })
      .catch(() => {
        if (!cancelled) setNotFoundFor(id);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const isNotFound = notFoundFor === id;
  // Booléen simple (pas de narrowing TypeScript de `analysis` à travers une
  // variable dérivée) : uniquement pour la condition "Chargement..." ci-dessous.
  // Le rendu d'AnalysisResult re-teste `analysis && analysis.id === id` en
  // ligne pour que TypeScript le rétrécisse correctement.
  const isLoaded = analysis !== null && analysis.id === id;

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Analyse {id}</h1>
        <Link href="/historique" className="text-sm text-blue-600 underline">
          ← Retour à l&apos;historique
        </Link>
      </div>

      {isNotFound && <p className="text-red-600">Analyse introuvable.</p>}

      {!isNotFound && !isLoaded && <p>Chargement...</p>}

      {analysis && analysis.id === id && (
        <AnalysisResult
          analysisId={analysis.data.id}
          side={analysis.data.side}
          summary={analysis.data}
          videoUrl={`/analyses/${analysis.data.id}/video`}
          csvUrl={`/analyses/${analysis.data.id}/frames.csv`}
          pose3dUrl={`/analyses/${analysis.data.id}/pose3d`}
        />
      )}
    </main>
  );
}
