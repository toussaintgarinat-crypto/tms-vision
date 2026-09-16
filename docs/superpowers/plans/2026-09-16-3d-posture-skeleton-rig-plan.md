# Avatar 3D de posture — Tranche 2 (squelette articulé) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le rig "10 capsules indépendantes" de la Tranche 1 par un vrai squelette
articulé (`THREE.Bone`/`THREE.Skeleton`) piloté par les mêmes données `pose3d.json`, et prouver que
le skinning fonctionne avec un maillage de test non anatomique — fondation nécessaire pour intégrer
de vrais muscles Z-Anatomy à la tranche suivante.

**Architecture:** Un nouveau module pur `web/app/pose3dSkeleton.ts` construit la hiérarchie d'os
(racine = milieu des hanches ; chaîne spine→neck ; bras gauche/droit ; cuisses gauche/droite) et
calcule, à chaque frame, la rotation locale de chaque os à partir des positions de landmarks 3D déjà
exportées par le backend (aucun changement backend). Un second module pur
`web/app/testSkinnedGeometry.ts` construit un maillage de test (cylindres + une sphère pour la tête,
fusionnés en une seule géométrie skinnée). `PostureAvatar3D.tsx` assemble les deux dans un
`THREE.SkinnedMesh` lié au squelette, remplaçant l'ancien rendu par capsules indépendantes.

**Tech Stack:** TypeScript, Three.js 0.186.0, @react-three/fiber 9.7.0, @react-three/drei 10.7.8
(inchangés), Vitest (nouveau, pour les deux modules purs — première suite de tests automatisée dans
`web/`).

## Global Constraints

- Aucun changement backend dans cette tranche (spec, section "Décisions de cadrage").
- Mêmes 10 paires de landmarks que la Tranche 1 (`overlay.py::_SKELETON_CONNECTIONS`), réorganisées
  en hiérarchie de 8 os + racine — pas de nouveaux points de tracking (spec).
- Roll/torsion de chaque os non calculé — laissé à sa valeur de repos (identité), documenté comme
  limite connue plutôt que résolu (spec).
- Poids de peau du maillage de test : 100% sur l'os le plus proche par vertex, pas de blending aux
  jointures (spec).
- Nouvelles dépendances npm épinglées en version exacte (pas de `^`), cohérent avec la correction
  appliquée pendant la revue de la Tranche 1 (commit `95fb2e7`, voir `.superpowers/sdd/progress.md`).
- Pas de changement visuel majeur attendu par rapport à la Tranche 1 — silhouette générale similaire
  (spec, "Décisions de cadrage").

---

## Task 1: Squelette — hiérarchie d'os (`buildSkeleton`)

**Files:**
- Create: `web/app/pose3dSkeleton.ts`
- Create: `web/app/pose3dSkeleton.test.ts`
- Create: `web/vitest.config.ts`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `export type Pose3DLandmarks = Record<string, [number, number, number]>`
- Produces: `export const BONE_ORDER: readonly ["root", "spine", "neck", "L_upper_arm", "L_forearm", "R_upper_arm", "R_forearm", "L_thigh", "R_thigh"]`
- Produces: `export type BoneKey = (typeof BONE_ORDER)[number]`
- Produces: `export const BIND_LENGTH: number`
- Produces: `export interface SkeletonRig { skeleton: THREE.Skeleton; bones: Record<BoneKey, THREE.Bone> }`
- Produces: `export function buildSkeleton(): SkeletonRig`

- [ ] **Step 1: Installer Vitest**

Éditer `web/package.json` :

```json
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint",
    "test": "vitest run"
  },
```

Ajouter dans `devDependencies` (ordre alphabétique, cohérent avec le fichier existant) :

```json
    "vitest": "3.2.4",
```

Run: `cd "web" && npm install`
Expected: `vitest@3.2.4` installé, `package-lock.json` mis à jour, aucune erreur.

- [ ] **Step 2: Config Vitest**

Créer `web/vitest.config.ts` :

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
  },
});
```

- [ ] **Step 3: Écrire le test qui échoue**

Créer `web/app/pose3dSkeleton.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import { BONE_ORDER, buildSkeleton } from "./pose3dSkeleton";

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
```

- [ ] **Step 4: Lancer le test, vérifier qu'il échoue**

Run: `cd "web" && npx vitest run app/pose3dSkeleton.test.ts`
Expected: FAIL — `pose3dSkeleton.ts` n'existe pas encore (`Cannot find module './pose3dSkeleton'`).

- [ ] **Step 5: Implémentation minimale**

Créer `web/app/pose3dSkeleton.ts` :

```ts
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

