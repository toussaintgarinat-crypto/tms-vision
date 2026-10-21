import * as THREE from "three";
import { BONE_LENGTH, BoneKey, Pose3DLandmarks } from "./pose3dSkeleton";

// Pose d'un exercice d'étirement en angles par os, convertie en pose du squelette
// articulé de l'avatar (voir exercises/README.md et
// docs/superpowers/plans/2026-10-21-generation-modules-etirement-plan.md).
//
// Repère (Three.js, y vers le haut), établi par mesure sur le vrai
// muscle-rig.glb (verrouillé par exercisePose.test.ts) : le côté GAUCHE du
// modèle est +x, son AVANT est +z (face à la caméra de l'avatar).

export type AngleBoneKey = Exclude<BoneKey, "root">;
export type BoneAngles = { flexion?: number; lateral?: number };
export type PoseAngles = Partial<Record<AngleBoneKey, BoneAngles>>;

export type Zone = "neck" | "trunk" | "upper_arm" | "lower_arm";

export type Exercise = {
  id: string;
  zone: Zone;
  title: string;
  description: string;
  status: "draft" | "validated";
  source: "human" | "ai";
  validated_by: string | null;
  validated_on: string | null;
  view: "front" | "side" | "three_quarter";
  target_segments: Zone[];
  poses: Record<string, PoseAngles>;
  keyframes: { t: number; pose: string }[];
  instructions: { t: number; text: string }[];
  duration_seconds: number;
};

// Os dont la direction neutre est vers le haut ; les autres pendent vers le bas.
const UP_BONES: ReadonlySet<AngleBoneKey> = new Set<AngleBoneKey>(["spine", "neck"]);
// Os du côté droit du sujet : leur `lateral` est miroité (écartement = vers -x).
const RIGHT_BONES: ReadonlySet<AngleBoneKey> = new Set<AngleBoneKey>([
  "R_upper_arm",
  "R_forearm",
  "R_thigh",
]);

const AXIS_X = new THREE.Vector3(1, 0, 0);
const AXIS_Z = new THREE.Vector3(0, 0, 1);

const ANGLE_BONES: readonly AngleBoneKey[] = [
  "spine",
  "neck",
  "L_upper_arm",
  "L_forearm",
  "R_upper_arm",
  "R_forearm",
  "L_thigh",
  "R_thigh",
];

// Conventions (angles en degrés, absolus par rapport à la posture neutre) :
// - `flexion` positif : l'extrémité de l'os va vers l'avant du corps (+z).
// - `lateral` positif : vers la droite du sujet (-x) pour `spine` et `neck` ;
//   écartement du corps (abduction) pour les os pairés, miroité à droite.
// Composition : d'abord `lateral` autour de l'axe avant-arrière (z), puis
// `flexion` autour de l'axe gauche-droite (x). Un bras avec flexion 90 est donc
// à l'horizontale devant soi, et `lateral` l'en écarte dans le plan horizontal.
function directionFor(bone: AngleBoneKey, angles: BoneAngles | undefined): THREE.Vector3 {
  const isUp = UP_BONES.has(bone);
  const flexion = THREE.MathUtils.degToRad(angles?.flexion ?? 0);
  const lateral = THREE.MathUtils.degToRad(angles?.lateral ?? 0);

  return new THREE.Vector3(0, isUp ? 1 : -1, 0)
    .applyAxisAngle(AXIS_Z, RIGHT_BONES.has(bone) ? -lateral : lateral)
    .applyAxisAngle(AXIS_X, isUp ? flexion : -flexion)
    .normalize();
}

export function boneDirections(angles: PoseAngles): Record<AngleBoneKey, THREE.Vector3> {
  const directions = {} as Record<AngleBoneKey, THREE.Vector3>;
  for (const bone of ANGLE_BONES) {
    directions[bone] = directionFor(bone, angles[bone]);
  }
  return directions;
}

function smoothstep(u: number): number {
  return u * u * (3 - 2 * u);
}

