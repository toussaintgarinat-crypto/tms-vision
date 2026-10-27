"use client";

import {
  CustomPointMetrics,
  DetectionQuality,
  HandSideMetrics,
  confidenceLabel,
  customDisplayName,
  formatDegrees,
  formatPercent,
  formatRate,
  formatSeconds,
  handSideLabel,
} from "./poseInfoFormat";
import { GROUP_LEGEND, StoredPoseOptions, groupsForOptions, poseModelLabel } from "./poseModels";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Ce que l'API renvoie sur le modèle de pose d'une analyse (création ou lecture). */
export type PoseAnalysisInfo = {
  pose_model?: string | null;
  pose_options?: StoredPoseOptions | null;
  keypoint_count?: number | null;
  detection_quality?: DetectionQuality | null;
  hands_metrics?: Record<string, HandSideMetrics> | null;
  custom_metrics?: Record<string, CustomPointMetrics> | null;
};

/** Le modèle whole-body est en 2D : pas de points « monde », donc pas d'avatar 3D. */
export function hasAvatar3D(info: PoseAnalysisInfo | null | undefined): boolean {
  return !(info?.pose_options?.enable_wholebody || info?.pose_model === "rtmpose_wholebody_133");
}

function hasExtraKeypoints(info: PoseAnalysisInfo): boolean {
  const options = info.pose_options;
  return Boolean(options?.enable_hands || options?.enable_wholebody || options?.custom_points);
}

export function PoseInfoPanel({ analysisId, info }: { analysisId: string; info: PoseAnalysisInfo }) {
  const quality = info.detection_quality ?? null;
  const groups = groupsForOptions(info.pose_options);
  const confidence = quality?.avg_confidence ?? null;

  return (
    <section className="flex flex-col gap-3 rounded border p-3 text-sm" aria-label="Modèle de pose">
      <h3 className="font-semibold">Modèle de pose</h3>
      <dl className="grid grid-cols-2 gap-2">
        <dt>Modèle</dt>
        <dd>{poseModelLabel(info.pose_model)}</dd>
        <dt>Points par personne</dt>
        <dd>{info.keypoint_count ?? 33}</dd>
        {quality && (
          <>
            <dt>Points détectés par image</dt>
            <dd>{quality.frames_with_points > 0 ? quality.avg_keypoints_per_frame : "—"}</dd>
            <dt>Confiance de détection</dt>
            <dd>
              {confidence === null ? (
                "—"
              ) : (
                <span className="flex items-center gap-2">
                  <span
                    className="h-2 w-24 overflow-hidden rounded bg-gray-200"
                    role="meter"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(confidence * 100)}
                    aria-label="Confiance moyenne de détection"
                  >
                    <span className="block h-full bg-green-600" style={{ width: `${Math.round(confidence * 100)}%` }} />
                  </span>
                  {formatPercent(confidence)} ({confidenceLabel(confidence)})
                </span>
              )}
            </dd>
          </>
        )}
      </dl>

      <div className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Couleurs de la vidéo annotée">
        {GROUP_LEGEND.filter((entry) => groups.includes(entry.group)).map((entry) => (
          <span key={entry.group} className="flex items-center gap-1 text-xs">
            <span
              className="inline-block h-3 w-3 rounded-full border border-gray-400"
              style={{ backgroundColor: entry.color }}
            />
            {entry.label}
          </span>
        ))}
      </div>

      {!hasAvatar3D(info) && (
        <p className="text-xs text-gray-600">
          Ce modèle travaille en 2D : l&apos;avatar 3D et l&apos;angle de cheville ne sont pas disponibles.
        </p>
      )}

      {info.hands_metrics && (
        <div className="flex flex-col gap-1">
          <h4 className="font-medium">Mains</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-gray-600">
                  <th className="pr-2 font-normal">Côté</th>
                  <th className="pr-2 font-normal">Détectée</th>
                  <th className="pr-2 font-normal">Flexion doigts (moy. / max)</th>
                  <th className="pr-2 font-normal">Préhensions</th>
                  <th className="pr-2 font-normal">Durée</th>
                  <th className="font-normal">Cadence</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(info.hands_metrics).map(([side, metrics]) => (
                  <tr key={side} className="border-t">
                    <td className="pr-2 py-1">{handSideLabel(side)}</td>
                    <td className="pr-2">{formatPercent(metrics.detection_ratio)}</td>
                    <td className="pr-2">
                      {formatDegrees(metrics.finger_curl_mean_deg)} / {formatDegrees(metrics.finger_curl_max_deg)}
                    </td>
                    <td className="pr-2">{metrics.grasp_count}</td>
                    <td className="pr-2">{formatSeconds(metrics.grasp_seconds)}</td>
                    <td>
                      {formatRate(metrics.grasps_per_minute)}
                      {metrics.repetitive && (
                        <span className="ml-1 rounded bg-amber-100 px-1 text-amber-900">répétitif</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-600">
            Seuils non calibrés. Les doigts ne sont pas mesurés quand la main est trop petite dans l&apos;image.
          </p>
        </div>
      )}

      {info.custom_metrics && Object.keys(info.custom_metrics).length > 0 && (
        <div className="flex flex-col gap-1">
          <h4 className="font-medium">Points personnalisés</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-gray-600">
                  <th className="pr-2 font-normal">Point</th>
                  <th className="pr-2 font-normal">Suivi</th>
                  <th className="pr-2 font-normal">Déplacement</th>
                  <th className="font-normal">À la main</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(info.custom_metrics).map(([key, metrics]) => (
                  <tr key={key} className="border-t">
                    <td className="pr-2 py-1">{customDisplayName(key)}</td>
                    <td className="pr-2">{formatPercent(metrics.tracked_ratio)}</td>
                    <td className="pr-2">{metrics.path_length.toFixed(2).replace(".", ",")} h</td>
                    <td>{formatSeconds(metrics.hand_contact_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-600">
            Déplacement en hauteurs d&apos;image, mesuré dans l&apos;image : fiable avec une caméra fixe seulement.
          </p>
        </div>
      )}

      {hasExtraKeypoints(info) && (
        <a href={`${API_URL}/analyses/${encodeURIComponent(analysisId)}/keypoints`} className="text-blue-600 underline">
          Télécharger les points (JSON)
        </a>
      )}
    </section>
  );
}
