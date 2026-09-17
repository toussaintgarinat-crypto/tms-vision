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

// Longueurs d'os fixes, en mètres (proportions humaines adultes approximatives),
// cohérentes avec l'échelle métrique des `pose_world_landmarks` MediaPipe dont
// provient `root.position`. Comme dans tout rig skinné classique, ces longueurs
// ne sont PAS recalculées par frame : seule la rotation des os est animée.
// `root` est un simple locateur de longueur nulle.
export const BONE_LENGTH: Record<BoneKey, number> = {
  root: 0,
  spine: 0.5,
  neck: 0.25,
  L_upper_arm: 0.3,
  L_forearm: 0.25,
  R_upper_arm: 0.3,
  R_forearm: 0.25,
  L_thigh: 0.45,
  R_thigh: 0.45,
};

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
    // L'origine d'un os se place au bout de son parent : le décalage est donc
    // la longueur DU PARENT (0 pour les enfants de `root`, qui est un locateur).
    bones[key].position.set(0, BONE_LENGTH[spec.parent], 0);
  }
  const skeleton = new THREE.Skeleton(BONE_ORDER.map((key) => bones[key]));
  return { skeleton, bones };
}

// `THREE.Quaternion.setFromUnitVectors(UP, direction)` contient une branche
// discontinue quand `direction` est quasi antiparallèle à `UP` — exactement le
// cas d'un bras ou d'une cuisse qui pend à la verticale : le roll de l'os
// bascule alors de ~180° d'une frame à l'autre sur un simple bruit de capteur.
// On construit donc explicitement une base orthonormée à partir d'un axe de
// référence stable. Un champ de repères totalement continu sur toutes les
// directions est impossible (théorème de la boule chevelue) : cette
// construction ne fait que déplacer la discontinuité de ±UP vers ±Z (l'axe de
// profondeur de la caméra dans la convention MediaPipe), un cas beaucoup plus
// rare pour un membre humain filmé de profil ou de face. Elle reste possible
// (un membre pointant droit vers/depuis la caméra) : un flip de roll de
// ~90° sur une frame de bruit peut encore s'y produire.
// TODO : à revisiter si la Tranche 3 (vrais maillages musculaires) rend ce
// flip résiduel visible.
const STABLE_REFERENCE = new THREE.Vector3(0, 0, 1);
const FALLBACK_REFERENCE = new THREE.Vector3(1, 0, 0);

// `direction` doit déjà être normalisé. Les deux références étant orthogonales,
// au plus une des deux peut être quasi parallèle à `direction` : le produit
// vectoriel qui construit `xAxis` ne dégénère jamais.
function swingQuaternion(direction: THREE.Vector3): THREE.Quaternion {
  const reference =
    Math.abs(direction.dot(STABLE_REFERENCE)) > 0.99 ? FALLBACK_REFERENCE : STABLE_REFERENCE;
  const xAxis = new THREE.Vector3().crossVectors(reference, direction).normalize();
  const zAxis = new THREE.Vector3().crossVectors(xAxis, direction).normalize();
  const matrix = new THREE.Matrix4().makeBasis(xAxis, direction, zAxis);
  return new THREE.Quaternion().setFromRotationMatrix(matrix);
}

function toThreeVector(coords: readonly [number, number, number]): THREE.Vector3 {
  // MediaPipe pose_world_landmarks : x droite, y vers le bas, origine au
  // centre des hanches. Three.js est y-vers-le-haut : on inverse y. Même
  // convention que la Tranche 1 (vérifiée visuellement sur une vraie vidéo).
  const [x, y, z] = coords;
  return new THREE.Vector3(x, -y, z);
}

function averageLandmark(
  landmarks: Pose3DLandmarks,
  names: readonly string[]
): THREE.Vector3 | null {
  const vectors: THREE.Vector3[] = [];
  for (const name of names) {
    const coords = landmarks[name];
    if (!coords) return null;
    vectors.push(toThreeVector(coords));
  }
  const sum = vectors.reduce((acc, vector) => acc.add(vector), new THREE.Vector3());
  return sum.multiplyScalar(1 / vectors.length);
}

export function applyFrameToSkeleton(
  bones: Record<BoneKey, THREE.Bone>,
  landmarks: Pose3DLandmarks,
  lastKnownLandmarks: Partial<Pose3DLandmarks>
): void {
  for (const name of Object.keys(landmarks)) {
    lastKnownLandmarks[name] = landmarks[name];
  }
  const merged = lastKnownLandmarks as Pose3DLandmarks;

  const rootPosition = averageLandmark(merged, ROOT_LANDMARKS);
  if (rootPosition) {
    bones.root.position.copy(rootPosition);
  }

  const worldQuatByBone: Partial<Record<BoneKey, THREE.Quaternion>> = {
    root: new THREE.Quaternion(),
  };

  for (const key of BONE_ORDER) {
    if (key === "root") continue;
    const spec = BONE_SPECS[key];
    const bone = bones[key];
    const parentWorldQuat = worldQuatByBone[spec.parent]!;

    const from = averageLandmark(merged, spec.from);
    const to = averageLandmark(merged, spec.to);
    const direction = from && to ? new THREE.Vector3().subVectors(to, from) : null;

    if (direction && direction.lengthSq() > 1e-8) {
      direction.normalize();
      const desiredWorldQuat = swingQuaternion(direction);
      bone.quaternion.copy(parentWorldQuat.clone().invert().multiply(desiredWorldQuat));
      worldQuatByBone[key] = desiredWorldQuat;
    } else {
      // Landmarks manquants ou os de longueur quasi nulle cette frame : on
      // conserve la rotation locale actuelle plutôt que de la remettre à
      // zéro ou de produire une direction indéfinie.
      worldQuatByBone[key] = parentWorldQuat.clone().multiply(bone.quaternion);
    }
  }
}
