"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "../../auth/AuthProvider";
import { ExercisePlayer } from "../../bibliotheque/ExercisePlayer";
import { Exercise, POSITIONS, REGIONS, Region } from "../../exercisePose";
import { useI18n } from "../../i18n/I18nProvider";
import { ValidationBadge, ValidationLabel } from "../../ValidationBadge";
import { ValidationPanel } from "../../ValidationPanel";
import { saveBlob } from "../exchange";
import {
  ANGLE_KEYS, EDITABLE_BONES, MAX_ANGLE, Sheet, addKeyframe, addPose, bonesUsed, canRemovePose, emptySheet,
  poseNameError, previewExercise, removeKeyframe, removePose, setAngle, sheetFrom, sheetProblems,
  singlePosePreview, skeletonWarnings, toPayload, updateKeyframe,
} from "../sheetEditor";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const VIEWS = ["front", "side", "three_quarter"] as const;

type Loaded = Exercise & {
  benefit?: string;
  validation: ValidationLabel & { archived: boolean; copied_from: { id: string; title: string } | null };
};
type Access = { can_edit: boolean; can_copy: boolean };

// Éditeur de fiche : formulaire, éditeur d'animation manuel (poses par curseurs d'angles, poses clés
// datées, aperçu en direct) et validation. Une fiche d'origine ou d'un confrère se lit, puis se copie ;
// seule la fiche dont on est propriétaire se modifie, et chaque enregistrement crée une version à
// revalider.
export default function SheetEditorPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const creating = id === "nouvelle";
  const router = useRouter();
  const { t } = useI18n();
  const { user } = useAuth();
  const isOsteopath = user?.roles.includes("osteopathe") ?? false;

  const [sheet, setSheet] = useState<Sheet | null>(creating ? emptySheet() : null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [access, setAccess] = useState<Access>({ can_edit: creating, can_copy: false });
  const [poseName, setPoseName] = useState("tenue");
  const [bone, setBone] = useState<(typeof EDITABLE_BONES)[number]>("neck");
  const [newPose, setNewPose] = useState("");
  const [previewMode, setPreviewMode] = useState<"animation" | "pose">("animation");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [validating, setValidating] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    if (creating) return;
    try {
      const [exerciseResponse, stateResponse] = await Promise.all([
        fetch(`${API_URL}/exercises/${encodeURIComponent(id)}`),
        fetch(`${API_URL}/exercises/${encodeURIComponent(id)}/validation`),
      ]);
      if (!exerciseResponse.ok || !stateResponse.ok) throw new Error("load");
      const exercise = (await exerciseResponse.json()) as Loaded;
      const state = (await stateResponse.json()) as Access;
      setLoaded(exercise);
      setAccess(state);
      setSheet(sheetFrom(exercise));
      setPoseName((previous) => (previous in exercise.poses ? previous : Object.keys(exercise.poses)[0]));
    } catch {
      setFailed(true);
    }
  }, [id, creating]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const problems = useMemo(() => (sheet ? sheetProblems(sheet) : []), [sheet]);
  const warnings = useMemo(() => (sheet ? skeletonWarnings(sheet) : []), [sheet]);
  const preview = useMemo(() => {
    if (!sheet) return null;
    return previewMode === "pose" && poseName in sheet.poses ? singlePosePreview(sheet, poseName) : previewExercise(sheet);
  }, [sheet, previewMode, poseName]);

  if (!user) return null;
  if (!isOsteopath) return <main className="mx-auto w-full max-w-3xl flex-1 p-6 text-sm">{t("queue.forbidden")}</main>;
  if (failed) return <main className="p-6 text-sm text-red-700">{t("sheets.loadFailed")}</main>;
  if (!sheet || !preview) return <main className="p-6 text-sm text-gray-600">{t("live.loading")}</main>;

  const editable = access.can_edit && !(loaded?.validation.archived ?? false);
  const update = (patch: Partial<Sheet>) => setSheet({ ...sheet, ...patch });
  const poseNames = Object.keys(sheet.poses);
  const currentAngles = sheet.poses[poseName]?.[bone] ?? {};

  async function save() {
    if (!sheet) return;
    setSaving(true);
    setMessage(null);
    try {
      const response = await fetch(creating ? `${API_URL}/exercises` : `${API_URL}/exercises/${encodeURIComponent(id)}`, {
        method: creating ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(toPayload(sheet)),
      });
      const body = (await response.json().catch(() => null)) as ({ id?: string; detail?: string } | null);
      if (!response.ok) {
        setMessage({ kind: "error", text: typeof body?.detail === "string" ? body.detail : t("sheets.saveFailed") });
        return;
      }
      setMessage({ kind: "ok", text: t("sheets.saved") });
      if (creating && body?.id) router.replace(`/fiches/${encodeURIComponent(body.id)}`);
      else await load();
    } catch {
      setMessage({ kind: "error", text: t("sheets.saveFailed") });
    } finally {
      setSaving(false);
    }
  }

  async function post(path: string) {
    const response = await fetch(`${API_URL}/exercises/${encodeURIComponent(id)}/${path}`, { method: "POST" });
    if (!response.ok) {
      setMessage({ kind: "error", text: t("sheets.saveFailed") });
      return null;
    }
    return (await response.json()) as { id: string };
  }

  const field = "rounded border p-1 text-sm";
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{creating ? t("sheets.newTitle") : sheet.title || t("sheets.untitled")}</h1>
        <Link href="/fiches" className="text-sm text-blue-700 underline">{t("sheets.back")}</Link>
      </div>

      {loaded && (
        <div className="flex flex-col gap-1 text-xs">
          <ValidationBadge label={loaded.validation} />
          {loaded.validation.copied_from && (
            <span className="text-gray-600">{t("sheets.copiedFrom", { title: loaded.validation.copied_from.title })}</span>
          )}
          {!access.can_edit && <span className="text-amber-800">{t("sheets.readOnly")}</span>}
          {loaded.validation.archived && <span className="text-amber-800">{t("sheets.archivedNote")}</span>}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="flex flex-col gap-5">
          <fieldset disabled={!editable} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              {t("sheets.field.title")}
              <input value={sheet.title} onChange={(e) => update({ title: e.target.value })} className={field} />
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="flex flex-col gap-1 text-sm">
                {t("sheets.field.zone")}
                <select value={sheet.zone} onChange={(e) => update({ zone: e.target.value as Region })} className={field}>
                  {REGIONS.map((region) => <option key={region} value={region}>{t(`region.${region}`)}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                {t("sheets.field.position")}
                <select value={sheet.position} onChange={(e) => update({ position: e.target.value as Sheet["position"] })} className={field}>
                  {POSITIONS.map((position) => <option key={position} value={position}>{t(`sheets.position.${position}`)}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                {t("sheets.field.view")}
                <select value={sheet.view} onChange={(e) => update({ view: e.target.value as Sheet["view"] })} className={field}>
                  {VIEWS.map((view) => <option key={view} value={view}>{t(`sheets.view.${view}`)}</option>)}
                </select>
              </label>
            </div>
            <label className="flex flex-col gap-1 text-sm">
              {t("sheets.field.description")}
              <textarea rows={3} value={sheet.description} onChange={(e) => update({ description: e.target.value })} className={field} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              {t("sheets.field.benefit")}
              <textarea rows={2} value={sheet.benefit} onChange={(e) => update({ benefit: e.target.value })} className={field} />
              <span className="text-xs text-gray-600">{t("sheets.field.benefitHelp")}</span>
            </label>
            <label className="flex max-w-xs flex-col gap-1 text-sm">
              {t("sheets.field.duration")}
              <input type="number" value={sheet.duration_seconds} onChange={(e) => update({ duration_seconds: Number(e.target.value) })} className={field} />
            </label>
            <div className="text-sm">
              <p className="mb-1">{t("sheets.field.segments")}</p>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {REGIONS.map((region) => (
                  <label key={region} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={sheet.target_segments.includes(region)}
                      onChange={(e) =>
                        update({
                          target_segments: e.target.checked
                            ? [...sheet.target_segments, region]
                            : sheet.target_segments.filter((s) => s !== region),
                        })
                      }
                    />
                    {t(`region.${region}`)}
                  </label>
                ))}
              </div>
            </div>
          </fieldset>

          <fieldset disabled={!editable} className="flex flex-col gap-3 rounded border p-3">
            <legend className="px-1 text-sm font-semibold">{t("sheets.poses")}</legend>
            <p className="text-xs text-gray-600">{t("sheets.posesHelp")}</p>
            <div className="flex flex-wrap items-end gap-2 text-sm">
              <label className="flex flex-col gap-1">
                {t("sheets.pose")}
                <select value={poseName} onChange={(e) => setPoseName(e.target.value)} className={field}>
                  {poseNames.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
              <button type="button" disabled={!canRemovePose(sheet, poseName)} onClick={() => { setSheet(removePose(sheet, poseName)); setPoseName(poseNames.find((n) => n !== poseName) ?? poseName); }} className="rounded border border-red-600 px-2 py-1 text-red-700 disabled:opacity-40" title={t("sheets.poseRemoveHelp")}>
                {t("sheets.poseRemove")}
              </button>
              <label className="flex flex-col gap-1">
                {t("sheets.poseNew")}
                <input value={newPose} onChange={(e) => setNewPose(e.target.value.toLowerCase())} placeholder="tilt_right" className={field} />
              </label>
              <button
                type="button"
                disabled={poseNameError(newPose, poseNames) !== null}
                onClick={() => { setSheet(addPose(sheet, newPose, poseName)); setPoseName(newPose); setNewPose(""); }}
                className="rounded border border-blue-600 px-2 py-1 text-blue-800 disabled:opacity-40"
              >
                {t("sheets.poseAdd")}
              </button>
            </div>
            {newPose && poseNameError(newPose, poseNames) && (
              <p className="text-xs text-red-700">{t(`sheets.poseName.${poseNameError(newPose, poseNames)}`)}</p>
            )}
            <label className="flex flex-col gap-1 text-sm">
              {t("sheets.bone")}
              <select value={bone} onChange={(e) => setBone(e.target.value as typeof bone)} className={`${field} max-w-xs`}>
                {EDITABLE_BONES.map((name) => <option key={name} value={name}>{t(`sheets.bone.${name}`)}</option>)}
              </select>
            </label>
            {ANGLE_KEYS.map((key) => (
              <label key={key} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-2 text-sm">
                {t(`sheets.angle.${key}`)}
                <input
                  type="range" min={-MAX_ANGLE} max={MAX_ANGLE} value={currentAngles[key] ?? 0}
                  onChange={(e) => update({ poses: setAngle(sheet.poses, poseName, bone, key, Number(e.target.value)) })}
                />
                <input
                  type="number" min={-MAX_ANGLE} max={MAX_ANGLE} value={currentAngles[key] ?? 0}
                  onChange={(e) => update({ poses: setAngle(sheet.poses, poseName, bone, key, Number(e.target.value)) })}
                  className={field}
                />
              </label>
            ))}
            <p className="text-xs text-gray-600">
              {t("sheets.bonesUsed")} {bonesUsed(sheet.poses, poseName).map((name) => t(`sheets.bone.${name}`)).join(", ") || t("sheets.noBone")}
            </p>
          </fieldset>

          <fieldset disabled={!editable} className="flex flex-col gap-2 rounded border p-3">
            <legend className="px-1 text-sm font-semibold">{t("sheets.keyframes")}</legend>
            <p className="text-xs text-gray-600">{t("sheets.keyframesHelp")}</p>
            {sheet.keyframes.map((keyframe, index) => (
              <div key={index} className="flex flex-wrap items-center gap-2 text-sm">
                <input type="number" min={0} step={0.5} value={keyframe.t} onChange={(e) => setSheet(updateKeyframe(sheet, index, { t: Number(e.target.value) }))} className={`${field} w-24`} aria-label={t("sheets.keyframeTime")} />
                <span>s</span>
                <select value={keyframe.pose} onChange={(e) => setSheet(updateKeyframe(sheet, index, { pose: e.target.value }))} className={field} aria-label={t("sheets.pose")}>
                  {poseNames.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
                <button type="button" onClick={() => setSheet(removeKeyframe(sheet, index))} className="rounded border border-red-600 px-2 py-0.5 text-xs text-red-700">{t("program.remove")}</button>
              </div>
            ))}
            <button type="button" onClick={() => setSheet(addKeyframe(sheet, poseName))} className="self-start rounded border border-blue-600 px-2 py-1 text-sm text-blue-800">{t("sheets.keyframeAdd")}</button>
          </fieldset>

          <fieldset disabled={!editable} className="flex flex-col gap-2 rounded border p-3">
            <legend className="px-1 text-sm font-semibold">{t("sheets.instructions")}</legend>
            <p className="text-xs text-gray-600">{t("sheets.instructionsHelp")}</p>
            {sheet.instructions.map((instruction, index) => (
              <div key={index} className="flex flex-wrap items-start gap-2 text-sm">
                <input type="number" min={0} step={0.5} value={instruction.t} onChange={(e) => update({ instructions: sheet.instructions.map((item, i) => (i === index ? { ...item, t: Number(e.target.value) } : item)) })} className={`${field} w-24`} aria-label={t("sheets.keyframeTime")} />
                <input value={instruction.text} onChange={(e) => update({ instructions: sheet.instructions.map((item, i) => (i === index ? { ...item, text: e.target.value } : item)) })} className={`${field} min-w-0 flex-1`} aria-label={t("sheets.instructionText")} />
                <button type="button" onClick={() => update({ instructions: sheet.instructions.filter((_, i) => i !== index) })} className="rounded border border-red-600 px-2 py-0.5 text-xs text-red-700">{t("program.remove")}</button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => update({ instructions: [...sheet.instructions, { t: Math.min(sheet.duration_seconds, (sheet.instructions.at(-1)?.t ?? 0) + 5), text: "" }] })}
              className="self-start rounded border border-blue-600 px-2 py-1 text-sm text-blue-800"
            >
              {t("sheets.instructionAdd")}
            </button>
          </fieldset>
        </div>

        <aside className="flex flex-col gap-3 lg:sticky lg:top-4 lg:self-start">
          <div className="flex gap-1 text-xs" role="group" aria-label={t("sheets.preview")}>
            {(["animation", "pose"] as const).map((mode) => (
              <button key={mode} type="button" aria-pressed={previewMode === mode} onClick={() => setPreviewMode(mode)}
                className={`rounded border px-2 py-1 ${previewMode === mode ? "border-blue-700 bg-blue-700 text-white" : "border-blue-600 text-blue-800"}`}>
                {t(`sheets.preview.${mode}`)}
              </button>
            ))}
          </div>
          <ExercisePlayer key={`${previewMode}-${poseName}-${JSON.stringify(preview.poses).length}-${preview.keyframes.length}`} exercise={preview} />

          {problems.length > 0 && (
            <ul className="list-disc rounded border border-amber-300 bg-amber-50 p-3 pl-6 text-xs text-amber-900" aria-label={t("sheets.problems")}>
              {problems.map((problem) => <li key={problem.code}>{t(`sheets.problem.${problem.code}`, problem.vars)}</li>)}
            </ul>
          )}
          {warnings.length > 0 && (
            <ul className="list-disc rounded border border-sky-300 bg-sky-50 p-3 pl-6 text-xs text-sky-900" aria-label={t("sheets.limits")}>
              {warnings.map((warning, index) => (
                <li key={index}>
                  {warning.code === "grouped"
                    ? t("sheets.warn.grouped", { bone: t(`sheets.bone.${warning.bone}`), pose: warning.pose })
                    : t("sheets.warn.extreme", { bone: t(`sheets.bone.${warning.bone}`), pose: warning.pose, angle: t(`sheets.angle.${warning.angle}`), value: warning.value ?? 0 })}
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-gray-600">{t("sheets.limitsNote")}</p>

          {message && <p role="status" className={`text-sm ${message.kind === "ok" ? "text-emerald-800" : "text-red-700"}`}>{message.text}</p>}
          {editable && (
            <button type="button" disabled={saving || problems.length > 0} onClick={() => void save()} className="rounded bg-blue-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {creating ? t("sheets.create") : t("sheets.save")}
            </button>
          )}
          {editable && !creating && <p className="text-xs text-gray-600">{t("sheets.saveHelp")}</p>}
          {!creating && access.can_copy && (
            <button type="button" onClick={async () => { const created = await post("copy"); if (created) router.push(`/fiches/${encodeURIComponent(created.id)}`); }} className="rounded border border-blue-600 px-3 py-2 text-sm text-blue-800">
              {t("sheets.copy")}
            </button>
          )}
          {!creating && access.can_edit && (
            <button type="button" onClick={async () => { if (await post(loaded?.validation.archived ? "unarchive" : "archive")) await load(); }} className="rounded border px-3 py-2 text-sm">
              {loaded?.validation.archived ? t("sheets.unarchive") : t("sheets.archive")}
            </button>
          )}
          {!creating && (
            <button
              type="button"
              onClick={async () => {
                const response = await fetch(`${API_URL}/sheets/export?ids=${encodeURIComponent(id)}`);
                if (response.ok) saveBlob(await response.blob(), `fiche-${id}.json`);
                else setMessage({ kind: "error", text: t("sheets.exchange.exportFailed") });
              }}
              className="rounded border px-3 py-2 text-sm"
            >
              {t("sheets.exchange.exportOne")}
            </button>
          )}
          {!creating && !loaded?.validation.archived && (
            <button type="button" onClick={() => setValidating((value) => !value)} className="rounded border border-emerald-700 px-3 py-2 text-sm text-emerald-800">
              {t("validation.validateButton")}
            </button>
          )}
        </aside>
      </div>
      {validating && !creating && <ValidationPanel exerciseId={id} onClose={() => setValidating(false)} onChanged={() => void load()} />}
    </main>
  );
}
