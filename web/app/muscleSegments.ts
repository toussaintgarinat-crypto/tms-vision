import * as THREE from "three";
import { BoneKey } from "./pose3dSkeleton";
import type { Region } from "./exercisePose";

// Zones mesurées par la vidéo : les quatre zones RULA, plus la main et le pied (Tranche 5, notés hors
// RULA, voir src/tms_vision/extremities.py).
export type RulaSegment = "neck" | "trunk" | "upper_arm" | "lower_arm" | "hand" | "foot";

export const RULA_SEGMENTS: readonly RulaSegment[] = [
  "neck",
  "trunk",
  "upper_arm",
  "lower_arm",
  "hand",
  "foot",
];

// Repli quand un maillage ne porte pas sa région dans le fichier 3D (anciens fichiers) : l'os qui
// domine ses poids de peau donne la région. Le fichier actuel porte la région de chaque muscle
// (`userData.region`, exportée par tools/blender/export_muscle_rig.py), qui prime.
export const REGION_BY_BONE: Record<BoneKey, Region | null> = {
  root: "hip",
  spine: "trunk",
  neck: "neck",
  head: "head",
  L_clavicle: "shoulder",
  R_clavicle: "shoulder",
  L_upper_arm: "upper_arm",
  R_upper_arm: "upper_arm",
  L_forearm: "lower_arm",
  R_forearm: "lower_arm",
  L_hand: "hand",
  R_hand: "hand",
  L_fingers: "hand",
  R_fingers: "hand",
  L_thumb: "hand",
  R_thumb: "hand",
  L_thigh: "thigh",
  R_thigh: "thigh",
  L_shin: "lower_leg",
  R_shin: "lower_leg",
  L_foot: "foot",
  R_foot: "foot",
  L_toes: "foot",
  R_toes: "foot",
};

// Régions dont les muscles ont un côté (gauche ou droit) ; le tronc, le cou et la tête n'en ont pas.
const SIDED_REGIONS: ReadonlySet<Region> = new Set<Region>([
  "upper_arm",
  "lower_arm",
  "shoulder",
  "hand",
  "hip",
  "thigh",
  "lower_leg",
  "foot",
]);

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
  // Région du muscle (`null` si inconnue).
  region: Region | null;
  // Zone RULA mesurée, ou `null` pour les régions sans donnée mesurée (elles restent grises dans
  // l'analyse : on ne colore jamais une donnée non mesurée).
  segment: RulaSegment | null;
  side: "left" | "right" | null;
}

function isRulaSegment(region: Region | null): region is RulaSegment {
  return region !== null && (RULA_SEGMENTS as readonly string[]).includes(region);
}

export function resolveMeshRouting(mesh: THREE.SkinnedMesh): MeshSegmentRouting {
  const declared = mesh.userData?.region as Region | undefined;
  const boneKey = resolveMeshBoneKey(mesh);
  const region = declared ?? REGION_BY_BONE[boneKey] ?? null;

  let side: "left" | "right" | null = null;
  if (region !== null && SIDED_REGIONS.has(region)) {
    const declaredSide = mesh.userData?.side as string | undefined;
    side = declaredSide === "l" ? "left" : declaredSide === "r" ? "right" : sideOfBone(boneKey);
  }
  return { region, segment: isRulaSegment(region) ? region : null, side };
}
