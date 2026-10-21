import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  applyFrameToSkeleton,
  BONE_ORDER,
  buildSkeleton,
  PARENT_OF,
  Pose3DLandmarks,
} from "./pose3dSkeleton";

describe("buildSkeleton", () => {
  it("crée 24 os avec la hiérarchie attendue", () => {
    const { skeleton, bones } = buildSkeleton();

    expect(BONE_ORDER.length).toBe(24);
    expect(skeleton.bones.length).toBe(24);

    expect(bones.root.parent).toBeNull();
    expect(bones.spine.parent).toBe(bones.root);
    expect(bones.neck.parent).toBe(bones.spine);
    expect(bones.head.parent).toBe(bones.neck);
    expect(bones.L_clavicle.parent).toBe(bones.spine);
    expect(bones.L_upper_arm.parent).toBe(bones.L_clavicle);
    expect(bones.L_forearm.parent).toBe(bones.L_upper_arm);
    expect(bones.R_upper_arm.parent).toBe(bones.R_clavicle);
    expect(bones.R_forearm.parent).toBe(bones.R_upper_arm);
    expect(bones.L_hand.parent).toBe(bones.L_forearm);
    expect(bones.L_fingers.parent).toBe(bones.L_hand);
    expect(bones.L_thumb.parent).toBe(bones.L_hand);
    expect(bones.L_thigh.parent).toBe(bones.root);
    expect(bones.R_thigh.parent).toBe(bones.root);
    expect(bones.L_shin.parent).toBe(bones.L_thigh);
    expect(bones.R_foot.parent).toBe(bones.R_shin);
    expect(bones.R_toes.parent).toBe(bones.R_foot);
  });

  it("place chaque os après son parent dans BONE_ORDER", () => {
    for (const key of BONE_ORDER) {
      if (key === "root") continue;
      expect(BONE_ORDER.indexOf(PARENT_OF[key]), key).toBeLessThan(BONE_ORDER.indexOf(key));
    }
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
    // Os dégénéré (landmarks confondus) mais PAS manquant : ne doit pas
    // déclencher le masquage par échelle, contrairement au cas "jamais vu".
    expect(bones.L_upper_arm.scale.x).toBeCloseTo(1, 5);
    expect(bones.L_upper_arm.scale.y).toBeCloseTo(1, 5);
    expect(bones.L_upper_arm.scale.z).toBeCloseTo(1, 5);
  });

  it("masque (échelle quasi nulle) un os dont le landmark n'a jamais été détecté, sans affecter un os valide", () => {
    const { bones } = buildSkeleton();
    const cache: Partial<Pose3DLandmarks> = {};

    // Vue de profil : LEFT_ELBOW n'apparaît jamais (occlusion sur toute la
    // vidéo), contrairement au reste des landmarks du tronc.
    applyFrameToSkeleton(
      bones,
      {
        LEFT_HIP: [-0.1, 0, 0],
        RIGHT_HIP: [0.1, 0, 0],
        LEFT_SHOULDER: [-0.1, -0.5, 0],
        RIGHT_SHOULDER: [0.1, -0.5, 0],
      },
      cache
    );

    expect(bones.L_upper_arm.scale.x).toBeLessThan(1e-3);
    expect(bones.L_upper_arm.scale.y).toBeLessThan(1e-3);
    expect(bones.L_upper_arm.scale.z).toBeLessThan(1e-3);
    // Un os avec des landmarks valides ne doit pas être affecté.
    expect(bones.spine.scale.x).toBeCloseTo(1, 5);
    expect(bones.spine.scale.y).toBeCloseTo(1, 5);
    expect(bones.spine.scale.z).toBeCloseTo(1, 5);
  });

  it("restaure l'échelle à 1 dès que le landmark manquant est enfin détecté", () => {
    const { bones } = buildSkeleton();
    const cache: Partial<Pose3DLandmarks> = {};

    applyFrameToSkeleton(
      bones,
      {
        LEFT_HIP: [-0.1, 0, 0],
        RIGHT_HIP: [0.1, 0, 0],
        LEFT_SHOULDER: [-0.1, -0.5, 0],
        RIGHT_SHOULDER: [0.1, -0.5, 0],
        // LEFT_ELBOW jamais vu pour l'instant.
      },
      cache
    );
    expect(bones.L_upper_arm.scale.x).toBeLessThan(1e-3);

    applyFrameToSkeleton(
      bones,
      {
        LEFT_HIP: [-0.1, 0, 0],
        RIGHT_HIP: [0.1, 0, 0],
        LEFT_SHOULDER: [-0.1, -0.5, 0],
        RIGHT_SHOULDER: [0.1, -0.5, 0],
        LEFT_ELBOW: [-0.6, -0.5, 0], // enfin détecté.
      },
      cache
    );

    expect(bones.L_upper_arm.scale.x).toBeCloseTo(1, 5);
    expect(bones.L_upper_arm.scale.y).toBeCloseTo(1, 5);
    expect(bones.L_upper_arm.scale.z).toBeCloseTo(1, 5);
  });
});

