import { beforeAll, describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import * as THREE from "three";
import { GLTFLoader, GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import {
  AngleBoneKey,
  Exercise,
  PoseAngles,
  activeInstruction,
  applyPoseToSkeleton,
  boneDirections,
  captureRestPose,
  samplePose,
} from "./exercisePose";
import { MuscleModel, prepareMuscleModel } from "./muscleModel";
import { resolveMeshBoneKey } from "./muscleSegments";
import { BONE_ORDER, BoneKey } from "./pose3dSkeleton";


function expectDirection(actual: THREE.Vector3, x: number, y: number, z: number) {
  expect(actual.x).toBeCloseTo(x, 6);
  expect(actual.y).toBeCloseTo(y, 6);
  expect(actual.z).toBeCloseTo(z, 6);
}

describe("orientation du modèle réel (web/public/muscle-rig.glb)", () => {
  // Verrouille les faits dont dépend le sens des angles : le côté gauche du
  // modèle est +x, et son avant est +z (face à la caméra de l'avatar).
  let meshes: { mesh: THREE.SkinnedMesh; centre: THREE.Vector3 }[];

  beforeAll(async () => {
    const buffer = fs.readFileSync(path.resolve(__dirname, "..", "public", "muscle-rig.glb"));
    const arrayBuffer = buffer.buffer.slice(
      buffer.byteOffset,
      buffer.byteOffset + buffer.byteLength,
    ) as ArrayBuffer;
    const gltf = await new Promise<GLTF>((resolve, reject) => {
      new GLTFLoader().parse(arrayBuffer, "", resolve, reject);
    });
    meshes = [];
    gltf.scene.traverse((object) => {
      const mesh = object as THREE.SkinnedMesh;
      if (!mesh.isSkinnedMesh) return;
      mesh.geometry.computeBoundingBox();
      const centre = new THREE.Vector3();
      mesh.geometry.boundingBox!.getCenter(centre);
      meshes.push({ mesh, centre });
    });
  });

  it("place les muscles du bras gauche en +x et ceux du bras droit en -x", () => {
    const left = meshes.filter(({ mesh }) => resolveMeshBoneKey(mesh) === "L_upper_arm");
    const right = meshes.filter(({ mesh }) => resolveMeshBoneKey(mesh) === "R_upper_arm");

    expect(left.length).toBeGreaterThan(0);
    expect(right.length).toBeGreaterThan(0);
    expect(left.every(({ centre }) => centre.x > 0.05)).toBe(true);
    expect(right.every(({ centre }) => centre.x < -0.05)).toBe(true);
  });

  it("place l'avant du corps vers +z : un muscle postérieur est derrière un muscle antérieur", () => {
    const find = (prefix: string) =>
      meshes.find(({ mesh }) => mesh.name.startsWith(prefix))!.centre;

    const trapezius = find("Descending_part_of_trapezius_muscle");
    const oblique = find("External_abdominal_oblique_muscle");

    expect(trapezius.z).toBeLessThan(oblique.z);
  });
});

describe("boneDirections", () => {
  it("donne la posture neutre : tronc et cou vers le haut, membres vers le bas", () => {
    const directions = boneDirections({});

    expectDirection(directions.spine, 0, 1, 0);
    expectDirection(directions.neck, 0, 1, 0);
    for (const bone of ["L_upper_arm", "R_upper_arm", "L_forearm", "R_forearm", "L_thigh", "R_thigh"] as const) {
      expectDirection(directions[bone], 0, -1, 0);
    }
  });

  it("flexion positive : l'extrémité de l'os va vers l'avant (+z), pour tous les os", () => {
    const flexed = boneDirections({
      spine: { flexion: 90 },
      neck: { flexion: 90 },
      R_upper_arm: { flexion: 90 },
      L_upper_arm: { flexion: 90 },
      R_thigh: { flexion: 90 },
    });

    expectDirection(flexed.spine, 0, 0, 1);
    expectDirection(flexed.neck, 0, 0, 1);
    expectDirection(flexed.R_upper_arm, 0, 0, 1);
    expectDirection(flexed.L_upper_arm, 0, 0, 1);
    expectDirection(flexed.R_thigh, 0, 0, 1);
  });

  it("flexion négative : vers l'arrière (extension)", () => {
    const extended = boneDirections({ spine: { flexion: -90 }, L_upper_arm: { flexion: -90 } });

    expectDirection(extended.spine, 0, 0, -1);
    expectDirection(extended.L_upper_arm, 0, 0, -1);
  });

  it("lateral positif sur le tronc et le cou : vers la droite du sujet (-x)", () => {
    const tilted = boneDirections({ spine: { lateral: 90 }, neck: { lateral: 35 } });

    expectDirection(tilted.spine, -1, 0, 0);
    expect(tilted.neck.x).toBeCloseTo(-Math.sin(THREE.MathUtils.degToRad(35)), 6);
    expect(tilted.neck.y).toBeCloseTo(Math.cos(THREE.MathUtils.degToRad(35)), 6);
  });

  it("lateral positif sur un membre pairé : écartement du corps, avec le miroir gauche/droite", () => {
    const abducted = boneDirections({
      L_upper_arm: { lateral: 90 },
      R_upper_arm: { lateral: 90 },
      L_thigh: { lateral: 30 },
      R_thigh: { lateral: 30 },
    });

    expectDirection(abducted.L_upper_arm, 1, 0, 0);
    expectDirection(abducted.R_upper_arm, -1, 0, 0);
    expect(abducted.L_thigh.x).toBeGreaterThan(0);
    expect(abducted.R_thigh.x).toBeLessThan(0);
    expect(abducted.L_thigh.x).toBeCloseTo(-abducted.R_thigh.x, 6);
  });

  it("compose l'écartement puis la flexion : bras horizontal croisé devant la poitrine", () => {
    const crossed = boneDirections({ R_upper_arm: { flexion: 90, lateral: -45 } });

    // Bras droit à l'horizontale devant soi, ramené de 45° vers le milieu du corps
    // (donc vers +x, du côté du bras gauche).
    expectDirection(crossed.R_upper_arm, Math.SQRT1_2, 0, Math.SQRT1_2);
  });

  it("flexion de 180° sur un avant-bras : il pointe vers le haut (coude plié, bras levé devant)", () => {
    const bent = boneDirections({ R_forearm: { flexion: 180 } });

    expectDirection(bent.R_forearm, 0, 1, 0);
  });

  it("retourne des vecteurs unitaires", () => {
    const directions = boneDirections({
      spine: { flexion: 33, lateral: -12 },
      L_upper_arm: { flexion: 140, lateral: 55 },
      R_forearm: { flexion: -20, lateral: 170 },
    });

    for (const vector of Object.values(directions)) {
      expect(vector.length()).toBeCloseTo(1, 6);
    }
  });
});

function exercise(overrides: Partial<Exercise> = {}): Exercise {
  return {
    id: "test",
    zone: "neck",
    title: "Test",
    description: "Test",
    status: "draft",
    source: "human",
    validated_by: null,
    validated_on: null,
    view: "front",
    target_segments: ["neck"],
    poses: {
      neutral: {},
      tilt: { neck: { lateral: 40 }, spine: { flexion: 20 } },
    },
    keyframes: [
      { t: 0, pose: "neutral" },
      { t: 10, pose: "tilt" },
      { t: 20, pose: "tilt" },
      { t: 30, pose: "neutral" },
    ],
    instructions: [
      { t: 0, text: "Début." },
      { t: 10, text: "Maintenez." },
    ],
    duration_seconds: 30,
    ...overrides,
  };
}

describe("samplePose", () => {
  it("renvoie exactement la pose aux instants des poses clés", () => {
    const e = exercise();

    expect(samplePose(e, 10).neck?.lateral).toBeCloseTo(40, 9);
    expect(samplePose(e, 10).spine?.flexion).toBeCloseTo(20, 9);
    expect(samplePose(e, 0).neck?.lateral ?? 0).toBeCloseTo(0, 9);
  });

  it("adoucit le mouvement entre deux poses : milieu à 50 % mais départ plus lent qu'un linéaire", () => {
    const e = exercise();

    expect(samplePose(e, 5).neck?.lateral).toBeCloseTo(20, 9);
    // smoothstep(0.1) = 0.028, donc 1.12° contre 4° pour une interpolation linéaire.
    expect(samplePose(e, 1).neck?.lateral).toBeCloseTo(40 * 0.028, 9);
    expect(samplePose(e, 1).neck?.lateral as number).toBeLessThan(4);
  });

  it("tient la position entre deux poses clés identiques", () => {
    const e = exercise();

    expect(samplePose(e, 15).neck?.lateral).toBeCloseTo(40, 9);
    expect(samplePose(e, 12.5).neck?.lateral).toBeCloseTo(40, 9);
  });

  it("revient à neutre sur la dernière pose", () => {
    expect(samplePose(exercise(), 30).neck?.lateral ?? 0).toBeCloseTo(0, 9);
  });

  it("borne le temps : avant 0 la première pose, après la fin la dernière", () => {
    const e = exercise();

    expect(samplePose(e, -5).neck?.lateral ?? 0).toBeCloseTo(0, 9);
    expect(samplePose(e, 999).neck?.lateral ?? 0).toBeCloseTo(0, 9);
  });

  it("interpole un os absent d'une des deux poses depuis l'angle neutre (0)", () => {
    const e = exercise({
      poses: { neutral: {}, raised: { R_upper_arm: { flexion: 90 } } },
      keyframes: [{ t: 0, pose: "neutral" }, { t: 10, pose: "raised" }],
    });

    expect(samplePose(e, 5).R_upper_arm?.flexion).toBeCloseTo(45, 9);
  });

  it("est déterministe : le même instant donne la même pose", () => {
    const e = exercise();

    expect(samplePose(e, 7.3)).toEqual(samplePose(e, 7.3));
  });
});

describe("activeInstruction", () => {
  const e = exercise();

  it("ne renvoie rien avant la première consigne", () => {
    expect(activeInstruction(exercise({ instructions: [{ t: 3, text: "Plus tard." }] }), 1)).toBeNull();
  });

  it("renvoie la consigne en cours, puis la dernière après elle", () => {
    expect(activeInstruction(e, 0)).toEqual({ text: "Début.", index: 0 });
    expect(activeInstruction(e, 9.99)).toEqual({ text: "Début.", index: 0 });
    expect(activeInstruction(e, 10)).toEqual({ text: "Maintenez.", index: 1 });
    expect(activeInstruction(e, 29)).toEqual({ text: "Maintenez.", index: 1 });
  });
});

const UP_BONES: readonly string[] = ["spine", "neck"];

const POSES_TO_CHECK: Record<string, PoseAngles> = {
  neutral: {},
  neck_tilt: { neck: { lateral: 35 } },
  trunk_forward: { spine: { flexion: 40 } },
  trunk_back: { spine: { flexion: -15 } },
  shoulder_cross: {
    R_upper_arm: { flexion: 90, lateral: -45 },
    R_forearm: { flexion: 90, lateral: -45 },
  },
  elbow_bent: { L_upper_arm: { flexion: 90 }, L_forearm: { flexion: 180 } },
  everything: {
    spine: { flexion: 25, lateral: -10 },
    neck: { flexion: 15, lateral: 20 },
    L_upper_arm: { flexion: 60, lateral: 30 },
    L_forearm: { flexion: 100, lateral: 10 },
    R_upper_arm: { flexion: -20, lateral: 70 },
    R_forearm: { flexion: 45, lateral: -30 },
    L_thigh: { flexion: 20, lateral: 10 },
    R_thigh: { flexion: -10, lateral: 15 },
  },
};

describe("applyPoseToSkeleton sur le vrai squelette (web/public/muscle-rig.glb)", () => {
  let model: MuscleModel;
  let rest: ReturnType<typeof captureRestPose>;
  let restPositions: Record<BoneKey, THREE.Vector3>;

  const worldQuaternion = (bone: THREE.Bone) => bone.getWorldQuaternion(new THREE.Quaternion());
  const worldPosition = (bone: THREE.Bone) => bone.getWorldPosition(new THREE.Vector3());

  // Centre (monde) des maillages dont l'os dominant est `boneKey`, squelette à jour.
  function centreOf(boneKey: BoneKey): THREE.Vector3 {
    model.scene.updateMatrixWorld(true);
    const centre = new THREE.Vector3();
    let count = 0;
    model.meshes.forEach((mesh) => {
      if (resolveMeshBoneKey(mesh) !== boneKey) return;
      mesh.skeleton.update();
      mesh.computeBoundingBox();
      centre.add(mesh.boundingBox!.clone().applyMatrix4(mesh.matrixWorld).getCenter(new THREE.Vector3()));
      count++;
    });
    return centre.multiplyScalar(1 / count);
  }

  function pose(angles: PoseAngles) {
    applyPoseToSkeleton(model.bones, rest, angles);
    model.scene.updateMatrixWorld(true);
  }

  beforeAll(async () => {
    const buffer = fs.readFileSync(path.resolve(__dirname, "..", "public", "muscle-rig.glb"));
    const arrayBuffer = buffer.buffer.slice(
      buffer.byteOffset,
      buffer.byteOffset + buffer.byteLength,
    ) as ArrayBuffer;
    const gltf = await new Promise<GLTF>((resolve, reject) => {
      new GLTFLoader().parse(arrayBuffer, "", resolve, reject);
    });
    model = prepareMuscleModel(gltf.scene);
    model.scene.updateMatrixWorld(true);
    rest = captureRestPose(model.bones);
    restPositions = {} as Record<BoneKey, THREE.Vector3>;
    for (const key of BONE_ORDER) restPositions[key] = worldPosition(model.bones[key]);
  });

  it("la pose neutre reproduit exactement la pose de repos (orientations et positions)", () => {
    pose({});

    for (const key of BONE_ORDER) {
      expect(worldQuaternion(model.bones[key]).angleTo(rest[key]), key).toBeLessThan(1e-6);
      expect(worldPosition(model.bones[key]).distanceTo(restPositions[key]), key).toBeLessThan(1e-6);
    }
  });

  it("garde le bras gauche en +x et le bras droit en -x en pose neutre (pas de miroir)", () => {
    pose({});

    expect(centreOf("L_upper_arm").x).toBeGreaterThan(0.1);
    expect(centreOf("R_upper_arm").x).toBeLessThan(-0.1);
  });

  for (const [name, angles] of Object.entries(POSES_TO_CHECK)) {
    it(`applique à chaque os la rotation attendue, parents compris : pose « ${name} »`, () => {
      pose(angles);

      const expected = boneDirections(angles);
      for (const key of BONE_ORDER) {
        if (key === "root") continue;
        // Rotation réellement appliquée à l'os par rapport à son repos, appliquée à sa
        // direction neutre (haut pour tronc et cou, bas pour les membres).
        const relative = worldQuaternion(model.bones[key]).multiply(rest[key].clone().invert());
        const neutral = new THREE.Vector3(0, UP_BONES.includes(key) ? 1 : -1, 0);
        const actual = neutral.applyQuaternion(relative);

        expect(actual.distanceTo(expected[key as AngleBoneKey]), `${name}/${key}`).toBeLessThan(1e-6);
      }
    });
  }

  it("bras droit croisé : le coude passe devant et vers le milieu du corps ; le bras gauche ne bouge pas", () => {
    pose({});
    const restLeft = centreOf("L_upper_arm");

    pose({ R_upper_arm: { flexion: 90, lateral: -45 }, R_forearm: { flexion: 90, lateral: -45 } });

    // Coude (origine de l'os de l'avant-bras) par rapport à l'épaule (origine de l'os du
    // bras). Au repos le bras pend vers le bas ; ici il est à peu près à l'horizontale
    // (le repos du modèle est légèrement écarté du corps, d'où l'écart de quelques degrés).
    const shoulder = worldPosition(model.bones.R_upper_arm);
    const elbow = worldPosition(model.bones.R_forearm);
    const upperArm = elbow.clone().sub(shoulder);
    expect(upperArm.z).toBeGreaterThan(0.1); // vers l'avant
    expect(upperArm.x).toBeGreaterThan(0.05); // vers le milieu du corps (+x pour le bras droit)
    expect(Math.abs(upperArm.y)).toBeLessThan(0.08); // à peu près horizontal
    expect(centreOf("L_upper_arm").distanceTo(restLeft)).toBeLessThan(1e-6);
  });

  it("inclinaison latérale positive du cou : vers la droite du sujet (-x)", () => {
    pose({});
    const neutral = centreOf("neck");

    pose({ neck: { lateral: 35 } });

    expect(centreOf("neck").x - neutral.x).toBeLessThan(-0.03);
  });

  it("flexion positive du tronc : le haut du corps passe vers l'avant (+z)", () => {
    pose({});
    const neck = centreOf("neck");
    const arm = centreOf("R_upper_arm");

    pose({ spine: { flexion: 40 } });

    expect(centreOf("neck").z - neck.z).toBeGreaterThan(0.1);
    expect(centreOf("R_upper_arm").z - arm.z).toBeGreaterThan(0.1);
    expect(centreOf("R_thigh").z).toBeCloseTo(-0.009, 1);
  });

  it("coude plié, bras levé devant : l'avant-bras est au-dessus de l'épaule", () => {
    pose({ R_upper_arm: { flexion: 90 }, R_forearm: { flexion: 180 } });

    expect(centreOf("R_forearm").y).toBeGreaterThan(centreOf("R_upper_arm").y);
  });

  it("revient exactement au repos après une pose extrême (aucun état résiduel)", () => {
    pose(POSES_TO_CHECK.everything);
    pose({});

    for (const key of BONE_ORDER) {
      expect(worldQuaternion(model.bones[key]).angleTo(rest[key]), key).toBeLessThan(1e-6);
      expect(worldPosition(model.bones[key]).distanceTo(restPositions[key]), key).toBeLessThan(1e-6);
    }
  });
});
