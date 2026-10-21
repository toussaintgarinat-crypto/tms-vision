import * as THREE from "three";

export type Pose3DLandmarks = Record<string, [number, number, number]>;

// 24 os, parent avant enfant. Même ordre et mêmes noms que `BONE_ORDER` dans
// tools/blender/rig_spec.py (à tenir synchronisés à la main). `fingers` regroupe les quatre
// doigts longs, `toes` les orteils ; le tronc reste un seul os `spine`.
export const BONE_ORDER = [
  "root",
  "spine",
  "neck",
  "head",
  "L_clavicle",
  "R_clavicle",
  "L_upper_arm",
  "R_upper_arm",
  "L_forearm",
  "R_forearm",
  "L_hand",
  "R_hand",
  "L_fingers",
  "R_fingers",
  "L_thumb",
  "R_thumb",
  "L_thigh",
  "R_thigh",
  "L_shin",
  "R_shin",
  "L_foot",
  "R_foot",
  "L_toes",
  "R_toes",
] as const;
export type BoneKey = (typeof BONE_ORDER)[number];

export const PARENT_OF: Record<Exclude<BoneKey, "root">, BoneKey> = {
  spine: "root",
  neck: "spine",
  head: "neck",
  L_clavicle: "spine",
  R_clavicle: "spine",
  L_upper_arm: "L_clavicle",
  R_upper_arm: "R_clavicle",
  L_forearm: "L_upper_arm",
  R_forearm: "R_upper_arm",
  L_hand: "L_forearm",
  R_hand: "R_forearm",
  L_fingers: "L_hand",
  R_fingers: "R_hand",
  L_thumb: "L_hand",
  R_thumb: "R_hand",
  L_thigh: "root",
  R_thigh: "root",
  L_shin: "L_thigh",
  R_shin: "R_thigh",
  L_foot: "L_shin",
  R_foot: "R_shin",
  L_toes: "L_foot",
  R_toes: "R_foot",
};

// Longueurs d'os fixes, en mètres (proportions humaines adultes approximatives),
// cohérentes avec l'échelle métrique des `pose_world_landmarks` MediaPipe dont
// provient `root.position`. Comme dans tout rig skinné classique, ces longueurs
// ne sont PAS recalculées par frame : seule la rotation des os est animée.
// `root` est un simple locateur de longueur nulle.
export const BONE_LENGTH: Record<BoneKey, number> = {
  root: 0,
  spine: 0.5,
  neck: 0.12,
  head: 0.16,
  L_clavicle: 0.15,
  R_clavicle: 0.15,
  L_upper_arm: 0.3,
  R_upper_arm: 0.3,
  L_forearm: 0.25,
  R_forearm: 0.25,
  L_hand: 0.09,
  R_hand: 0.09,
  L_fingers: 0.09,
  R_fingers: 0.09,
  L_thumb: 0.09,
  R_thumb: 0.09,
  L_thigh: 0.43,
  R_thigh: 0.43,
  L_shin: 0.35,
  R_shin: 0.35,
  L_foot: 0.13,
  R_foot: 0.13,
  L_toes: 0.055,
  R_toes: 0.055,
};

// Un os sans `from`/`to` n'a pas de point de repère dans MediaPipe Pose (clavicule, tête, doigts,
// orteils) : il suit son parent, dans sa position de repos par rapport à lui.
interface BoneSpec {
  parent: BoneKey;
  from?: readonly string[];
  to?: readonly string[];
}

