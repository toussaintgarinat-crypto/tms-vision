import { BONE_ORDER } from "../pose3dSkeleton";
import type { AngleBoneKey, BoneAngles, Exercise, PoseAngles, Position, Region } from "../exercisePose";

// Logique pure de l'éditeur de fiches (phase 4) : modifications de poses, de poses clés et de
// consignes, contrôles identiques à ceux du serveur (exercises.py) pour signaler les erreurs avant
// l'enregistrement, et avertissements sur les limites du squelette. Rien ici ne touche au réseau.

export const MIN_DURATION = 10;
export const MAX_DURATION = 180;
export const MAX_ANGLE = 180;
export const ANGLE_KEYS = ["flexion", "lateral", "twist"] as const;
export type AngleKey = (typeof ANGLE_KEYS)[number];
export const EDITABLE_BONES = BONE_ORDER.filter((bone): bone is AngleBoneKey => bone !== "root");

// Contenu d'une fiche tel que l'éditeur le manipule (sans id, statut ni validation : posés par le
// serveur).
export type Sheet = {
  title: string;
  zone: Region;
  description: string;
  benefit: string;
  position: Position;
  view: Exercise["view"];
  target_segments: Region[];
  poses: Record<string, PoseAngles>;
  keyframes: { t: number; pose: string }[];
  instructions: { t: number; text: string }[];
  duration_seconds: number;
};

export function emptySheet(): Sheet {
  return {
    title: "",
    zone: "neck",
    description: "",
    benefit: "",
    position: "standing",
    view: "front",
    target_segments: ["neck"],
    poses: { neutral: {}, tenue: {} },
    keyframes: [
      { t: 0, pose: "neutral" },
      { t: 5, pose: "tenue" },
      { t: 15, pose: "tenue" },
      { t: 20, pose: "neutral" },
    ],
    instructions: [{ t: 0, text: "" }],
    duration_seconds: 20,
  };
}

// Fiche existante -> contenu éditable (copie profonde, champs absents remplacés par des défauts).
export function sheetFrom(exercise: Exercise & { benefit?: string }): Sheet {
  return {
    title: exercise.title,
    zone: exercise.zone,
    description: exercise.description,
    benefit: exercise.benefit ?? "",
    position: exercise.position ?? "standing",
    view: exercise.view,
    target_segments: [...exercise.target_segments],
    poses: structuredClone(exercise.poses),
    keyframes: exercise.keyframes.map((keyframe) => ({ ...keyframe })),
    instructions: exercise.instructions.map((instruction) => ({ ...instruction })),
    duration_seconds: exercise.duration_seconds,
  };
}

// Corps envoyé au serveur : `benefit` vide = champ absent.
export function toPayload(sheet: Sheet): Record<string, unknown> {
  const { benefit, ...rest } = sheet;
  return benefit.trim() ? { ...rest, benefit: benefit.trim() } : rest;
}

// Exercice jouable par le lecteur 3D à partir d'une fiche en cours d'édition.
export function previewExercise(sheet: Sheet): Exercise {
  return {
    id: "apercu",
    ...sheet,
    status: "draft",
    source: "human",
    validated_by: null,
    validated_on: null,
  };
}

// Aperçu d'UNE pose, tenue pendant toute la durée minimale : sert à régler les angles.
export function singlePosePreview(sheet: Sheet, poseName: string): Exercise {
  return {
    ...previewExercise(sheet),
    poses: { [poseName]: sheet.poses[poseName] ?? {} },
    keyframes: [
      { t: 0, pose: poseName },
      { t: MIN_DURATION, pose: poseName },
    ],
    instructions: [{ t: 0, text: "" }],
    duration_seconds: MIN_DURATION,
  };
}

export function clampAngle(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(-MAX_ANGLE, Math.min(MAX_ANGLE, Math.round(value)));
}

// Fixe un angle ; un angle nul est retiré (l'os reste aligné sur son parent), et un os sans angle
// disparaît de la pose, comme dans les fichiers du catalogue.
export function setAngle(
  poses: Sheet["poses"], poseName: string, bone: AngleBoneKey, key: AngleKey, value: number,
): Sheet["poses"] {
  const pose = { ...(poses[poseName] ?? {}) };
  const angles: BoneAngles = { ...(pose[bone] ?? {}) };
  const clamped = clampAngle(value);
  if (clamped === 0) delete angles[key];
  else angles[key] = clamped;
  if (Object.keys(angles).length === 0) delete pose[bone];
  else pose[bone] = angles;
  return { ...poses, [poseName]: pose };
}

const POSE_NAME = /^[a-z0-9_]+$/;

export function poseNameError(name: string, existing: string[]): "empty" | "format" | "taken" | null {
  if (!name) return "empty";
  if (!POSE_NAME.test(name)) return "format";
  return existing.includes(name) ? "taken" : null;
}

