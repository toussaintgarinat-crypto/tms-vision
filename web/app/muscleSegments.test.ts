import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { BoneKey, BONE_ORDER, buildSkeleton } from "./pose3dSkeleton";
import {
  dominantBoneIndex,
  resolveMeshBoneKey,
  resolveMeshRouting,
  REGION_BY_BONE,
  sideOfBone,
} from "./muscleSegments";

function makeSkinAttributes(assignments: { boneIndex: number; weight: number }[][]) {
  const vertexCount = assignments.length;
  const skinIndices = new Uint16Array(vertexCount * 4);
  const skinWeights = new Float32Array(vertexCount * 4);
  assignments.forEach((slots, vertex) => {
    slots.forEach((slot, i) => {
      skinIndices[vertex * 4 + i] = slot.boneIndex;
      skinWeights[vertex * 4 + i] = slot.weight;
    });
  });
  return {
    skinIndex: new THREE.Uint16BufferAttribute(skinIndices, 4),
    skinWeight: new THREE.Float32BufferAttribute(skinWeights, 4),
  };
}

describe("dominantBoneIndex", () => {
  it("retourne l'os qui accumule le plus de poids sur l'ensemble du maillage", () => {
    const { skinIndex, skinWeight } = makeSkinAttributes([
      [{ boneIndex: 5, weight: 1 }],
      [{ boneIndex: 5, weight: 1 }],
      [{ boneIndex: 2, weight: 1 }],
    ]);

    expect(dominantBoneIndex(skinIndex, skinWeight)).toBe(5);
  });

  it("agrège les poids répartis sur plusieurs des 4 slots d'un même vertex", () => {
    const { skinIndex, skinWeight } = makeSkinAttributes([
      [
        { boneIndex: 3, weight: 0.5 },
        { boneIndex: 3, weight: 0.4 },
        { boneIndex: 7, weight: 0.1 },
      ],
    ]);

    expect(dominantBoneIndex(skinIndex, skinWeight)).toBe(3);
  });
});

describe("REGION_BY_BONE / sideOfBone", () => {
  it("mappe chaque os sur sa région", () => {
    expect(REGION_BY_BONE.spine).toBe("trunk");
    expect(REGION_BY_BONE.neck).toBe("neck");
    expect(REGION_BY_BONE.head).toBe("head");
    expect(REGION_BY_BONE.L_clavicle).toBe("shoulder");
    expect(REGION_BY_BONE.L_upper_arm).toBe("upper_arm");
    expect(REGION_BY_BONE.R_forearm).toBe("lower_arm");
    expect(REGION_BY_BONE.L_hand).toBe("hand");
    expect(REGION_BY_BONE.R_fingers).toBe("hand");
    expect(REGION_BY_BONE.L_thumb).toBe("hand");
    expect(REGION_BY_BONE.R_thigh).toBe("thigh");
    expect(REGION_BY_BONE.L_shin).toBe("lower_leg");
    expect(REGION_BY_BONE.R_toes).toBe("foot");
    expect(REGION_BY_BONE.root).toBe("hip");
  });

  it("couvre tous les os", () => {
    for (const key of BONE_ORDER) expect(REGION_BY_BONE[key], key).toBeDefined();
  });

  it("déduit le côté d'un os depuis son préfixe L_/R_", () => {
    expect(sideOfBone("L_forearm")).toBe("left");
    expect(sideOfBone("R_upper_arm")).toBe("right");
    expect(sideOfBone("spine")).toBeNull();
    expect(sideOfBone("neck")).toBeNull();
  });
});

function buildSingleVertexMesh(boneKey: BoneKey): THREE.SkinnedMesh {
  const { skeleton, bones } = buildSkeleton();
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0], 3));
  const boneIndex = BONE_ORDER.indexOf(boneKey);
  const { skinIndex, skinWeight } = makeSkinAttributes([[{ boneIndex, weight: 1 }]]);
  geometry.setAttribute("skinIndex", skinIndex);
  geometry.setAttribute("skinWeight", skinWeight);
  const mesh = new THREE.SkinnedMesh(geometry, new THREE.MeshStandardMaterial());
  mesh.add(bones.root);
  mesh.bind(skeleton);
  return mesh;
}

describe("resolveMeshBoneKey / resolveMeshRouting", () => {
  it("retrouve le nom de l'os dominant d'un SkinnedMesh réel et son routage", () => {
    const mesh = buildSingleVertexMesh("L_forearm");
    expect(resolveMeshBoneKey(mesh)).toBe("L_forearm");
    expect(resolveMeshRouting(mesh)).toEqual({ region: "lower_arm", segment: "lower_arm", side: "left" });
  });

  it("une région sans zone RULA (cuisse) n'a pas de segment mesuré, mais garde son côté", () => {
    const mesh = buildSingleVertexMesh("R_thigh");
    expect(resolveMeshRouting(mesh)).toEqual({ region: "thigh", segment: null, side: "right" });
  });

  it("ne signale aucun côté pour le tronc (os unique, sans variante gauche/droite)", () => {
    const mesh = buildSingleVertexMesh("spine");
    expect(resolveMeshRouting(mesh)).toEqual({ region: "trunk", segment: "trunk", side: null });
  });

  it("la région déclarée par le fichier 3D prime sur l'os dominant", () => {
    const mesh = buildSingleVertexMesh("spine");
    mesh.userData = { region: "neck", side: "l" };
    // Le cou n'a pas de côté, même si le muscle est exporté en deux objets .l et .r.
    expect(resolveMeshRouting(mesh)).toEqual({ region: "neck", segment: "neck", side: null });
  });

  it("une région du membre prend le côté déclaré par le fichier 3D", () => {
    const mesh = buildSingleVertexMesh("spine");
    mesh.userData = { region: "hand", side: "r" };
    expect(resolveMeshRouting(mesh)).toEqual({ region: "hand", segment: null, side: "right" });
  });
});
