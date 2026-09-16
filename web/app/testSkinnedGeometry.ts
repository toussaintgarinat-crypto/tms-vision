import * as THREE from "three";
import { BIND_LENGTH, BONE_ORDER, BoneKey } from "./pose3dSkeleton";

const CYLINDER_RADIUS = 0.05;
const HEAD_RADIUS = 0.12;

export function buildTestSkinnedGeometry(): THREE.BufferGeometry {
  const boneIndexOf = {} as Record<BoneKey, number>;
  BONE_ORDER.forEach((key, index) => {
    boneIndexOf[key] = index;
  });

  const geometries: THREE.BufferGeometry[] = [];
  for (const key of BONE_ORDER) {
    if (key === "root") continue;
    const cylinder = new THREE.CylinderGeometry(CYLINDER_RADIUS, CYLINDER_RADIUS, BIND_LENGTH, 8);
    cylinder.translate(0, BIND_LENGTH / 2, 0);
    assignSkinAttributes(cylinder, boneIndexOf[key]);
    geometries.push(cylinder);
  }

  const head = new THREE.SphereGeometry(HEAD_RADIUS, 12, 12);
  head.translate(0, BIND_LENGTH, 0);
  assignSkinAttributes(head, boneIndexOf.neck);
  geometries.push(head);

  return mergeBufferGeometries(geometries);
}

function assignSkinAttributes(geometry: THREE.BufferGeometry, boneIndex: number): void {
  const vertexCount = geometry.attributes.position.count;
  const skinIndices = new Uint16Array(vertexCount * 4);
  const skinWeights = new Float32Array(vertexCount * 4);
  for (let i = 0; i < vertexCount; i++) {
    skinIndices[i * 4] = boneIndex;
    skinWeights[i * 4] = 1;
  }
  geometry.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(skinIndices, 4));
  geometry.setAttribute("skinWeight", new THREE.Float32BufferAttribute(skinWeights, 4));
}

function mergeBufferGeometries(geometries: THREE.BufferGeometry[]): THREE.BufferGeometry {
  const merged = new THREE.BufferGeometry();
  const positions: number[] = [];
  const normals: number[] = [];
  const skinIndices: number[] = [];
  const skinWeights: number[] = [];
  const indices: number[] = [];
  let vertexOffset = 0;

  for (const geometry of geometries) {
    const positionAttr = geometry.attributes.position;
    const normalAttr = geometry.attributes.normal;
    const skinIndexAttr = geometry.attributes.skinIndex;
    const skinWeightAttr = geometry.attributes.skinWeight;
    const indexAttr = geometry.index;
    if (!indexAttr) {
      throw new Error("La géométrie doit être indexée avant la fusion.");
    }

    for (let i = 0; i < positionAttr.count; i++) {
      positions.push(positionAttr.getX(i), positionAttr.getY(i), positionAttr.getZ(i));
      normals.push(normalAttr.getX(i), normalAttr.getY(i), normalAttr.getZ(i));
      skinIndices.push(
        skinIndexAttr.getX(i),
        skinIndexAttr.getY(i),
        skinIndexAttr.getZ(i),
        skinIndexAttr.getW(i)
      );
      skinWeights.push(
        skinWeightAttr.getX(i),
        skinWeightAttr.getY(i),
        skinWeightAttr.getZ(i),
        skinWeightAttr.getW(i)
      );
    }
    for (let i = 0; i < indexAttr.count; i++) {
      indices.push(indexAttr.getX(i) + vertexOffset);
    }
    vertexOffset += positionAttr.count;
  }

  merged.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  merged.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  merged.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(skinIndices, 4));
  merged.setAttribute("skinWeight", new THREE.Float32BufferAttribute(skinWeights, 4));
  merged.setIndex(indices);
  return merged;
}
