import Link from "next/link";

import {
  DRAFT_BADGE_TEXT,
  NO_PROGRAM_TEXT,
  VIDEO_MISSING_TEXT,
  capsuleVideoSrc,
} from "./programFormat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ProgramCapsule = {
  id: string;
  zone: string;
  kind: string;
  status: "draft" | "validated";
  title: string;
  description: string;
  video_url: string;
  // Vrai quand la vidéo a été générée (python -m tms_vision.capsule_build).
  video_available?: boolean;
};

export type ProgramItem = {
  rank: number;
  zone: string;
  capsule: ProgramCapsule;
  reason: string;
  load: number;
};

// Réservé à la correction du geste : l'API renvoie toujours une liste vide
// pour l'instant, et rien n'est affiché tant qu'elle l'est.
export type GestureCorrection = { title?: string; description?: string };

export function ProgramList({
  program,
  gestureCorrections = [],
}: {
  program: ProgramItem[];
  gestureCorrections?: GestureCorrection[];
}) {
  if (program.length === 0 && gestureCorrections.length === 0) {
    return (
      <p className="rounded border border-gray-300 bg-gray-50 p-3 text-sm text-gray-900">
        {NO_PROGRAM_TEXT}{" "}
        <Link href="/bibliotheque" className="text-blue-600 underline">
          Ouvrir la bibliothèque
        </Link>
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {program.length > 0 && (
        <div className="rounded border border-blue-200 bg-blue-50 p-3 text-gray-900">
          <h3 className="text-sm font-semibold">
            Programme d&apos;étirements ({program.length} capsule{program.length > 1 ? "s" : ""})
          </h3>
          <ol className="mt-2 flex flex-col gap-3">
            {program.map((item) => {
              const videoSrc = capsuleVideoSrc(item.capsule, API_URL);
              return (
                <li key={item.zone} className="flex gap-3">
                  <span className="font-semibold">{item.rank}.</span>
                  <div>
                    <p className="font-medium">{item.capsule.title}</p>
                    {item.capsule.status === "draft" && (
                      <p className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
                        {DRAFT_BADGE_TEXT}
                      </p>
                    )}
                    <p className="text-sm text-gray-700">{item.capsule.description}</p>
                    <p className="text-xs text-gray-600">{item.reason}</p>
                    {!videoSrc && (
                      <p className="mt-2 text-xs text-amber-800">{VIDEO_MISSING_TEXT}</p>
                    )}
                    {videoSrc && (
                      <video
                        controls
                        preload="metadata"
                        src={videoSrc}
                        className="mt-2 w-full max-w-sm rounded bg-black"
                      />
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {gestureCorrections.length > 0 && (
        <div className="rounded border border-green-200 bg-green-50 p-3 text-gray-900">
          <h3 className="text-sm font-semibold">Correction du geste</h3>
          <ul className="mt-2 flex flex-col gap-2">
            {gestureCorrections.map((correction, index) => (
              <li key={index}>
                <p className="font-medium">{correction.title}</p>
                <p className="text-sm text-gray-700">{correction.description}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