export const BIND_LENGTH = 1;

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
    bones[key].position.set(0, BIND_LENGTH, 0);
  }
  const skeleton = new THREE.Skeleton(BONE_ORDER.map((key) => bones[key]));
  return { skeleton, bones };
}
```

- [ ] **Step 6: Lancer le test, vérifier qu'il passe**

Run: `cd "web" && npx vitest run app/pose3dSkeleton.test.ts`
Expected: PASS (1 test).

- [ ] **Step 7: Vérifier que le reste du projet compile toujours**

Run: `cd "web" && npx tsc --noEmit`
Expected: aucune erreur (le fichier n'est encore importé nulle part ailleurs, donc pas de régression
possible, mais on vérifie que le nouveau fichier lui-même est valide TypeScript).

- [ ] **Step 8: Commit**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts web/app/pose3dSkeleton.ts web/app/pose3dSkeleton.test.ts
git commit -m "feat: squelette articulé de l'avatar 3D — hiérarchie d'os (buildSkeleton)"
```

---

## Task 2: Squelette — rotations par frame, cas simple (`applyFrameToSkeleton`)

**Files:**
- Modify: `web/app/pose3dSkeleton.ts`
- Modify: `web/app/pose3dSkeleton.test.ts`

**Interfaces:**
- Consumes: `BONE_ORDER`, `BoneKey`, `BIND_LENGTH`, `SkeletonRig`, `buildSkeleton()` (Task 1)
- Produces: `export function applyFrameToSkeleton(bones: Record<BoneKey, THREE.Bone>, landmarks: Pose3DLandmarks, lastKnownLandmarks: Partial<Pose3DLandmarks>): void`

- [ ] **Step 1: Écrire le test qui échoue**

Remplacer la ligne d'import existante en haut de `web/app/pose3dSkeleton.test.ts` (celle qui importe
`BONE_ORDER, buildSkeleton`) par :

```ts
import * as THREE from "three";
import { applyFrameToSkeleton, BONE_ORDER, buildSkeleton, Pose3DLandmarks } from "./pose3dSkeleton";
```

Puis ajouter à la fin du fichier (après le `describe("buildSkeleton", ...)` existant) :

```ts
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
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd "web" && npx vitest run app/pose3dSkeleton.test.ts`
Expected: FAIL — `applyFrameToSkeleton` n'est pas exporté par `pose3dSkeleton.ts`.

- [ ] **Step 3: Implémentation minimale**

Ajouter à la fin de `web/app/pose3dSkeleton.ts` :

```ts
const UP = new THREE.Vector3(0, 1, 0);

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
      const desiredWorldQuat = new THREE.Quaternion().setFromUnitVectors(UP, direction);
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
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd "web" && npx vitest run app/pose3dSkeleton.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add web/app/pose3dSkeleton.ts web/app/pose3dSkeleton.test.ts
git commit -m "feat: calcule les rotations du squelette par frame (applyFrameToSkeleton)"
```

---

## Task 3: Squelette — landmarks manquants et os de longueur nulle

**Files:**
- Modify: `web/app/pose3dSkeleton.test.ts`

(Aucune modification de `pose3dSkeleton.ts` n'est attendue dans cette tâche si Task 2 est
implémentée correctement — ces tests vérifient un comportement déjà écrit. S'ils échouent, corriger
`applyFrameToSkeleton` dans `web/app/pose3dSkeleton.ts` avant de continuer.)

**Interfaces:**
- Consumes: `applyFrameToSkeleton`, `buildSkeleton`, `Pose3DLandmarks` (Task 1/2)

- [ ] **Step 1: Écrire les tests**

Ajouter à `web/app/pose3dSkeleton.test.ts` :

```ts
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
```

- [ ] **Step 2: Lancer les tests**

Run: `cd "web" && npx vitest run app/pose3dSkeleton.test.ts`
Expected: PASS (4 tests). Si un test échoue, relire la Step 3 de la Task 2 : la branche `else` de
`applyFrameToSkeleton` doit laisser `bone.quaternion` inchangé et propager
`parentWorldQuat.clone().multiply(bone.quaternion)` pour les enfants.

- [ ] **Step 3: Commit**

```bash
git add web/app/pose3dSkeleton.test.ts
git commit -m "test: couvre les landmarks manquants et les os de longueur nulle du squelette"
```

---

## Task 4: Maillage de test skinné (`buildTestSkinnedGeometry`)

**Files:**
- Create: `web/app/testSkinnedGeometry.ts`
- Create: `web/app/testSkinnedGeometry.test.ts`

