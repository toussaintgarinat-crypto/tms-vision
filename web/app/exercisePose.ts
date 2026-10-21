import * as THREE from "three";
import { BONE_ORDER, BoneKey } from "./pose3dSkeleton";

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
function rotationFor(bone: AngleBoneKey, angles: BoneAngles | undefined): THREE.Quaternion {
  const isUp = UP_BONES.has(bone);
  const flexion = THREE.MathUtils.degToRad(angles?.flexion ?? 0);
  const lateral = THREE.MathUtils.degToRad(angles?.lateral ?? 0);

  const aroundZ = new THREE.Quaternion().setFromAxisAngle(
    AXIS_Z,
    RIGHT_BONES.has(bone) ? -lateral : lateral,
  );
  const aroundX = new THREE.Quaternion().setFromAxisAngle(AXIS_X, isUp ? flexion : -flexion);
  // Appliqué à un vecteur : d'abord autour de z, puis autour de x.
  return aroundX.multiply(aroundZ);
}

function neutralDirection(bone: AngleBoneKey): THREE.Vector3 {
  return new THREE.Vector3(0, UP_BONES.has(bone) ? 1 : -1, 0);
}

export function boneDirections(angles: PoseAngles): Record<AngleBoneKey, THREE.Vector3> {
  const directions = {} as Record<AngleBoneKey, THREE.Vector3>;
  for (const bone of ANGLE_BONES) {
    directions[bone] = neutralDirection(bone).applyQuaternion(rotationFor(bone, angles[bone]));
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

export type RestPose = Record<BoneKey, THREE.Quaternion>;

// Orientations MONDE de repos de tous les os, à capturer une fois, squelette intact.
export function captureRestPose(bones: Record<BoneKey, THREE.Bone>): RestPose {
  bones.root.updateWorldMatrix(true, true);
  const rest = {} as RestPose;
  for (const key of BONE_ORDER) {
    rest[key] = bones[key].getWorldQuaternion(new THREE.Quaternion());
  }
  return rest;
}

// Pose le squelette : l'orientation monde de chaque os est sa rotation de repos
// composée avec la rotation de la pose (monde), donc la pose neutre redonne exactement
// le repos, sans roulis ni miroir. Les positions viennent de la hiérarchie du squelette.
//
// On n'utilise PAS `applyFrameToSkeleton` (avatar piloté par la vidéo) : pour un tronc
// vertical, `swingQuaternion` construit un repère tourné de 180° autour de l'axe
// vertical, que les os enfants héritent ; vérifié sur le vrai muscle-rig.glb, le bras
// gauche (+x au repos) se retrouve alors à -x et inversement. Inoffensif pour des bras
// qui pendent, il ferait bouger le mauvais bras ici.
export function applyPoseToSkeleton(
  bones: Record<BoneKey, THREE.Bone>,
  rest: RestPose,
  angles: PoseAngles,
): void {
  const worldQuaternion: Partial<Record<BoneKey, THREE.Quaternion>> = {};

  for (const key of BONE_ORDER) {
    const bone = bones[key];
    const desired =
      key === "root"
        ? rest.root.clone()
        : rotationFor(key as AngleBoneKey, angles[key as AngleBoneKey]).multiply(rest[key]);
    worldQuaternion[key] = desired;

    const parentWorld =
      (bone.parent && worldQuaternion[bone.parent.name as BoneKey]) ||
      (bone.parent ? bone.parent.getWorldQuaternion(new THREE.Quaternion()) : new THREE.Quaternion());
    bone.quaternion.copy(parentWorld.clone().invert().multiply(desired));
  }
}