// `from`/`to` : noms de landmarks moyennés pour obtenir les extrémités de
// l'os (utilisé par applyFrameToSkeleton, Task 2/3 de ce plan). Regroupés
// ici avec `parent` pour n'avoir qu'une seule table à maintenir.
const BONE_SPECS: Record<Exclude<BoneKey, "root">, BoneSpec> = {
  spine: { parent: "root", from: ["LEFT_HIP", "RIGHT_HIP"], to: ["LEFT_SHOULDER", "RIGHT_SHOULDER"] },
  neck: { parent: "spine", from: ["LEFT_SHOULDER", "RIGHT_SHOULDER"], to: ["NOSE"] },
  head: { parent: "neck" },
  L_clavicle: { parent: "spine" },
  R_clavicle: { parent: "spine" },
  L_upper_arm: { parent: "L_clavicle", from: ["LEFT_SHOULDER"], to: ["LEFT_ELBOW"] },
  R_upper_arm: { parent: "R_clavicle", from: ["RIGHT_SHOULDER"], to: ["RIGHT_ELBOW"] },
  L_forearm: { parent: "L_upper_arm", from: ["LEFT_ELBOW"], to: ["LEFT_WRIST"] },
  R_forearm: { parent: "R_upper_arm", from: ["RIGHT_ELBOW"], to: ["RIGHT_WRIST"] },
  L_hand: { parent: "L_forearm", from: ["LEFT_WRIST"], to: ["LEFT_INDEX", "LEFT_PINKY"] },
  R_hand: { parent: "R_forearm", from: ["RIGHT_WRIST"], to: ["RIGHT_INDEX", "RIGHT_PINKY"] },
  L_fingers: { parent: "L_hand" },
  R_fingers: { parent: "R_hand" },
  L_thumb: { parent: "L_hand", from: ["LEFT_WRIST"], to: ["LEFT_THUMB"] },
  R_thumb: { parent: "R_hand", from: ["RIGHT_WRIST"], to: ["RIGHT_THUMB"] },
  L_thigh: { parent: "root", from: ["LEFT_HIP"], to: ["LEFT_KNEE"] },
  R_thigh: { parent: "root", from: ["RIGHT_HIP"], to: ["RIGHT_KNEE"] },
  L_shin: { parent: "L_thigh", from: ["LEFT_KNEE"], to: ["LEFT_ANKLE"] },
  R_shin: { parent: "R_thigh", from: ["RIGHT_KNEE"], to: ["RIGHT_ANKLE"] },
  L_foot: { parent: "L_shin", from: ["LEFT_HEEL"], to: ["LEFT_FOOT_INDEX"] },
  R_foot: { parent: "R_shin", from: ["RIGHT_HEEL"], to: ["RIGHT_FOOT_INDEX"] },
  L_toes: { parent: "L_foot" },
  R_toes: { parent: "R_foot" },
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
    // La clavicule du squelette de test est un simple locateur : l'épaule reste au bout du tronc,
    // comme avant l'ajout de cet os (dans le vrai modèle, le décalage vient du fichier 3D).
    const offset = spec.parent.endsWith("_clavicle") ? 0 : BONE_LENGTH[spec.parent];
    bones[key].position.set(0, offset, 0);
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

// Échelle appliquée à un os dont le landmark n'a JAMAIS été détecté sur toute
// la vidéo (occultation en vue de profil, ex. LEFT_ELBOW/LEFT_KNEE) : on ne
// peut pas mettre 0 exactement (matrice non inversible pour le skinning),
// mais une échelle quasi nulle collapse visuellement le segment sans risque
// numérique.
const HIDDEN_SCALE = 1e-6;

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

    if (!spec.from || !spec.to) {
      // Pas de point de repère : l'os suit son parent dans sa position de repos (rotation
      // locale capturée au premier appel, avant toute pose).
      bone.userData.restQuaternion ??= bone.quaternion.clone();
      bone.scale.setScalar(1);
      bone.quaternion.copy(bone.userData.restQuaternion as THREE.Quaternion);
      worldQuatByBone[key] = parentWorldQuat.clone().multiply(bone.quaternion);
      continue;
    }

    const from = averageLandmark(merged, spec.from);
    const to = averageLandmark(merged, spec.to);

    if (from === null || to === null) {
      // Articulation jamais détectée sur toute la vidéo (occultée en vue de
      // profil, ex. LEFT_ELBOW/LEFT_KNEE sur une vidéo filmée de côté) : on
      // masque le segment via une échelle quasi nulle plutôt que de le laisser
      // figé en pose de repos — même principe que le masquage de capsule de la
      // Tranche 1 (commit c166cd0), adapté à un maillage skinné unique. Un bone
      // masqué masque aussi ses enfants (l'échelle se propage dans la
      // hiérarchie) : sans conséquence quand l'occlusion touche une seule
      // chaîne d'un même membre (ex. épaule+coude+poignet, tous dans la même
      // chaîne parent-enfant). Risque réel, non démontré : `spine` dépend des
      // DEUX hanches (cf. BONE_SPECS) alors que ses enfants `neck`,
      // `L_upper_arm` et `R_upper_arm` n'en dépendent pas — une vidéo future
      // qui n'exporterait jamais une seule hanche masquerait donc tout le haut
      // du corps (cou, deux bras, deux avant-bras, tête) via cette cascade. Pas
      // déclenché par `moi coupe.mp4` (les deux hanches y sont visibles en
      // continu) ; non corrigé ici.
      bone.scale.setScalar(HIDDEN_SCALE);
      worldQuatByBone[key] = parentWorldQuat.clone().multiply(bone.quaternion);
      continue;
    }
    bone.scale.setScalar(1);

    const direction = new THREE.Vector3().subVectors(to, from);

    if (direction.lengthSq() > 1e-8) {
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
