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
  Region,
  boneDirections,
  captureRestPose,
  neutralDirection,
  rotationFor,
  samplePose,
  withBasePose,
} from "./exercisePose";
import { MuscleModel, prepareMuscleModel } from "./muscleModel";
import { resolveMeshRouting } from "./muscleSegments";
import { BONE_ORDER, BoneKey } from "./pose3dSkeleton";


// Angle entre deux rotations, précis même pour de très petits angles (`angleTo` perd toute
// précision près de zéro : acos d'un produit scalaire voisin de 1).
function rotationAngle(a: THREE.Quaternion, b: THREE.Quaternion): number {
  const delta = a.clone().multiply(b.clone().invert());
  return 2 * Math.atan2(Math.hypot(delta.x, delta.y, delta.z), Math.abs(delta.w));
}

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
    const side = (wanted: "left" | "right") =>
      meshes.filter(({ mesh }) => {
        const routing = resolveMeshRouting(mesh);
        return routing.region === "upper_arm" && routing.side === wanted;
      });
    const left = side("left");
    const right = side("right");

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
    expectDirection(directions.head, 0, 1, 0);
    for (const bone of [
      "L_upper_arm", "R_upper_arm", "L_forearm", "R_forearm", "L_hand", "R_hand",
      "L_fingers", "R_fingers", "L_thumb", "R_thumb", "L_thigh", "R_thigh", "L_shin", "R_shin",
    ] as const) {
      expectDirection(directions[bone], 0, -1, 0);
    }
    expectDirection(directions.L_clavicle, 1, 0, 0);
    expectDirection(directions.R_clavicle, -1, 0, 0);
    for (const bone of ["L_foot", "R_foot", "L_toes", "R_toes"] as const) {
      expectDirection(directions[bone], 0, 0, 1);
    }
  });

  it("flexion positive : l'extrémité de l'os va vers l'avant (+z), pour tous les os", () => {
    const trunk = boneDirections({ spine: { flexion: 90 } });
    const limbs = boneDirections({
      R_upper_arm: { flexion: 90 },
      L_upper_arm: { flexion: 90 },
      R_thigh: { flexion: 90 },
    });

    expectDirection(trunk.spine, 0, 0, 1);
    expectDirection(limbs.R_upper_arm, 0, 0, 1);
    expectDirection(limbs.L_upper_arm, 0, 0, 1);
    expectDirection(limbs.R_thigh, 0, 0, 1);
    // Le cou et la tête, sans angle propre, suivent le tronc.
    expectDirection(trunk.neck, 0, 0, 1);
    expectDirection(trunk.head, 0, 0, 1);
  });

  it("les angles sont relatifs au parent : un os sans angle suit son parent", () => {
    const raised = boneDirections({ R_upper_arm: { flexion: 90 } });

    // L'avant-bras, la main, les doigts et le pouce prolongent le bras levé devant.
    for (const bone of ["R_forearm", "R_hand", "R_fingers", "R_thumb"] as const) {
      expectDirection(raised[bone], 0, 0, 1);
    }
    // Le bras gauche n'est pas concerné.
    expectDirection(raised.L_forearm, 0, -1, 0);
  });

  it("un angle d'avant-bras se compose avec celui du bras (coude plié à 90° sur un bras levé)", () => {
    const bent = boneDirections({ R_upper_arm: { flexion: 90 }, R_forearm: { flexion: 90 } });

    // Bras horizontal vers l'avant, avant-bras tourné de 90° de plus : vers le haut.
    expectDirection(bent.R_forearm, 0, 1, 0);
  });

  it("flexion de la tête et du poignet par rapport à leur parent", () => {
    const bent = boneDirections({ neck: { flexion: 20 }, head: { flexion: 10 }, L_hand: { flexion: 45 } });

    const headAngle = THREE.MathUtils.degToRad(30);
    expectDirection(bent.head, 0, Math.cos(headAngle), Math.sin(headAngle));
    expectDirection(
      bent.L_hand,
      0,
      -Math.cos(THREE.MathUtils.degToRad(45)),
      Math.sin(THREE.MathUtils.degToRad(45)),
    );
  });

  it("flexion positive du pied : flexion dorsale, les orteils vont vers le haut", () => {
    const dorsiflexed = boneDirections({ L_foot: { flexion: 30 } });
    const angle = THREE.MathUtils.degToRad(30);

    expectDirection(dorsiflexed.L_foot, 0, Math.sin(angle), Math.cos(angle));
    expectDirection(dorsiflexed.L_toes, 0, Math.sin(angle), Math.cos(angle));
  });

  it("élévation de la clavicule : lateral positif lève l'épaule des deux côtés", () => {
    const shrugged = boneDirections({ L_clavicle: { lateral: 20 }, R_clavicle: { lateral: 20 } });
    const angle = THREE.MathUtils.degToRad(20);

    expectDirection(shrugged.L_clavicle, Math.cos(angle), Math.sin(angle), 0);
    expectDirection(shrugged.R_clavicle, -Math.cos(angle), Math.sin(angle), 0);
    // Les bras suivent la clavicule : levée autour de l'articulation sterno-claviculaire, la
    // ceinture scapulaire écarte légèrement le bras qui pend.
    expect(shrugged.L_upper_arm.x).toBeGreaterThan(0);
    expect(shrugged.R_upper_arm.x).toBeLessThan(0);
  });

  it("flexion de la hanche ou du genou : le bas de la jambe suit la cuisse", () => {
    const bent = boneDirections({ L_thigh: { flexion: 90 }, L_shin: { flexion: -90 } });

    expectDirection(bent.L_thigh, 0, 0, 1);
    // Genou fléchi : le bas de la jambe revient vers le bas, comme au repos.
    expectDirection(bent.L_shin, 0, -1, 0);
  });

  it("flexion négative : vers l'arrière (extension)", () => {
    const extended = boneDirections({ spine: { flexion: -90 } });
    const armBack = boneDirections({ L_upper_arm: { flexion: -90 } });

    expectDirection(extended.spine, 0, 0, -1);
    expectDirection(armBack.L_upper_arm, 0, 0, -1);
  });

  it("lateral positif sur le tronc et le cou : vers la droite du sujet (-x)", () => {
    const tilted = boneDirections({ neck: { lateral: 35 } });
    const trunkTilted = boneDirections({ spine: { lateral: 90 } });

    expectDirection(trunkTilted.spine, -1, 0, 0);
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

  it("twist : rotation vers la droite du sujet (tronc, cou, tête), externe pour les os pairés", () => {
    const front = new THREE.Vector3(0, 0, 1);
    const turned = (bone: AngleBoneKey) =>
      front.clone().applyQuaternion(rotationFor(bone, { twist: 90 }));

    // Vers la droite du sujet = -x.
    expectDirection(turned("neck"), -1, 0, 0);
    expectDirection(turned("head"), -1, 0, 0);
    expectDirection(turned("spine"), -1, 0, 0);
    // Rotation externe : le devant de l'os tourne vers l'extérieur du corps.
    expectDirection(turned("L_upper_arm"), 1, 0, 0);
    expectDirection(turned("R_upper_arm"), -1, 0, 0);
    expectDirection(turned("L_forearm"), 1, 0, 0);
    expectDirection(turned("R_thigh"), -1, 0, 0);
  });

  it("twist ne change pas la direction d'un os vertical", () => {
    const twisted = boneDirections({ neck: { twist: 60 }, R_forearm: { twist: -40 } });

    expectDirection(twisted.neck, 0, 1, 0);
    expectDirection(twisted.R_forearm, 0, -1, 0);
  });

  it("retourne des vecteurs unitaires", () => {
    const directions = boneDirections({
      spine: { flexion: 33, lateral: -12 },
      L_upper_arm: { flexion: 140, lateral: 55 },
      R_forearm: { flexion: -20, lateral: 170 },
      head: { flexion: 12, twist: 30 },
      L_hand: { flexion: -40, lateral: 15, twist: 20 },
      R_foot: { flexion: 25, lateral: 5 },
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

const POSES_TO_CHECK: Record<string, PoseAngles> = {
  neutral: {},
  neck_tilt: { neck: { lateral: 35 } },
  head_turn: { neck: { twist: 20 }, head: { twist: 40, flexion: 10 } },
  trunk_forward: { spine: { flexion: 40 } },
  trunk_back: { spine: { flexion: -15 } },
  shoulder_cross: { R_upper_arm: { flexion: 90, lateral: -45 } },
  elbow_bent: { L_upper_arm: { flexion: 90 }, L_forearm: { flexion: 90 } },
  wrist_bent: { L_upper_arm: { flexion: 90 }, L_hand: { flexion: -60 }, L_fingers: { flexion: -30 } },
  shoulder_shrug: { L_clavicle: { lateral: 15 }, R_clavicle: { lateral: 15, twist: 10 } },
  knee_bent: { R_thigh: { flexion: 80 }, R_shin: { flexion: -90 }, R_foot: { flexion: 20 } },
  everything: {
    spine: { flexion: 25, lateral: -10, twist: 15 },
    neck: { flexion: 15, lateral: 20, twist: -10 },
    head: { flexion: -10, lateral: 5, twist: 25 },
    L_clavicle: { lateral: 10, twist: 5 },
    L_upper_arm: { flexion: 60, lateral: 30, twist: 20 },
    L_forearm: { flexion: 100, twist: -30 },
    L_hand: { flexion: 20, lateral: 10 },
    L_fingers: { flexion: 40 },
    L_thumb: { flexion: 20, lateral: 30 },
    R_upper_arm: { flexion: -20, lateral: 70 },
    R_forearm: { flexion: 45, lateral: -30 },
    R_hand: { flexion: -15 },
    L_thigh: { flexion: 20, lateral: 10, twist: 10 },
    L_shin: { flexion: -40 },
    L_foot: { flexion: 15, twist: 10 },
    L_toes: { flexion: 25 },
    R_thigh: { flexion: -10, lateral: 15 },
    R_shin: { flexion: -20 },
    R_foot: { flexion: -20, lateral: 8 },
  },
};

describe("applyPoseToSkeleton sur le vrai squelette (web/public/muscle-rig.glb)", () => {
  let model: MuscleModel;
  let rest: ReturnType<typeof captureRestPose>;
  let restPositions: Record<BoneKey, THREE.Vector3>;

  const worldQuaternion = (bone: THREE.Bone) => bone.getWorldQuaternion(new THREE.Quaternion());
  const worldPosition = (bone: THREE.Bone) => bone.getWorldPosition(new THREE.Vector3());

  // Centre (monde) des maillages d'une région (et d'un côté), squelette à jour.
  function centreOf(region: Region, side: "left" | "right" | null = null): THREE.Vector3 {
    model.scene.updateMatrixWorld(true);
    const centre = new THREE.Vector3();
    let count = 0;
    model.meshes.forEach((mesh) => {
      const routing = resolveMeshRouting(mesh);
      if (routing.region !== region || (side !== null && routing.side !== side)) return;
      mesh.skeleton.update();
      mesh.computeBoundingBox();
      centre.add(mesh.boundingBox!.clone().applyMatrix4(mesh.matrixWorld).getCenter(new THREE.Vector3()));
      count++;
    });
    expect(count, `aucun muscle pour ${region}/${side}`).toBeGreaterThan(0);
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
      expect(rotationAngle(worldQuaternion(model.bones[key]), rest[key]), key).toBeLessThan(1e-5);
      expect(worldPosition(model.bones[key]).distanceTo(restPositions[key]), key).toBeLessThan(1e-5);
    }
  });

  it("garde le bras gauche en +x et le bras droit en -x en pose neutre (pas de miroir)", () => {
    pose({});

    expect(centreOf("upper_arm", "left").x).toBeGreaterThan(0.1);
    expect(centreOf("upper_arm", "right").x).toBeLessThan(-0.1);
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
        const actual = neutralDirection(key as AngleBoneKey).applyQuaternion(relative);

        expect(actual.distanceTo(expected[key as AngleBoneKey]), `${name}/${key}`).toBeLessThan(1e-5);
      }
    });
  }

  it("bras droit croisé : le coude passe devant et vers le milieu du corps ; le bras gauche ne bouge pas", () => {
    pose({});
    const restLeft = centreOf("upper_arm", "left");

    pose({ R_upper_arm: { flexion: 90, lateral: -45 } });

    // Coude (origine de l'os de l'avant-bras) par rapport à l'épaule (origine de l'os du
    // bras). Au repos le bras pend vers le bas ; ici il est à peu près à l'horizontale
    // (le repos du modèle est légèrement écarté du corps, d'où l'écart de quelques degrés).
    const shoulder = worldPosition(model.bones.R_upper_arm);
    const elbow = worldPosition(model.bones.R_forearm);
    const upperArm = elbow.clone().sub(shoulder);
    expect(upperArm.z).toBeGreaterThan(0.1); // vers l'avant
    expect(upperArm.x).toBeGreaterThan(0.05); // vers le milieu du corps (+x pour le bras droit)
    expect(Math.abs(upperArm.y)).toBeLessThan(0.08); // à peu près horizontal
    expect(centreOf("upper_arm", "left").distanceTo(restLeft)).toBeLessThan(1e-6);
  });

  it("inclinaison latérale positive du cou : vers la droite du sujet (-x)", () => {
    pose({});
    const neutral = centreOf("neck");
    const neutralHead = centreOf("head");

    pose({ neck: { lateral: 35 } });

    expect(centreOf("neck").x - neutral.x).toBeLessThan(-0.02);
    // La tête, sans angle propre, suit le cou.
    expect(centreOf("head").x - neutralHead.x).toBeLessThan(-0.02);
  });

  it("flexion positive du tronc : le haut du corps passe vers l'avant (+z)", () => {
    pose({});
    const neck = centreOf("neck");
    const arm = centreOf("upper_arm", "right");
    const thigh = centreOf("thigh", "right");

    pose({ spine: { flexion: 40 } });

    expect(centreOf("neck").z - neck.z).toBeGreaterThan(0.1);
    expect(centreOf("upper_arm", "right").z - arm.z).toBeGreaterThan(0.1);
    // Le bassin et les jambes ne bougent pas.
    expect(centreOf("thigh", "right").distanceTo(thigh)).toBeLessThan(1e-3);
  });

  it("coude plié, bras levé devant : l'avant-bras est au-dessus de l'épaule", () => {
    pose({ R_upper_arm: { flexion: 90 }, R_forearm: { flexion: 90 } });

    expect(centreOf("lower_arm", "right").y).toBeGreaterThan(centreOf("upper_arm", "right").y);
  });

  it("revient exactement au repos après une pose extrême (aucun état résiduel)", () => {
    pose(POSES_TO_CHECK.everything);
    pose({});

    for (const key of BONE_ORDER) {
      expect(rotationAngle(worldQuaternion(model.bones[key]), rest[key]), key).toBeLessThan(1e-5);
      expect(worldPosition(model.bones[key]).distanceTo(restPositions[key]), key).toBeLessThan(1e-5);
    }
  });
});

describe("withBasePose", () => {
  it("leaves a standing pose unchanged", () => {
    const pose = { neck: { lateral: 30 } };
    expect(withBasePose(undefined, pose)).toEqual(pose);
    expect(withBasePose("standing", pose)).toEqual(pose);
    expect(withBasePose("lying", pose)).toEqual(pose);
  });

  it("starts a seated pose from the sitting position and adds the exercise angles", () => {
    const seated = withBasePose("seated", { neck: { lateral: 30 }, R_shin: { flexion: 90 } });
    expect(seated.neck).toEqual({ lateral: 30 });
    expect(seated.R_thigh).toEqual({ flexion: 90, lateral: 0, twist: 0 });
    expect(seated.L_shin).toEqual({ flexion: -90, lateral: 0, twist: 0 });
    // Genou tendu : -90 (assis) + 90 (exercice) = 0, jambe dans le prolongement de la cuisse.
    expect(seated.R_shin?.flexion).toBe(0);
  });

  it("puts the thighs horizontal and the shins vertical when seated", () => {
    const directions = boneDirections(withBasePose("seated", {}));
    expect(directions.R_thigh.z).toBeCloseTo(1, 5);
    expect(directions.R_shin.y).toBeCloseTo(-1, 5);
  });
});
