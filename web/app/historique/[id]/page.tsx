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
  // react-hooks/set-state-in-effect (voir Global Constraints du plan).
  const [analysis, setAnalysis] = useState<{ id: string; data: StoredAnalysis } | null>(null);
  const [notFoundFor, setNotFoundFor] = useState<string | null>(null);
  // Distinct de notFoundFor : un 404 (analyse qui n'existe vraiment pas) et une
  // erreur réseau/serveur (l'analyse existe peut-être, on ne sait juste pas)
  // ne doivent pas afficher le même message -- l'un est définitif, l'autre
  // mérite une nouvelle tentative.
  const [fetchErrorFor, setFetchErrorFor] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/analyses/${encodeURIComponent(id)}`)
      .then((response) => {
        if (response.status === 404) {
          if (!cancelled) {
            setNotFoundFor(id);
            setFetchErrorFor(null);
          }
          return null;
        }
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<StoredAnalysis>;
      })
      .then((data) => {
        if (!cancelled && data) {
          setAnalysis({ id, data });
          setNotFoundFor(null);
          setFetchErrorFor(null);
        }
      })
      .catch(() => {
        if (!cancelled) setFetchErrorFor(id);
      });
    return () => {
      cancelled = true;
    };
  }, [id, retryToken]);

  const isNotFound = notFoundFor === id;
  const isFetchError = fetchErrorFor === id;
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

      {isFetchError && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-red-600">
            Impossible de charger cette analyse (problème réseau ou serveur).
          </p>
          <button
            onClick={() => setRetryToken((token) => token + 1)}
            className="rounded border border-black px-3 py-1 text-sm"
          >
            Réessayer
          </button>
        </div>
      )}

      {!isNotFound && !isFetchError && !isLoaded && <p>Chargement...</p>}

      {analysis && analysis.id === id && (
        <AnalysisResult
          analysisId={analysis.data.id}
          side={analysis.data.side}
          summary={analysis.data}
          videoUrl={`/analyses/${encodeURIComponent(analysis.data.id)}/video`}
          csvUrl={`/analyses/${encodeURIComponent(analysis.data.id)}/frames.csv`}
          pose3dUrl={`/analyses/${encodeURIComponent(analysis.data.id)}/pose3d`}
        />
      )}
    </main>
  );
}