export function addPose(sheet: Sheet, name: string, copyFrom?: string): Sheet {
  const base = copyFrom ? structuredClone(sheet.poses[copyFrom] ?? {}) : {};
  return { ...sheet, poses: { ...sheet.poses, [name]: base } };
}

// Une pose utilisée par une pose clé ne se supprime pas (le serveur refuserait la fiche).
export function canRemovePose(sheet: Sheet, name: string): boolean {
  return Object.keys(sheet.poses).length > 1 && !sheet.keyframes.some((keyframe) => keyframe.pose === name);
}

export function removePose(sheet: Sheet, name: string): Sheet {
  if (!canRemovePose(sheet, name)) return sheet;
  const poses = { ...sheet.poses };
  delete poses[name];
  return { ...sheet, poses };
}

// Ajoute une pose clé 5 s après la dernière (dans la durée si possible).
export function addKeyframe(sheet: Sheet, pose: string): Sheet {
  const last = sheet.keyframes[sheet.keyframes.length - 1];
  const t = Math.min(sheet.duration_seconds, (last?.t ?? 0) + 5);
  return { ...sheet, keyframes: [...sheet.keyframes, { t, pose }] };
}

export function updateKeyframe(sheet: Sheet, index: number, patch: Partial<{ t: number; pose: string }>): Sheet {
  return { ...sheet, keyframes: sheet.keyframes.map((keyframe, i) => (i === index ? { ...keyframe, ...patch } : keyframe)) };
}

export function removeKeyframe(sheet: Sheet, index: number): Sheet {
  return { ...sheet, keyframes: sheet.keyframes.filter((_, i) => i !== index) };
}

export type SheetProblem = { code: string; vars?: Record<string, string | number> };

// Mêmes contrôles que `exercises.validate_exercise`, pour avertir avant d'envoyer.
export function sheetProblems(sheet: Sheet): SheetProblem[] {
  const problems: SheetProblem[] = [];
  if (!sheet.title.trim()) problems.push({ code: "title" });
  if (!sheet.description.trim()) problems.push({ code: "description" });
  if (sheet.target_segments.length === 0) problems.push({ code: "segments" });
  if (!(sheet.duration_seconds >= MIN_DURATION && sheet.duration_seconds <= MAX_DURATION)) {
    problems.push({ code: "duration", vars: { min: MIN_DURATION, max: MAX_DURATION } });
  }
  const { keyframes, instructions, duration_seconds: duration } = sheet;
  if (keyframes.length < 2) problems.push({ code: "keyframesCount" });
  if (keyframes.length > 0 && keyframes[0].t !== 0) problems.push({ code: "keyframeStart" });
  if (keyframes.some((keyframe, i) => i > 0 && keyframe.t <= keyframes[i - 1].t)) problems.push({ code: "keyframeOrder" });
  if (keyframes.length > 0 && keyframes[keyframes.length - 1].t > duration) problems.push({ code: "keyframeEnd" });
  if (keyframes.some((keyframe) => !(keyframe.pose in sheet.poses))) problems.push({ code: "keyframePose" });
  if (instructions.length === 0 || instructions.some((instruction) => !instruction.text.trim())) {
    problems.push({ code: "instructionText" });
  }
  if (instructions.some((instruction, i) => i > 0 && instruction.t <= instructions[i - 1].t)) {
    problems.push({ code: "instructionOrder" });
  }
  if (instructions.some((instruction) => instruction.t < 0 || instruction.t > duration)) {
    problems.push({ code: "instructionRange" });
  }
  return problems;
}

// Limites du squelette : l'éditeur ne les interdit pas, il les signale. Le squelette n'a que 24 os :
// doigts, orteils et tronc sont regroupés, et aucune limite d'articulation n'est appliquée par le
// rendu (un angle impossible pour un corps humain se dessine quand même).
const SOFT_LIMIT = 150;
const GROUPED_BONES: AngleBoneKey[] = ["L_fingers", "R_fingers", "L_toes", "R_toes", "L_thumb", "R_thumb"];

export type SkeletonWarning = { code: "extreme" | "grouped"; pose: string; bone: AngleBoneKey; angle?: AngleKey; value?: number };

export function skeletonWarnings(sheet: Sheet): SkeletonWarning[] {
  const warnings: SkeletonWarning[] = [];
  for (const [pose, bones] of Object.entries(sheet.poses)) {
    for (const bone of Object.keys(bones) as AngleBoneKey[]) {
      if (GROUPED_BONES.includes(bone)) warnings.push({ code: "grouped", pose, bone });
      for (const angle of ANGLE_KEYS) {
        const value = bones[bone]?.[angle];
        if (value !== undefined && Math.abs(value) > SOFT_LIMIT) {
          warnings.push({ code: "extreme", pose, bone, angle, value });
        }
      }
    }
  }
  return warnings;
}

// Os utilisés dans au moins une pose, pour l'affichage.
export function bonesUsed(poses: Sheet["poses"], poseName: string): AngleBoneKey[] {
  return Object.keys(poses[poseName] ?? {}) as AngleBoneKey[];
}
