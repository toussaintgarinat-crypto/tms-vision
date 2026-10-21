import * as THREE from "three";
import { BONE_ORDER, BoneKey, PARENT_OF } from "./pose3dSkeleton";

// Pose d'un exercice d'étirement en angles par os, convertie en pose du squelette
// articulé de l'avatar (voir exercises/README.md et
// docs/superpowers/specs/2026-10-22-avatar-corps-complet-design.md).
//
// Repère (Three.js, y vers le haut), établi par mesure sur le vrai
// muscle-rig.glb (verrouillé par exercisePose.test.ts) : le côté GAUCHE du
// modèle est +x, son AVANT est +z (face à la caméra de l'avatar).

export type AngleBoneKey = Exclude<BoneKey, "root">;
export type BoneAngles = { flexion?: number; lateral?: number; twist?: number };
export type PoseAngles = Partial<Record<AngleBoneKey, BoneAngles>>;

// Régions colorables : les quatre zones RULA mesurées, puis les régions ajoutées avec le corps
// complet (aucune donnée mesurée pour celles-ci, voir muscleSegments.ts).
export const REGIONS = [
  "neck",
  "trunk",
  "upper_arm",
  "lower_arm",
  "head",
  "shoulder",
  "hand",
  "hip",
  "thigh",
  "lower_leg",
  "foot",
] as const;
export type Region = (typeof REGIONS)[number];
// Ancien nom, conservé pour les modules qui parlent de « zone ».
export type Zone = Region;

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
  target_segments: Region[];
  poses: Record<string, PoseAngles>;
  keyframes: { t: number; pose: string }[];
  instructions: { t: number; text: string }[];
  duration_seconds: number;
};

// Direction de repos de chaque os, qui fixe le sens de ses trois angles :
// - "up" : tronc, cou, tête (vers le haut) ;
// - "down" : membres qui pendent (bras, avant-bras, main, doigts, pouce, cuisse, jambe) ;
// - "outward" : clavicule (horizontale, vers l'extérieur) ;
// - "forward" : pied et orteils (horizontaux, vers l'avant).
type RestKind = "up" | "down" | "outward" | "forward";

const REST_KIND: Record<AngleBoneKey, RestKind> = {
  spine: "up",
  neck: "up",
  head: "up",
  L_clavicle: "outward",
  R_clavicle: "outward",
  L_upper_arm: "down",
  R_upper_arm: "down",
  L_forearm: "down",
  R_forearm: "down",
  L_hand: "down",
  R_hand: "down",
  L_fingers: "down",
  R_fingers: "down",
  L_thumb: "down",
  R_thumb: "down",
  L_thigh: "down",
  R_thigh: "down",
  L_shin: "down",
  R_shin: "down",
  L_foot: "forward",
  R_foot: "forward",
  L_toes: "forward",
  R_toes: "forward",
};

// Signe de chaque angle selon le type d'os. `mirrored` : le signe de `lateral` et de `twist` est
// inversé du côté droit du sujet (écartement et rotation externe vont vers l'extérieur du corps).
const SIGNS: Record<RestKind, { flexion: number; lateral: number; twist: number; mirrored: boolean }> = {
  up: { flexion: 1, lateral: 1, twist: -1, mirrored: false },
  down: { flexion: -1, lateral: 1, twist: 1, mirrored: true },
  outward: { flexion: 1, lateral: 1, twist: -1, mirrored: true },
  forward: { flexion: -1, lateral: 1, twist: 1, mirrored: true },
};

const AXIS_X = new THREE.Vector3(1, 0, 0);
const AXIS_Y = new THREE.Vector3(0, 1, 0);
const AXIS_Z = new THREE.Vector3(0, 0, 1);

const ANGLE_BONES: readonly AngleBoneKey[] = BONE_ORDER.filter(
  (key): key is AngleBoneKey => key !== "root",
);