**Interfaces:**
- Consumes: `BONE_ORDER`, `BoneKey`, `BIND_LENGTH` (Task 1)
- Produces: `export function buildTestSkinnedGeometry(): THREE.BufferGeometry` (avec attributs
  `position`, `normal`, `skinIndex` (Uint16, 4 par vertex), `skinWeight` (Float32, 4 par vertex),
  et un index de triangles)

- [ ] **Step 1: Écrire le test qui échoue**

Créer `web/app/testSkinnedGeometry.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { BONE_ORDER } from "./pose3dSkeleton";
import { buildTestSkinnedGeometry } from "./testSkinnedGeometry";

describe("buildTestSkinnedGeometry", () => {
  it("assigne un poids de peau de 1 sur un seul os, pour chaque vertex", () => {
    const geometry = buildTestSkinnedGeometry();
    const skinWeight = geometry.attributes.skinWeight;
    const skinIndex = geometry.attributes.skinIndex;

    expect(skinWeight.count).toBeGreaterThan(0);
    for (let i = 0; i < skinWeight.count; i++) {
      expect(skinWeight.getX(i)).toBe(1);
      expect(skinWeight.getY(i)).toBe(0);
      expect(skinWeight.getZ(i)).toBe(0);
      expect(skinWeight.getW(i)).toBe(0);
      expect(skinIndex.getX(i)).toBeGreaterThanOrEqual(0);
      expect(skinIndex.getX(i)).toBeLessThan(BONE_ORDER.length);
    }
  });

  it("produit une géométrie indexée non vide", () => {
    const geometry = buildTestSkinnedGeometry();
    expect(geometry.attributes.position.count).toBeGreaterThan(0);
    expect(geometry.index).not.toBeNull();
    expect((geometry.index as THREE.BufferAttribute).count).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd "web" && npx vitest run app/testSkinnedGeometry.test.ts`
Expected: FAIL — `testSkinnedGeometry.ts` n'existe pas encore.

- [ ] **Step 3: Implémentation**

Créer `web/app/testSkinnedGeometry.ts` :

```ts
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
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd "web" && npx vitest run app/testSkinnedGeometry.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Lancer toute la suite Vitest**

Run: `cd "web" && npx vitest run`
Expected: PASS (6 tests au total : 4 de `pose3dSkeleton.test.ts` + 2 de `testSkinnedGeometry.test.ts`).

- [ ] **Step 6: Commit**

```bash
git add web/app/testSkinnedGeometry.ts web/app/testSkinnedGeometry.test.ts
git commit -m "feat: maillage de test skinné pour valider le squelette articulé"
```

---

## Task 5: Brancher le squelette et le maillage skinné dans `PostureAvatar3D`

**Files:**
- Modify: `web/app/PostureAvatar3D.tsx`

**Interfaces:**
- Consumes: `applyFrameToSkeleton`, `buildSkeleton`, `Pose3DLandmarks` (`web/app/pose3dSkeleton.ts`),
  `buildTestSkinnedGeometry` (`web/app/testSkinnedGeometry.ts`)

- [ ] **Step 1: Remplacer le contenu du fichier**

Remplacer entièrement `web/app/PostureAvatar3D.tsx` par :

```tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { applyFrameToSkeleton, buildSkeleton, Pose3DLandmarks } from "./pose3dSkeleton";
import { buildTestSkinnedGeometry } from "./testSkinnedGeometry";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Même palette que src/tms_vision/overlay.py::_COLOR_BY_LEVEL (converti BGR -> hex RGB).
const ACTION_LEVEL_COLORS: Record<string, string> = {
  acceptable: "#4CAF50",
  investigation_recommandee: "#EBD23C",
  investigation_et_changement_bientot: "#EB9628",
  changement_immediat: "#D23232",
};
const DEFAULT_COLOR = "#9E9E9E";

type Pose3DFrame = {
  frame_index: number;
  timestamp_seconds: number;
  detected: boolean;
  landmarks: Pose3DLandmarks | null;
  action_level: string | null;
};

function findNearestFrameIndex(frames: Pose3DFrame[], time: number): number {
  let low = 0;
  let high = frames.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (frames[mid].timestamp_seconds < time) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  if (
    low > 0 &&
    Math.abs(frames[low - 1].timestamp_seconds - time) <=
      Math.abs(frames[low].timestamp_seconds - time)
  ) {
    return low - 1;
  }
  return low;
}