// Pose à l'instant t : interpolation adoucie, dans l'espace des angles, entre
// les deux poses clés qui l'encadrent. Un os absent d'une des deux poses part
// ou arrive à l'angle neutre (0). Le temps est borné à [premier, dernier].
export function samplePose(exercise: Exercise, t: number): PoseAngles {
  const { keyframes, poses } = exercise;
  const clamped = Math.min(Math.max(t, keyframes[0].t), keyframes[keyframes.length - 1].t);

  let index = 0;
  while (index < keyframes.length - 2 && clamped > keyframes[index + 1].t) index++;
  const from = keyframes[index];
  const to = keyframes[index + 1];
  const eased = smoothstep((clamped - from.t) / (to.t - from.t));

  const poseFrom = poses[from.pose];
  const poseTo = poses[to.pose];
  const result: PoseAngles = {};
  for (const bone of ANGLE_BONES) {
    if (!(bone in poseFrom) && !(bone in poseTo)) continue;
    const a = poseFrom[bone] ?? {};
    const b = poseTo[bone] ?? {};
    result[bone] = {
      flexion: (a.flexion ?? 0) + ((b.flexion ?? 0) - (a.flexion ?? 0)) * eased,
      lateral: (a.lateral ?? 0) + ((b.lateral ?? 0) - (a.lateral ?? 0)) * eased,
    };
  }
  return result;
}

// Consigne en cours à l'instant t : la dernière dont l'instant est atteint.
export function activeInstruction(
  exercise: Exercise,
  t: number,
): { text: string; index: number } | null {
  let found: { text: string; index: number } | null = null;
  exercise.instructions.forEach((instruction, index) => {
    if (instruction.t <= t) found = { text: instruction.text, index };
  });
  return found;
}

const SHOULDER_HALF_WIDTH = 0.2;
const HIP_HALF_WIDTH = 0.1;

// Landmarks synthétiques (repère MediaPipe : y vers le bas) qui, passés à
// `applyFrameToSkeleton`, donnent au squelette les directions de `boneDirections`.
// C'est le MÊME chemin que l'avatar piloté par la vidéo : mêmes conventions de
// calcul des rotations. Seules les directions comptent (les positions des os
// viennent de la hiérarchie) ; les largeurs d'épaules et de hanches sont de simples
// décalages latéraux.
export function anglesToLandmarks(angles: PoseAngles): Pose3DLandmarks {
  const d = boneDirections(angles);
  const at = (base: THREE.Vector3, direction: THREE.Vector3, length: number) =>
    base.clone().addScaledVector(direction, length);
  const asLandmark = (v: THREE.Vector3): [number, number, number] => [v.x, -v.y, v.z];

  const hipLeft = new THREE.Vector3(HIP_HALF_WIDTH, 0, 0);
  const hipRight = new THREE.Vector3(-HIP_HALF_WIDTH, 0, 0);
  const shoulderMid = at(new THREE.Vector3(0, 0, 0), d.spine, BONE_LENGTH.spine);
  const shoulderLeft = shoulderMid.clone().add(new THREE.Vector3(SHOULDER_HALF_WIDTH, 0, 0));
  const shoulderRight = shoulderMid.clone().add(new THREE.Vector3(-SHOULDER_HALF_WIDTH, 0, 0));
  const nose = at(shoulderMid, d.neck, BONE_LENGTH.neck);
  const elbowLeft = at(shoulderLeft, d.L_upper_arm, BONE_LENGTH.L_upper_arm);
  const elbowRight = at(shoulderRight, d.R_upper_arm, BONE_LENGTH.R_upper_arm);
  const wristLeft = at(elbowLeft, d.L_forearm, BONE_LENGTH.L_forearm);
  const wristRight = at(elbowRight, d.R_forearm, BONE_LENGTH.R_forearm);
  const kneeLeft = at(hipLeft, d.L_thigh, BONE_LENGTH.L_thigh);
  const kneeRight = at(hipRight, d.R_thigh, BONE_LENGTH.R_thigh);

  return {
    LEFT_HIP: asLandmark(hipLeft),
    RIGHT_HIP: asLandmark(hipRight),
    LEFT_SHOULDER: asLandmark(shoulderLeft),
    RIGHT_SHOULDER: asLandmark(shoulderRight),
    NOSE: asLandmark(nose),
    LEFT_ELBOW: asLandmark(elbowLeft),
    RIGHT_ELBOW: asLandmark(elbowRight),
    LEFT_WRIST: asLandmark(wristLeft),
    RIGHT_WRIST: asLandmark(wristRight),
    LEFT_KNEE: asLandmark(kneeLeft),
    RIGHT_KNEE: asLandmark(kneeRight),
  };
}
