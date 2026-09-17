import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  applyFrameToSkeleton,
  BONE_ORDER,
  BoneKey,
  buildSkeleton,
  Pose3DLandmarks,
} from "./pose3dSkeleton";
import { buildTestSkinnedGeometry } from "./testSkinnedGeometry";

// Test d'intégration squelette + maillage skinné : c'est ce niveau qui manquait
// quand l'avatar est parti en morceaux disjoints hors champ alors que les tests
// unitaires (hiérarchie, rotations, attributs de peau) passaient tous.
// On vérifie ici que les vertices RÉELLEMENT déformés par le skinning tombent
// bien sur le segment de landmarks de leur os, et pas à une unité de là.

// Même pose de référence que `pose3dSkeleton.test.ts` : tronc droit, bras
// gauche à l'horizontale.
const LANDMARKS: Pose3DLandmarks = {
  LEFT_HIP: [-0.1, 0, 0],
  RIGHT_HIP: [0.1, 0, 0],
  LEFT_SHOULDER: [-0.1, -0.5, 0],
  RIGHT_SHOULDER: [0.1, -0.5, 0],
  LEFT_ELBOW: [-0.6, -0.5, 0],
};

// Même convention que `pose3dSkeleton.ts` : MediaPipe est y-vers-le-bas.
function toWorld(name: string): THREE.Vector3 {
  const [x, y, z] = LANDMARKS[name];
  return new THREE.Vector3(x, -y, z);
}

function midpoint(a: THREE.Vector3, b: THREE.Vector3): THREE.Vector3 {
  return new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5);
}

function distanceToSegment(point: THREE.Vector3, a: THREE.Vector3, b: THREE.Vector3): number {
  const ab = new THREE.Vector3().subVectors(b, a);
  const t = THREE.MathUtils.clamp(
    new THREE.Vector3().subVectors(point, a).dot(ab) / ab.lengthSq(),
    0,
    1
  );
  const closest = new THREE.Vector3().copy(a).addScaledVector(ab, t);
  return point.distanceTo(closest);
}

function buildPosedMesh(): THREE.SkinnedMesh {
  const { skeleton, bones } = buildSkeleton();
  const geometry = buildTestSkinnedGeometry();
  const mesh = new THREE.SkinnedMesh(geometry, new THREE.MeshStandardMaterial());
  mesh.add(bones.root);
  mesh.bind(skeleton);

  applyFrameToSkeleton(bones, LANDMARKS, {});

  mesh.updateMatrixWorld(true);
  bones.root.updateMatrixWorld(true);
  mesh.skeleton.update();
  return mesh;
}

// Positions déformées (espace local du mesh, ici confondu avec le monde : le
// mesh est à l'identité) de tous les vertices peints à 100% sur `key`.
function posedVerticesOf(mesh: THREE.SkinnedMesh, key: BoneKey): THREE.Vector3[] {
  const boneIndex = BONE_ORDER.indexOf(key);
  const position = mesh.geometry.attributes.position;
  const skinIndex = mesh.geometry.attributes.skinIndex;
  const posed: THREE.Vector3[] = [];
  for (let i = 0; i < position.count; i++) {
    if (skinIndex.getX(i) !== boneIndex) continue;
    const vertex = new THREE.Vector3().fromBufferAttribute(position, i);
    mesh.applyBoneTransform(i, vertex);
    posed.push(vertex);
  }
  return posed;
}

describe("skinning bout-en-bout (squelette + géométrie + bind + pose)", () => {
  it("place les vertices déformés de chaque os sur son segment de landmarks", () => {
    const mesh = buildPosedMesh();

    // Rayon du cylindre (0.05) + écart entre l'os (longueur fixe) et le
    // segment de landmarks mesuré : une tolérance large suffit pour attraper un
    // os décalé d'une unité entière ou posé sur un autre membre.
    const TOLERANCE = 0.15;

    const midHip = midpoint(toWorld("LEFT_HIP"), toWorld("RIGHT_HIP"));
    const midShoulder = midpoint(toWorld("LEFT_SHOULDER"), toWorld("RIGHT_SHOULDER"));

    const spineVertices = posedVerticesOf(mesh, "spine");
    expect(spineVertices.length).toBeGreaterThan(0);
    for (const vertex of spineVertices) {
      expect(distanceToSegment(vertex, midHip, midShoulder)).toBeLessThan(TOLERANCE);
    }

    const shoulder = toWorld("LEFT_SHOULDER");
    const elbow = toWorld("LEFT_ELBOW");
    const armVertices = posedVerticesOf(mesh, "L_upper_arm");
    expect(armVertices.length).toBeGreaterThan(0);
    for (const vertex of armVertices) {
      expect(distanceToSegment(vertex, shoulder, elbow)).toBeLessThan(TOLERANCE);
    }
  });

  it("ne confond pas le bras gauche avec le tronc (os distincts, pas superposés)", () => {
    const mesh = buildPosedMesh();

    const armCentroid = posedVerticesOf(mesh, "L_upper_arm")
      .reduce((acc, vertex) => acc.add(vertex), new THREE.Vector3())
      .multiplyScalar(1 / posedVerticesOf(mesh, "L_upper_arm").length);

    // Le bras gauche part vers les x négatifs (convention MediaPipe conservée
    // telle quelle), le tronc reste sur l'axe x ≈ 0.
    expect(armCentroid.x).toBeLessThan(-0.05);

    const midHip = midpoint(toWorld("LEFT_HIP"), toWorld("RIGHT_HIP"));
    const midShoulder = midpoint(toWorld("LEFT_SHOULDER"), toWorld("RIGHT_SHOULDER"));
    expect(distanceToSegment(armCentroid, midHip, midShoulder)).toBeGreaterThan(0.1);
  });

  it("garde tout le maillage déformé dans un volume de taille humaine autour de la racine", () => {
    const mesh = buildPosedMesh();
    const position = mesh.geometry.attributes.position;

    for (let i = 0; i < position.count; i++) {
      const vertex = new THREE.Vector3().fromBufferAttribute(position, i);
      mesh.applyBoneTransform(i, vertex);
      // Aucune partie du corps ne doit se retrouver à plus d'1.5 m de la racine
      // (hanches) : c'est exactement le symptôme qu'avait le bug d'origine.
      expect(vertex.length()).toBeLessThan(1.5);
    }
  });
});
