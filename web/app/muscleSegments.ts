import * as THREE from "three";
import { BoneKey } from "./pose3dSkeleton";

export type RulaSegment = "neck" | "trunk" | "upper_arm" | "lower_arm";

export const RULA_SEGMENTS: readonly RulaSegment[] = ["neck", "trunk", "upper_arm", "lower_arm"];

// Un seul os "logique" domine chaque muscle de ce rig (voir Tranche 3 : tronc/
// cou/cuisse en poids rigide déterministe -- 100% sur un seul os -- et
// bras/avant-bras via Automatic Weights mais toujours dominés par un seul des
// deux os possibles) : mapper l'os dominant d'un SkinnedMesh sur son segment
// RULA suffit, pas besoin de connaître le nom du muscle Z-Anatomy lui-même.
export const SEGMENT_BY_BONE: Record<BoneKey, RulaSegment | null> = {
  root: null,
  spine: "trunk",
  neck: "neck",
  L_upper_arm: "upper_arm",
  R_upper_arm: "upper_arm",
  L_forearm: "lower_arm",
  R_forearm: "lower_arm",
  L_thigh: null,
  R_thigh: null,
};

export function sideOfBone(boneKey: BoneKey): "left" | "right" | null {
  if (boneKey.startsWith("L_")) return "left";
  if (boneKey.startsWith("R_")) return "right";
  return null;
}

export function dominantBoneIndex(
  skinIndex: THREE.BufferAttribute,
  skinWeight: THREE.BufferAttribute
): number {
  const totalWeightByBoneIndex = new Map<number, number>();
  for (let vertex = 0; vertex < skinIndex.count; vertex++) {
    const indices = [
      skinIndex.getX(vertex),
      skinIndex.getY(vertex),
      skinIndex.getZ(vertex),
      skinIndex.getW(vertex),
    ];
    const weights = [
      skinWeight.getX(vertex),
      skinWeight.getY(vertex),
      skinWeight.getZ(vertex),
      skinWeight.getW(vertex),
    ];
    for (let slot = 0; slot < 4; slot++) {
      const weight = weights[slot];
      if (weight <= 0) continue;
      const boneIndex = indices[slot];
      totalWeightByBoneIndex.set(boneIndex, (totalWeightByBoneIndex.get(boneIndex) ?? 0) + weight);
    }
  }

  let bestBoneIndex = -1;
  let bestTotal = -Infinity;
  for (const [boneIndex, total] of totalWeightByBoneIndex) {
    // Égalité stricte (`>`, pas `>=`) : en cas d'ex-aequo exact, le premier
    // os rencontré selon l'ordre d'insertion du Map (donc l'ordre des
    // slots skinIndex/skinWeight par vertex) l'emporte. Déterministe, mais
    // sans signification anatomique particulière. Sans conséquence pratique
    // sur ce rig : vérifié qu'aucune primitive du vrai muscle-rig.glb ne
    // présente d'égalité réelle entre deux os (voir muscleRigInvariants.test.ts).
    if (total > bestTotal) {
      bestTotal = total;
      bestBoneIndex = boneIndex;
    }
  }
  if (bestBoneIndex === -1) {
    throw new Error("Aucun poids de peau non nul trouvé sur ce maillage.");
  }
  return bestBoneIndex;
}

export function resolveMeshBoneKey(mesh: THREE.SkinnedMesh): BoneKey {
  const skinIndex = mesh.geometry.attributes.skinIndex as THREE.BufferAttribute;
  const skinWeight = mesh.geometry.attributes.skinWeight as THREE.BufferAttribute;
  const boneIndex = dominantBoneIndex(skinIndex, skinWeight);
  const bone = mesh.skeleton.bones[boneIndex];
  if (!bone) {
    throw new Error(`Index d'os ${boneIndex} hors limites du squelette (mesh "${mesh.name}").`);
  }
  return bone.name as BoneKey;
}

export interface MeshSegmentRouting {
  segment: RulaSegment | null;
  side: "left" | "right" | null;
}

export function resolveMeshRouting(mesh: THREE.SkinnedMesh): MeshSegmentRouting {
  const boneKey = resolveMeshBoneKey(mesh);
  return { segment: SEGMENT_BY_BONE[boneKey] ?? null, side: sideOfBone(boneKey) };
}
