export type ProgramCapsule = {
  zone: string;
  kind: string;
  title: string;
  description: string;
  video_url: string;
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
  if (program.length === 0 && gestureCorrections.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      {program.length > 0 && (
        <div className="rounded border border-blue-200 bg-blue-50 p-3">
          <h3 className="text-sm font-semibold">
            Programme d&apos;étirements ({program.length} capsule{program.length > 1 ? "s" : ""})
          </h3>
          <ol className="mt-2 flex flex-col gap-3">
            {program.map((item) => (
              <li key={item.zone} className="flex gap-3">
                <span className="font-semibold">{item.rank}.</span>
                <div>
                  <p className="font-medium">{item.capsule.title}</p>
                  <p className="text-sm text-gray-700">{item.capsule.description}</p>
                  <p className="text-xs text-gray-600">{item.reason}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {gestureCorrections.length > 0 && (
        <div className="rounded border border-green-200 bg-green-50 p-3">
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