describe("applyFrameToSkeleton — nouveaux os du corps complet", () => {
  const upright = {
    LEFT_HIP: [-0.1, 0, 0],
    RIGHT_HIP: [0.1, 0, 0],
    LEFT_SHOULDER: [-0.1, -0.5, 0],
    RIGHT_SHOULDER: [0.1, -0.5, 0],
  } as Pose3DLandmarks;

  it("oriente la main du poignet vers le milieu de l'index et de l'auriculaire", () => {
    const { bones } = buildSkeleton();
    applyFrameToSkeleton(
      bones,
      {
        ...upright,
        LEFT_ELBOW: [-0.1, -0.2, 0],
        LEFT_WRIST: [-0.1, 0.1, 0],
        LEFT_INDEX: [-0.4, 0.1, 0],
        LEFT_PINKY: [-0.4, 0.1, 0],
      },
      {}
    );

    const direction = worldDirection(bones.L_hand);
    expect(direction.x).toBeCloseTo(-1, 5);
    expect(direction.y).toBeCloseTo(0, 5);
  });

  it("oriente la jambe et le pied avec le genou, la cheville, le talon et le bout du pied", () => {
    const { bones } = buildSkeleton();
    applyFrameToSkeleton(
      bones,
      {
        ...upright,
        LEFT_KNEE: [-0.1, 0.4, 0],
        LEFT_ANKLE: [-0.1, 0.8, 0],
        LEFT_HEEL: [-0.1, 0.85, 0.1],
        LEFT_FOOT_INDEX: [-0.1, 0.85, -0.2],
      },
      {}
    );

    const shin = worldDirection(bones.L_shin);
    expect(shin.y).toBeCloseTo(-1, 5);
    const foot = worldDirection(bones.L_foot);
    expect(foot.z).toBeCloseTo(-1, 5);
  });

  it("les os sans point de repère (tête, clavicule, doigts, orteils) suivent leur parent sans être masqués", () => {
    const { bones } = buildSkeleton();
    applyFrameToSkeleton(
      bones,
      { ...upright, LEFT_ELBOW: [-0.6, -0.5, 0], LEFT_WRIST: [-1.0, -0.5, 0], LEFT_INDEX: [-1.3, -0.5, 0], LEFT_PINKY: [-1.3, -0.5, 0] },
      {}
    );

    for (const key of ["head", "L_clavicle", "R_clavicle", "L_fingers", "R_toes"] as const) {
      expect(bones[key].scale.x, key).toBeCloseTo(1, 5);
    }
    // Les doigts prolongent la main.
    const hand = worldDirection(bones.L_hand);
    const fingers = worldDirection(bones.L_fingers);
    expect(fingers.distanceTo(hand)).toBeLessThan(1e-5);
  });
});
