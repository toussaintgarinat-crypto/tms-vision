"use client";

import { useI18n } from "./i18n/I18nProvider";
import {
  CustomPointMetrics,
  DetectionQuality,
  HandSideMetrics,
  confidenceLabel,
  customDisplayName,
  formatDecimal,
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
  const { t, tag } = useI18n();
  const quality = info.detection_quality ?? null;
  const groups = groupsForOptions(info.pose_options);
  const confidence = quality?.avg_confidence ?? null;

  return (
    <section className="flex flex-col gap-3 rounded border p-3 text-sm" aria-label={t("pose.title")}>
      <h3 className="font-semibold">{t("pose.title")}</h3>
      <dl className="grid grid-cols-2 gap-2">
        <dt>{t("pi.model")}</dt>
        <dd>{poseModelLabel(info.pose_model)}</dd>
        <dt>{t("pi.pointsPerPerson")}</dt>
        <dd>{info.keypoint_count ?? 33}</dd>
        {quality && (
          <>
            <dt>{t("pi.pointsDetected")}</dt>
            <dd>{quality.frames_with_points > 0 ? quality.avg_keypoints_per_frame : "—"}</dd>
            <dt>{t("pi.confidence")}</dt>
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
                    aria-label={t("pi.confidenceMeter")}
                  >
                    <span className="block h-full bg-green-600" style={{ width: `${Math.round(confidence * 100)}%` }} />
                  </span>
                  {formatPercent(confidence, t)} ({confidenceLabel(confidence, t)})
                </span>
              )}
            </dd>
          </>
        )}
      </dl>

      <div className="flex flex-wrap gap-x-4 gap-y-1" aria-label={t("pi.legend")}>
        {GROUP_LEGEND.filter((entry) => groups.includes(entry.group)).map((entry) => (
          <span key={entry.group} className="flex items-center gap-1 text-xs">
            <span
              className="inline-block h-3 w-3 rounded-full border border-gray-400"
              style={{ backgroundColor: entry.color }}
            />
            {t(entry.labelKey)}
          </span>
        ))}
      </div>

      {!hasAvatar3D(info) && (
        <p className="text-xs text-gray-600">
          {t("pi.no3d")}
        </p>
      )}

      {info.hands_metrics && (
        <div className="flex flex-col gap-1">
          <h4 className="font-medium">{t("pi.hands")}</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-gray-600">
                  <th className="pr-2 font-normal">{t("pi.col.side")}</th>
                  <th className="pr-2 font-normal">{t("pi.col.detected")}</th>
                  <th className="pr-2 font-normal">{t("pi.col.curl")}</th>
                  <th className="pr-2 font-normal">{t("pi.col.grasps")}</th>
                  <th className="pr-2 font-normal">{t("pi.col.duration")}</th>
                  <th className="font-normal">{t("pi.col.rate")}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(info.hands_metrics).map(([side, metrics]) => (
                  <tr key={side} className="border-t">
                    <td className="pr-2 py-1">{handSideLabel(side, t)}</td>
                    <td className="pr-2">{formatPercent(metrics.detection_ratio, t)}</td>
                    <td className="pr-2">
                      {formatDegrees(metrics.finger_curl_mean_deg)} / {formatDegrees(metrics.finger_curl_max_deg)}
                    </td>
                    <td className="pr-2">{metrics.grasp_count}</td>
                    <td className="pr-2">{formatSeconds(metrics.grasp_seconds, tag)}</td>
                    <td>
                      {formatRate(metrics.grasps_per_minute, tag)}
                      {metrics.repetitive && (
                        <span className="ml-1 rounded bg-amber-100 px-1 text-amber-900">{t("pi.repetitive")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-600">
            {t("pi.handsNote")}
          </p>
        </div>
      )}

      {info.custom_metrics && Object.keys(info.custom_metrics).length > 0 && (
        <div className="flex flex-col gap-1">
          <h4 className="font-medium">{t("pi.custom")}</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-gray-600">
                  <th className="pr-2 font-normal">{t("pi.col.point")}</th>
                  <th className="pr-2 font-normal">{t("pi.col.tracked")}</th>
                  <th className="pr-2 font-normal">{t("pi.col.travel")}</th>
                  <th className="font-normal">{t("pi.col.handContact")}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(info.custom_metrics).map(([key, metrics]) => (
                  <tr key={key} className="border-t">
                    <td className="pr-2 py-1">{customDisplayName(key)}</td>
                    <td className="pr-2">{formatPercent(metrics.tracked_ratio, t)}</td>
                    <td className="pr-2">{t("pi.travelUnit", { value: formatDecimal(metrics.path_length, tag, 2) })}</td>
                    <td>{formatSeconds(metrics.hand_contact_seconds, tag)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-600">
            {t("pi.customNote")}
          </p>
        </div>
      )}

      {hasExtraKeypoints(info) && (
        <a href={`${API_URL}/analyses/${encodeURIComponent(analysisId)}/keypoints`} className="text-blue-600 underline">
          {t("pi.downloadKeypoints")}
        </a>
      )}
    </section>
  );
}
