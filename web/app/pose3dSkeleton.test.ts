import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { applyFrameToSkeleton, BONE_ORDER, buildSkeleton, Pose3DLandmarks } from "./pose3dSkeleton";

describe("buildSkeleton", () => {
  it("crée 9 os (racine + 8) avec la hiérarchie attendue", () => {
    const { skeleton, bones } = buildSkeleton();

    expect(BONE_ORDER.length).toBe(9);
    expect(skeleton.bones.length).toBe(9);

    expect(bones.root.parent).toBeNull();
    expect(bones.spine.parent).toBe(bones.root);
    expect(bones.neck.parent).toBe(bones.spine);
    expect(bones.L_upper_arm.parent).toBe(bones.spine);
    expect(bones.L_forearm.parent).toBe(bones.L_upper_arm);
    expect(bones.R_upper_arm.parent).toBe(bones.spine);
    expect(bones.R_forearm.parent).toBe(bones.R_upper_arm);
    expect(bones.L_thigh.parent).toBe(bones.root);
    expect(bones.R_thigh.parent).toBe(bones.root);
  });
});

function worldDirection(bone: THREE.Bone): THREE.Vector3 {
  bone.updateWorldMatrix(true, false);
  const worldQuat = new THREE.Quaternion();
  bone.getWorldQuaternion(worldQuat);
  return new THREE.Vector3(0, 1, 0).applyQuaternion(worldQuat).normalize();
}

describe("applyFrameToSkeleton", () => {
  it("aligne le tronc à la verticale et le bras gauche à l'horizontale pour une pose de référence", () => {
    const { bones } = buildSkeleton();

    // Landmarks bruts MediaPipe (x droite, y vers le bas, échelle métrique).
    // Hanches et épaules alignées verticalement (tronc droit), coude gauche
    // à la même hauteur que l'épaule mais très écarté (bras à l'horizontale).
    const landmarks: Pose3DLandmarks = {
      LEFT_HIP: [-0.1, 0, 0],
      RIGHT_HIP: [0.1, 0, 0],
      LEFT_SHOULDER: [-0.1, -0.5, 0],
      RIGHT_SHOULDER: [0.1, -0.5, 0],
      LEFT_ELBOW: [-0.6, -0.5, 0],
    };

    applyFrameToSkeleton(bones, landmarks, {});

    const spineDir = worldDirection(bones.spine);
    expect(spineDir.x).toBeCloseTo(0, 5);
    expect(spineDir.y).toBeCloseTo(1, 5);
    expect(spineDir.z).toBeCloseTo(0, 5);

    const upperArmDir = worldDirection(bones.L_upper_arm);
    expect(upperArmDir.x).toBeCloseTo(-1, 5);
    expect(upperArmDir.y).toBeCloseTo(0, 5);
    expect(upperArmDir.z).toBeCloseTo(0, 5);

    expect(bones.root.position.x).toBeCloseTo(0, 5);
    expect(bones.root.position.y).toBeCloseTo(0, 5);
    expect(bones.root.position.z).toBeCloseTo(0, 5);
  });
});

describe("applyFrameToSkeleton — landmarks manquants ou os dégénéré", () => {
  it("garde la direction précédente d'un os quand son landmark disparaît une frame", () => {
    const { bones } = buildSkeleton();
    const cache: Partial<Pose3DLandmarks> = {};

    applyFrameToSkeleton(
      bones,
      {
        LEFT_HIP: [-0.1, 0, 0],
        RIGHT_HIP: [0.1, 0, 0],
        LEFT_SHOULDER: [-0.1, -0.5, 0],
        RIGHT_SHOULDER: [0.1, -0.5, 0],
        LEFT_ELBOW: [-0.6, -0.5, 0],
      },
      cache
    );
    const firstDirection = worldDirection(bones.L_upper_arm).clone();

    applyFrameToSkeleton(
      bones,
      {
        LEFT_HIP: [-0.1, 0, 0],
        RIGHT_HIP: [0.1, 0, 0],
        LEFT_SHOULDER: [-0.1, -0.5, 0],
        RIGHT_SHOULDER: [0.1, -0.5, 0],
        // LEFT_ELBOW manquant cette frame (occlusion) : réutilise la valeur en cache.
      },
      cache
    );
    const secondDirection = worldDirection(bones.L_upper_arm);

    expect(secondDirection.x).toBeCloseTo(firstDirection.x, 5);
    expect(secondDirection.y).toBeCloseTo(firstDirection.y, 5);
    expect(secondDirection.z).toBeCloseTo(firstDirection.z, 5);
  });

  it("garde la rotation locale précédente d'un os si ses deux landmarks sont confondus", () => {
    const { bones } = buildSkeleton();
    const cache: Partial<Pose3DLandmarks> = {};

    applyFrameToSkeleton(
      bones,
      {
        LEFT_HIP: [-0.1, 0, 0],
        RIGHT_HIP: [0.1, 0, 0],
        LEFT_SHOULDER: [-0.1, -0.5, 0],
        RIGHT_SHOULDER: [0.1, -0.5, 0],
        LEFT_ELBOW: [-0.6, -0.5, 0],
      },
      cache
    );
    const before = bones.L_upper_arm.quaternion.clone();

    applyFrameToSkeleton(
      bones,
      {
        LEFT_HIP: [-0.1, 0, 0],
        RIGHT_HIP: [0.1, 0, 0],
        LEFT_SHOULDER: [-0.2, -0.3, 0],
        RIGHT_SHOULDER: [0.1, -0.5, 0],
        LEFT_ELBOW: [-0.2, -0.3, 0], // confondu avec l'épaule cette frame
      },
      cache
    );
    const after = bones.L_upper_arm.quaternion;

    expect(after.x).toBeCloseTo(before.x, 5);
    expect(after.y).toBeCloseTo(before.y, 5);
    expect(after.z).toBeCloseTo(before.z, 5);
    expect(after.w).toBeCloseTo(before.w, 5);
  });
});