function Rig({
  frames,
  videoRef,
}: {
  frames: Pose3DFrame[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const rig = useMemo(() => {
    const { skeleton, bones } = buildSkeleton();
    const geometry = buildTestSkinnedGeometry();
    const material = new THREE.MeshStandardMaterial({ color: DEFAULT_COLOR });
    const mesh = new THREE.SkinnedMesh(geometry, material);
    mesh.add(bones.root);
    mesh.bind(skeleton);
    mesh.visible = false;
    return { mesh, bones, material };
  }, []);

  const lastKnownLandmarksRef = useRef<Partial<Pose3DLandmarks>>({});
  const lastKnownColorRef = useRef<string>(DEFAULT_COLOR);
  const hasDetectedOnceRef = useRef(false);

  useFrame(() => {
    const video = videoRef.current;
    if (!video || frames.length === 0) return;

    const index = findNearestFrameIndex(frames, video.currentTime);
    const frame = frames[index];

    if (frame.landmarks) {
      applyFrameToSkeleton(rig.bones, frame.landmarks, lastKnownLandmarksRef.current);
      hasDetectedOnceRef.current = true;
      rig.mesh.visible = true;
      // `action_level` peut être null même quand une pose est détectée (les
      // angles RULA n'ont pas pu être calculés cette frame-là) : dans ce cas
      // on conserve la dernière couleur connue plutôt que de retomber sur le
      // gris par défaut (même principe qu'en Tranche 1).
      if (frame.action_level) {
        lastKnownColorRef.current = ACTION_LEVEL_COLORS[frame.action_level] ?? DEFAULT_COLOR;
      }
    }

    if (!hasDetectedOnceRef.current) return;
    rig.material.color.set(lastKnownColorRef.current);
  });

  return <primitive object={rig.mesh} />;
}

export function PostureAvatar3D({
  pose3dUrl,
  videoRef,
}: {
  pose3dUrl: string;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const [frames, setFrames] = useState<Pose3DFrame[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setFrames(null);
    setError(null);
    fetch(`${API_URL}${pose3dUrl}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<Pose3DFrame[]>;
      })
      .then((data) => {
        if (!cancelled) setFrames(data);
      })
      .catch(() => {
        if (!cancelled) setError("Impossible de charger les données de posture 3D.");
      });
    return () => {
      cancelled = true;
    };
  }, [pose3dUrl]);

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (!frames) {
    return <p className="text-sm text-gray-500">Chargement de l&apos;avatar 3D...</p>;
  }
  if (!frames.some((frame) => frame.landmarks !== null)) {
    // `detected` signifie "angles RULA calculables", pas "pose détectée" :
    // une vidéo où MediaPipe trouve une pose sur chaque frame mais où le
    // calcul d'angles échoue systématiquement a quand même un track 3D
    // exploitable (même critère qu'en Tranche 1).
    return <p className="text-sm text-gray-500">Aucune posture détectée sur cette vidéo.</p>;
  }

  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg bg-gray-900">
      <Canvas camera={{ position: [0, 0, 2.5], fov: 50 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[2, 2, 2]} intensity={0.8} />
        <Rig frames={frames} videoRef={videoRef} />
        <OrbitControls target={[0, 0, 0]} />
      </Canvas>
    </div>
  );
}
```

- [ ] **Step 2: Vérifier la compilation TypeScript**

Run: `cd "web" && npx tsc --noEmit`
Expected: aucune erreur.

- [ ] **Step 3: Vérifier le lint**

Run: `cd "web" && npm run lint`
Expected: aucune erreur (avertissements pré-existants sans rapport avec ce fichier acceptables).

- [ ] **Step 4: Vérifier que le build de production passe**

Run: `cd "web" && npm run build`
Expected: build réussi, sans erreur.

- [ ] **Step 5: Relancer la suite Vitest (non-régression)**

Run: `cd "web" && npx vitest run`
Expected: PASS (6 tests, inchangé — ce fichier n'a pas de test dédié, voir Task 6 pour la
vérification manuelle).

- [ ] **Step 6: Commit**

```bash
git add web/app/PostureAvatar3D.tsx
git commit -m "feat: rend l'avatar 3D avec le squelette articulé et un maillage skinné de test"
```

---

## Task 6: Vérification manuelle et documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: l'application complète (API FastAPI + frontend Next.js)

- [ ] **Step 1: Démarrer les deux serveurs**

Terminal 1 :
```bash
cd "/Users/garinat_t/Desktop/TMS vision" && PYTHONPATH=src venv/bin/uvicorn tms_vision.api:app --reload --port 8000
```

Terminal 2 :
```bash
cd "/Users/garinat_t/Desktop/TMS vision/web" && npm run dev
```

- [ ] **Step 2: Vérifier sur une vraie vidéo avec le squelette articulé**

Utiliser Playwright (skill `playwright-skill`) pour : ouvrir `http://localhost:3000`, importer
`.playwright-mcp/moi coupe.mp4` (bouton "Importer une vidéo"), remplir le formulaire, lancer
l'analyse, puis une fois le résultat affiché :
- Vérifier que le maillage 3D suit la posture en synchro avec la lecture vidéo (pas de figeage, pas
  de saut).
- Vérifier l'absence de distorsion aberrante aux jointures (coude, épaule) en observant le maillage
  sous plusieurs angles de caméra (glisser la souris pour tourner avec `OrbitControls`) — aucun
  vertex qui s'étire de façon disproportionnée.
- Comparer visuellement à la Tranche 1 (capture d'écran ou souvenir du rendu précédent) pour
  confirmer l'absence de régression de fidélité perçue (silhouette générale similaire, cohérent
  avec la spec).
- Mettre la vidéo en pause à `t=0` avant toute détection : confirmer que le maillage reste invisible
  (pas de mannequin fantôme à l'origine), reproduisant la vérification faite en Tranche 1 pour ce
  même bug (commit `c166cd0`).
- Vérifier dans la console du navigateur l'absence d'erreur.

- [ ] **Step 3: Vérifier le fallback "aucune détection"**

Importer `samples/synthetic_smoke_test.mp4` (vidéo sans personne). Vérifier que le message
"Aucune posture détectée sur cette vidéo." s'affiche, sans erreur console.

- [ ] **Step 4: Mettre à jour le README**

Dans `README.md`, section "8. Feuille de Route de Déploiement", ajouter une entrée juste après le
bloc "Avatar 3D de posture, Tranche 1" (avant "#### Reste à faire pour la suite de la Phase 2") :

```markdown
#### ✅ Avatar 3D de posture, Tranche 2 (squelette articulé + preuve de skinning) — TERMINÉE

- **Contexte** : la Tranche 1 positionnait chaque capsule indépendamment (pas de hiérarchie), ce qui
  ne permet aucun skinning. Un vrai skinning de muscles (tranche future) exige un squelette
  articulé — c'est l'unique objet de cette tranche, sans changement visuel majeur attendu (silhouette
  générale similaire à la Tranche 1).
- **`web/app/pose3dSkeleton.ts`** (nouveau, module pur) : construit une hiérarchie de 8 os + racine
  (`THREE.Bone`/`THREE.Skeleton`) à partir des mêmes landmarks 3D que la Tranche 1, et calcule à
  chaque frame la rotation locale de chaque os par rapport à son parent. Roll/torsion de chaque os
  non calculé (limite connue des données MediaPipe, qui ne donnent que des positions).
- **`web/app/testSkinnedGeometry.ts`** (nouveau, module pur) : construit un maillage de test non
  anatomique (cylindres + une sphère pour la tête, poids de peau 100% par os) pour valider le
  mécanisme de skinning avant d'intégrer les vrais muscles.
- **`web/app/PostureAvatar3D.tsx`** : rend désormais un unique `THREE.SkinnedMesh` lié au squelette,
  à la place des 10 capsules indépendantes de la Tranche 1.
- **Première suite de tests automatisée dans `web/`** (Vitest, 6 tests) : hiérarchie du squelette,
  calcul des rotations sur une pose de référence, comportement sur landmarks manquants/os dégénéré,
  attributs du maillage de test.
- **Vérifié manuellement (2026-09-16)** sur `moi coupe.mp4` : le maillage suit la posture en synchro,
  pas de distorsion aberrante aux jointures, pas de mannequin fantôme avant la première détection,
  fallback "aucune posture détectée" toujours correct sur `synthetic_smoke_test.mp4`.
- **Ce qui n'est pas dans cette tranche** : vrais maillages musculaires Z-Anatomy, recherche sur leur
  riggabilité réelle — Tranche 3 (voir spec
  `docs/superpowers/specs/2026-09-16-3d-posture-skeleton-rig-design.md`).
```

Et mettre à jour la liste des documents de référence en haut de la section 8 pour ajouter :
```markdown
- `docs/superpowers/specs/2026-09-16-3d-posture-skeleton-rig-design.md` — la spec de la tranche 2 de
  l'avatar 3D de posture (squelette articulé + preuve de skinning).
- `docs/superpowers/plans/2026-09-16-3d-posture-skeleton-rig-plan.md` — le plan d'implémentation de
  cette tranche.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: valide la tranche 2 de l'avatar 3D (squelette articulé) sur une vraie vidéo"
```