// Conventions (angles en degrés, RELATIFS à l'os parent : un os dont l'angle est nul reste aligné
// sur son parent, donc la main suit l'avant-bras et la tête suit le cou) :
// - `flexion` : rotation autour de l'axe gauche-droite. Positif = l'extrémité de l'os va vers
//   l'avant du corps (os vertical) ; pour le pied et les orteils, positif = vers le haut
//   (flexion dorsale).
// - `lateral` : rotation autour de l'axe avant-arrière. Positif = vers la droite du sujet pour
//   `spine`, `neck` et `head` (inclinaison) ; écartement du corps (abduction) pour les os pairés,
//   miroité à droite ; pour la clavicule, élévation de l'épaule ; pour le pied, inversion.
// - `twist` : rotation autour de l'axe vertical du modèle au repos. Positif = rotation vers la
//   droite du sujet pour `spine`, `neck` et `head` ; rotation externe (le devant de l'os tourne
//   vers l'extérieur du corps) pour les os pairés ; pour la clavicule, projection vers l'avant.
// Composition : d'abord `twist`, puis `lateral`, puis `flexion`. Un bras avec flexion 90 est donc
// à l'horizontale devant soi, et `lateral` l'en écarte dans le plan horizontal.
export function rotationFor(bone: AngleBoneKey, angles: BoneAngles | undefined): THREE.Quaternion {
  const signs = SIGNS[REST_KIND[bone]];
  const side = signs.mirrored && bone.startsWith("R_") ? -1 : 1;
  const flexion = THREE.MathUtils.degToRad(angles?.flexion ?? 0) * signs.flexion;
  const lateral = THREE.MathUtils.degToRad(angles?.lateral ?? 0) * signs.lateral * side;
  const twist = THREE.MathUtils.degToRad(angles?.twist ?? 0) * signs.twist * side;

  const aroundY = new THREE.Quaternion().setFromAxisAngle(AXIS_Y, twist);
  const aroundZ = new THREE.Quaternion().setFromAxisAngle(AXIS_Z, lateral);
  const aroundX = new THREE.Quaternion().setFromAxisAngle(AXIS_X, flexion);
  // Appliqué à un vecteur : d'abord autour de y, puis de z, puis de x.
  return aroundX.multiply(aroundZ).multiply(aroundY);
}

// Direction de repos de l'os dans le repère du modèle.
export function neutralDirection(bone: AngleBoneKey): THREE.Vector3 {
  switch (REST_KIND[bone]) {
    case "up":
      return new THREE.Vector3(0, 1, 0);
    case "down":
      return new THREE.Vector3(0, -1, 0);
    case "outward":
      return new THREE.Vector3(bone.startsWith("L_") ? 1 : -1, 0, 0);
    case "forward":
      return new THREE.Vector3(0, 0, 1);
  }
}

// Direction de chaque os pour une pose, en tenant compte de la chaîne de parents (les angles étant
// relatifs). Sert surtout aux tests : le rendu utilise `applyPoseToSkeleton`.
export function boneDirections(angles: PoseAngles): Record<AngleBoneKey, THREE.Vector3> {
  const delta = {} as Record<BoneKey, THREE.Quaternion>;
  delta.root = new THREE.Quaternion();
  const directions = {} as Record<AngleBoneKey, THREE.Vector3>;
  for (const bone of ANGLE_BONES) {
    delta[bone] = delta[PARENT_OF[bone]].clone().multiply(rotationFor(bone, angles[bone]));
    directions[bone] = neutralDirection(bone).applyQuaternion(delta[bone]);
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
      twist: (a.twist ?? 0) + ((b.twist ?? 0) - (a.twist ?? 0)) * eased,
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

// Pose le squelette : l'orientation monde de chaque os est sa rotation de repos composée avec la
// rotation cumulée de ses ancêtres et la sienne, donc la pose neutre redonne exactement le repos,
// sans roulis ni miroir. Les positions viennent de la hiérarchie du squelette.
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
  // Rotation cumulée (monde) de chaque os par rapport à son repos.
  const delta: Partial<Record<BoneKey, THREE.Quaternion>> = { root: new THREE.Quaternion() };
  const worldQuaternion: Partial<Record<BoneKey, THREE.Quaternion>> = {
    root: rest.root.clone(),
  };

  for (const key of BONE_ORDER) {
    if (key === "root") continue;
    const bone = key as AngleBoneKey;
    const parentKey = PARENT_OF[bone];
    const cumulative = delta[parentKey]!.clone().multiply(rotationFor(bone, angles[bone]));
    delta[key] = cumulative;
    const desired = cumulative.clone().multiply(rest[key]);
    worldQuaternion[key] = desired;
    bones[key].quaternion.copy(worldQuaternion[parentKey]!.clone().invert().multiply(desired));
  }
}
