import * as THREE from "three";

export type Pose3DLandmarks = Record<string, [number, number, number]>;

export const BONE_ORDER = [
  "root",
  "spine",
  "neck",
  "L_upper_arm",
  "L_forearm",
  "R_upper_arm",
  "R_forearm",
  "L_thigh",
  "R_thigh",
] as const;
export type BoneKey = (typeof BONE_ORDER)[number];

export const BIND_LENGTH = 1;

interface BoneSpec {
  parent: BoneKey;
  from: readonly string[];
  to: readonly string[];
}

// `from`/`to` : noms de landmarks moyennés pour obtenir les extrémités de
// l'os (utilisé par applyFrameToSkeleton, Task 2/3 de ce plan). Regroupés
// ici avec `parent` pour n'avoir qu'une seule table à maintenir.
const BONE_SPECS: Record<Exclude<BoneKey, "root">, BoneSpec> = {
  spine: { parent: "root", from: ["LEFT_HIP", "RIGHT_HIP"], to: ["LEFT_SHOULDER", "RIGHT_SHOULDER"] },
  neck: { parent: "spine", from: ["LEFT_SHOULDER", "RIGHT_SHOULDER"], to: ["NOSE"] },
  L_upper_arm: { parent: "spine", from: ["LEFT_SHOULDER"], to: ["LEFT_ELBOW"] },
  L_forearm: { parent: "L_upper_arm", from: ["LEFT_ELBOW"], to: ["LEFT_WRIST"] },
  R_upper_arm: { parent: "spine", from: ["RIGHT_SHOULDER"], to: ["RIGHT_ELBOW"] },
  R_forearm: { parent: "R_upper_arm", from: ["RIGHT_ELBOW"], to: ["RIGHT_WRIST"] },
  L_thigh: { parent: "root", from: ["LEFT_HIP"], to: ["LEFT_KNEE"] },
  R_thigh: { parent: "root", from: ["RIGHT_HIP"], to: ["RIGHT_KNEE"] },
};

const ROOT_LANDMARKS = ["LEFT_HIP", "RIGHT_HIP"] as const;

export interface SkeletonRig {
  skeleton: THREE.Skeleton;
  bones: Record<BoneKey, THREE.Bone>;
}

export function buildSkeleton(): SkeletonRig {
  const bones = {} as Record<BoneKey, THREE.Bone>;
  for (const key of BONE_ORDER) {
    bones[key] = new THREE.Bone();
    bones[key].name = key;
  }
  for (const key of BONE_ORDER) {
    if (key === "root") continue;
    const spec = BONE_SPECS[key];
    bones[spec.parent].add(bones[key]);
    bones[key].position.set(0, BIND_LENGTH, 0);
  }
  const skeleton = new THREE.Skeleton(BONE_ORDER.map((key) => bones[key]));
  return { skeleton, bones };
}
