# Avatar 3D — Tranche 4 (coloration par segment anatomique) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la teinte uniforme appliquée à tous les muscles de l'avatar 3D (Tranche 3) par une coloration par segment anatomique — cou, tronc, bras et avant-bras du côté analysé prennent chacun la couleur de leur propre sous-score RULA, déjà calculé mais jusqu'ici jeté avant d'atteindre le frontend.

**Architecture:** Côté backend, `RulaScore` (déjà calculé à chaque frame) alimente un nouveau champ additif `segment_action_levels` sur `Pose3DFrameRecord`, sérialisé dans `pose3d.json` ; `side` (le côté analysé) est ajouté à la réponse JSON de `POST /analyses` existante, pas à `pose3d.json`. Côté frontend, un nouveau module pur `web/app/muscleSegments.ts` détermine, pour chaque `SkinnedMesh` du `.glb` déjà chargé, son os dominant (par sommation de `skinWeight`) puis son segment RULA via une table statique de 9 entrées (une par os) — pas de duplication de noms de muscles. `PostureAvatar3D.tsx` utilise ce routage pour colorer chaque muscle indépendamment : par son segment si celui-ci est pertinent pour le côté analysé, en gris fixe si c'est le bras/avant-bras du côté non analysé, ou par la teinte globale existante pour les cuisses (comportement Tranche 3 inchangé).

**Tech Stack:** Python (FastAPI, dataclasses), TypeScript/React (Three.js, @react-three/fiber, @react-three/drei), Vitest (frontend), pytest (backend) — inchangés depuis les tranches précédentes.

## Global Constraints

- Seuls le cou, le tronc, le bras et l'avant-bras sont colorés par segment ; les cuisses gardent la teinte uniforme du `action_level` global, inchangée depuis la Tranche 3 (spec, "Décisions de cadrage").
- Sur le bras/avant-bras, seul le côté effectivement analysé (`side`) est coloré par son sous-score ; le côté non analysé reste en permanence à la teinte neutre grise fixe (`#9E9E9E`, `DEFAULT_COLOR` existant) — jamais la couleur globale, jamais une donnée inventée (spec).
- Les sous-scores RULA sont mappés à une couleur via la fonction `action_level()` existante, réutilisée telle quelle (mêmes seuils absolus `<=2`/`<=4`/`<=6`/`7+`) — pas de normalisation proportionnelle par segment (spec).
- `pose3d.json` reste un tableau de frames : `segment_action_levels` est un champ additif par frame, pas de changement de forme/wrapper (spec).
- `side` est ajouté à la réponse JSON de `POST /analyses`/`.../complete` (déjà en paramètre de `_analyze_and_build_response`), pas à `pose3d.json`, et lu côté frontend depuis `result.side` (la réponse stockée), jamais depuis l'état local du formulaire (spec — évite une désynchronisation si l'utilisateur change le sélecteur après affichage d'un résultat).
- Pas de nouvelle table de noms de muscles Z-Anatomy côté TypeScript : le mapping muscle → segment passe par l'os dominant du skinning déjà présent dans `muscle-rig.glb`, via une table `BoneKey -> segment` de 9 entrées (spec).
- `wrist`, `wrist_twist`, `muscle_use_score`, `force_load_score`, `legs` ne sont pas exposés au frontend (aucun muscle du rig actuel ne leur correspond, spec "Hors périmètre").

---

## Task 1: Backend — `Pose3DFrameRecord` gagne `segment_action_levels`

**Files:**
- Modify: `src/tms_vision/pose3d_export.py`
- Modify: `tests/test_pose3d_export.py`

**Interfaces:**
- Produces: `Pose3DFrameRecord.segment_action_levels: dict[str, str] | None` (nouveau champ du dataclass existant)
- Produces: `write_pose3d_json` sérialise ce champ tel quel dans chaque entrée JSON sous la clé `"segment_action_levels"`

- [ ] **Step 1: Écrire le test qui échoue**

Dans `tests/test_pose3d_export.py`, remplacer la fonction `test_write_pose3d_json_writes_one_entry_per_frame` (lignes 48-65) par :

```python
def test_write_pose3d_json_writes_one_entry_per_frame(tmp_path):
    path = tmp_path / "pose3d.json"
    records = [
        Pose3DFrameRecord(
            0,
            0.0,
            True,
            {"NOSE": Landmark(0.1, 0.2, 0.3, 0.9)},
            "acceptable",
            {"neck": "acceptable", "trunk": "investigation_recommandee", "upper_arm": "acceptable", "lower_arm": "acceptable"},
        ),
        Pose3DFrameRecord(1, 1.0, False, None, None, None),
    ]

    write_pose3d_json(str(path), records)

    data = json.loads(path.read_text())
    assert len(data) == 2
    assert data[0]["frame_index"] == 0
    assert data[0]["detected"] is True
    assert data[0]["landmarks"]["NOSE"] == [0.1, 0.2, 0.3]
    assert data[0]["action_level"] == "acceptable"
    assert data[0]["segment_action_levels"] == {
        "neck": "acceptable",
        "trunk": "investigation_recommandee",
        "upper_arm": "acceptable",
        "lower_arm": "acceptable",
    }
    assert data[1]["landmarks"] is None
    assert data[1]["action_level"] is None
    assert data[1]["segment_action_levels"] is None
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `venv/bin/pytest tests/test_pose3d_export.py::test_write_pose3d_json_writes_one_entry_per_frame -v`
Expected: FAIL — `TypeError: Pose3DFrameRecord.__init__() takes 6 positional arguments but 7 were given` (le dataclass n'a pas encore le nouveau champ).

- [ ] **Step 3: Implémentation minimale**

Dans `src/tms_vision/pose3d_export.py`, remplacer le dataclass (lignes 13-19) :

```python
@dataclass
class Pose3DFrameRecord:
    frame_index: int
    timestamp_seconds: float
    detected: bool
    landmarks: dict[str, Landmark] | None
    action_level: str | None
    segment_action_levels: dict[str, str] | None
```

Puis, dans `write_pose3d_json` (le bloc `payload.append(...)`, actuellement lignes 63-71), ajouter la clé :

```python
        payload.append(
            {
                "frame_index": record.frame_index,
                "timestamp_seconds": record.timestamp_seconds,
                "detected": record.detected,
                "landmarks": landmarks,
                "action_level": record.action_level,
                "segment_action_levels": record.segment_action_levels,
            }
        )
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `venv/bin/pytest tests/test_pose3d_export.py -v`
Expected: PASS (tous les tests du fichier, y compris les 3 tests de `smooth_world_landmarks` inchangés).

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/pose3d_export.py tests/test_pose3d_export.py
git commit -m "feat: Pose3DFrameRecord gagne segment_action_levels (tranche 4)"
```

---

## Task 2: Backend — le pipeline calcule et propage `segment_action_levels`

**Files:**
- Modify: `src/tms_vision/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Pose3DFrameRecord.segment_action_levels` (Task 1), `RulaScore.neck/trunk/upper_arm/lower_arm` (existant, `src/tms_vision/rula/scoring.py:104-120`), `action_level()` (existant, `scoring.py:94-101`)

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `tests/test_pipeline.py`, modifier `test_analyze_video_produces_pose3d_json` (lignes 165-187) pour ajouter une assertion dans la boucle finale :

```python
    for entry in data:
        assert entry["detected"] is False
        assert entry["landmarks"] is None
        assert entry["action_level"] is None
        assert entry["segment_action_levels"] is None
```

Puis, dans `test_analyze_video_pose3d_json_key_set_varies_per_frame_when_landmark_occluded` (boucle finale, lignes 291-298), ajouter :

```python
    for entry in data:
        assert entry["detected"] is True
        assert entry["landmarks"] is not None
        assert entry["action_level"] is not None
        assert entry["segment_action_levels"] is not None
        assert set(entry["segment_action_levels"].keys()) == {"neck", "trunk", "upper_arm", "lower_arm"}
        valid_levels = {
            "acceptable",
            "investigation_recommandee",
            "investigation_et_changement_bientot",
            "changement_immediat",
        }
        for level in entry["segment_action_levels"].values():
            assert level in valid_levels
        for name, coords in entry["landmarks"].items():
            assert isinstance(coords, list)
            assert len(coords) == 3
            assert all(isinstance(v, float) for v in coords)
```

(Cette dernière assertion remplace la boucle `for name, coords in entry["landmarks"].items(): ...` existante en fin de fonction — la garder, seulement ajoutée après les nouvelles assertions sur `segment_action_levels`.)

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `venv/bin/pytest tests/test_pipeline.py -v -k pose3d_json`
Expected: FAIL — `KeyError: 'segment_action_levels'` (le champ n'est pas encore construit par `analyze_video`).

- [ ] **Step 3: Implémentation minimale**

Dans `src/tms_vision/pipeline.py`, étendre l'import existant (ligne 18) :

```python
from tms_vision.rula.scoring import action_level, compute_rula_score, detect_muscle_use
```

Puis, dans la boucle de construction des `pose3d_records` (actuellement lignes 133-158), juste après le calcul de `score` et avant `annotated = draw_overlay(...)`, ajouter le calcul du nouveau champ et le passer au `Pose3DFrameRecord` :

```python
    for (frame, pose_result, angles), world_landmarks in zip(per_frame_angles, smoothed_world_landmarks):
        score = None
        if angles is not None:
            score = compute_rula_score(
                angles, wrist_twist=wrist_twist_code, load_kg=load_kg, muscle_use_score=muscle_use_score
            )
        segment_action_levels = None
        if score is not None:
            segment_action_levels = {
                "neck": action_level(score.neck),
                "trunk": action_level(score.trunk),
                "upper_arm": action_level(score.upper_arm),
                "lower_arm": action_level(score.lower_arm),
            }
        annotated = draw_overlay(frame.image, pose_result.landmarks, score)
        writer.write(annotated)
        exporter.add_frame(
            FrameRecord(
                frame_index=frame.index,
                timestamp_seconds=frame.timestamp_seconds,
                detected=angles is not None,
                angles=angles,
                score=score,
            )
        )
        pose3d_records.append(
            Pose3DFrameRecord(
                frame_index=frame.index,
                timestamp_seconds=frame.timestamp_seconds,
                detected=angles is not None,
                landmarks=world_landmarks,
                action_level=score.action_level if score is not None else None,
                segment_action_levels=segment_action_levels,
            )
        )
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `venv/bin/pytest tests/test_pipeline.py -v`
Expected: PASS (tous les tests du fichier).

- [ ] **Step 5: Lancer toute la suite backend (non-régression)**

Run: `venv/bin/pytest -q`
Expected: PASS, aucune régression sur les autres modules (`scoring`, `api`, `angles`, etc.).

- [ ] **Step 6: Commit**

```bash
git add src/tms_vision/pipeline.py tests/test_pipeline.py
git commit -m "feat: le pipeline calcule segment_action_levels par frame (tranche 4)"
```

---

## Task 3: Backend — l'API expose `side` dans la réponse d'analyse

**Files:**
- Modify: `src/tms_vision/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: la réponse JSON de `POST /analyses` et `POST /uploads/{id}/complete` gagne une clé `"side": "left" | "right"`

- [ ] **Step 1: Écrire le test qui échoue**

Dans `tests/test_api.py`, modifier `test_create_analysis_with_no_detectable_person_returns_empty_summary` (lignes 19-39) pour ajouter à la fin :

```python
    assert body["pose3d_url"].startswith("/outputs/")
    assert body["side"] == "right"
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `venv/bin/pytest tests/test_api.py::test_create_analysis_with_no_detectable_person_returns_empty_summary -v`
Expected: FAIL — `KeyError: 'side'`.

- [ ] **Step 3: Implémentation minimale**

Dans `src/tms_vision/api.py`, modifier le `return` de `_analyze_and_build_response` (lignes 116-122) :

```python
    summary = json.loads(result.summary_json_path.read_text())
    return {
        "summary": summary,
        "annotated_video_url": f"/outputs/{result.video_path.name}",
        "csv_url": f"/outputs/{result.csv_path.name}",
        "pose3d_url": f"/outputs/{result.pose3d_path.name}",
        "side": side,
    }
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `venv/bin/pytest tests/test_api.py -v`
Expected: PASS (tous les tests du fichier, y compris ceux de l'upload chunké qui passent aussi par `_analyze_and_build_response`).

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/api.py tests/test_api.py
git commit -m "feat: expose le côté analysé (side) dans la réponse d'analyse (tranche 4)"
```

---

## Task 4: Frontend — module pur `muscleSegments.ts`

**Files:**
- Create: `web/app/muscleSegments.ts`
- Create: `web/app/muscleSegments.test.ts`

**Interfaces:**
- Consumes: `BONE_ORDER`, `BoneKey`, `buildSkeleton` (`web/app/pose3dSkeleton.ts`, existant)
- Produces: `export type RulaSegment = "neck" | "trunk" | "upper_arm" | "lower_arm"`
- Produces: `export const RULA_SEGMENTS: readonly RulaSegment[]`
- Produces: `export const SEGMENT_BY_BONE: Record<BoneKey, RulaSegment | null>`
- Produces: `export function sideOfBone(boneKey: BoneKey): "left" | "right" | null`
- Produces: `export function dominantBoneIndex(skinIndex: THREE.BufferAttribute, skinWeight: THREE.BufferAttribute): number`
- Produces: `export function resolveMeshBoneKey(mesh: THREE.SkinnedMesh): BoneKey`
- Produces: `export interface MeshSegmentRouting { segment: RulaSegment | null; side: "left" | "right" | null }`
- Produces: `export function resolveMeshRouting(mesh: THREE.SkinnedMesh): MeshSegmentRouting`

- [ ] **Step 1: Écrire le test qui échoue**

Créer `web/app/muscleSegments.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { BoneKey, BONE_ORDER, buildSkeleton } from "./pose3dSkeleton";
import {
  dominantBoneIndex,
  resolveMeshBoneKey,
  resolveMeshRouting,
  SEGMENT_BY_BONE,
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

describe("SEGMENT_BY_BONE / sideOfBone", () => {
  it("mappe chaque os sur son segment RULA (ou null si non applicable)", () => {
    expect(SEGMENT_BY_BONE.spine).toBe("trunk");
    expect(SEGMENT_BY_BONE.neck).toBe("neck");
    expect(SEGMENT_BY_BONE.L_upper_arm).toBe("upper_arm");
    expect(SEGMENT_BY_BONE.R_upper_arm).toBe("upper_arm");
    expect(SEGMENT_BY_BONE.L_forearm).toBe("lower_arm");
    expect(SEGMENT_BY_BONE.R_forearm).toBe("lower_arm");
    expect(SEGMENT_BY_BONE.L_thigh).toBeNull();
    expect(SEGMENT_BY_BONE.R_thigh).toBeNull();
    expect(SEGMENT_BY_BONE.root).toBeNull();
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
    expect(resolveMeshRouting(mesh)).toEqual({ segment: "lower_arm", side: "left" });
  });

  it("retourne un segment null pour un os sans segment RULA (cuisse), sans côté pertinent", () => {
    const mesh = buildSingleVertexMesh("R_thigh");
    expect(resolveMeshRouting(mesh)).toEqual({ segment: null, side: "right" });
  });

  it("ne signale aucun côté pour le tronc (os unique, sans variante gauche/droite)", () => {
    const mesh = buildSingleVertexMesh("spine");
    expect(resolveMeshRouting(mesh)).toEqual({ segment: "trunk", side: null });
  });
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd "web" && npx vitest run app/muscleSegments.test.ts`
Expected: FAIL — `Cannot find module './muscleSegments'`.

- [ ] **Step 3: Implémentation**

Créer `web/app/muscleSegments.ts` :

```ts
import * as THREE from "three";
import { BoneKey } from "./pose3dSkeleton";

export type RulaSegment = "neck" | "trunk" | "upper_arm" | "lower_arm";

export const RULA_SEGMENTS: readonly RulaSegment[] = ["neck", "trunk", "upper_arm", "lower_arm"];

// Un seul os "logique" domine chaque muscle de ce rig (voir Tranche 3 : tronc/
// cou/cuisse en poids rigide déterministe -- 100% sur un seul os -- et
// bras/avant-bras via Automatic Weights mais toujours dominés par un seul des
// deux os possibles) : mapper l'os dominant d'un SkinnedMesh sur son segment
// RULA suffit, pas besoin de connaître le nom du muscle Z-Anatomy lui-même.
export const SEGMENT_BY_BONE: Record<BoneKey, RulaSegment | null> = {
  root: null,
  spine: "trunk",
  neck: "neck",
  L_upper_arm: "upper_arm",
  R_upper_arm: "upper_arm",
  L_forearm: "lower_arm",
  R_forearm: "lower_arm",
  L_thigh: null,
  R_thigh: null,
};

export function sideOfBone(boneKey: BoneKey): "left" | "right" | null {
  if (boneKey.startsWith("L_")) return "left";
  if (boneKey.startsWith("R_")) return "right";
  return null;
}

export function dominantBoneIndex(
  skinIndex: THREE.BufferAttribute,
  skinWeight: THREE.BufferAttribute
): number {
  const totalWeightByBoneIndex = new Map<number, number>();
  for (let vertex = 0; vertex < skinIndex.count; vertex++) {
    const indices = [
      skinIndex.getX(vertex),
      skinIndex.getY(vertex),
      skinIndex.getZ(vertex),
      skinIndex.getW(vertex),
    ];
    const weights = [
      skinWeight.getX(vertex),
      skinWeight.getY(vertex),
      skinWeight.getZ(vertex),
      skinWeight.getW(vertex),
    ];
    for (let slot = 0; slot < 4; slot++) {
      const weight = weights[slot];
      if (weight <= 0) continue;
      const boneIndex = indices[slot];
      totalWeightByBoneIndex.set(boneIndex, (totalWeightByBoneIndex.get(boneIndex) ?? 0) + weight);
    }
  }

  let bestBoneIndex = -1;
  let bestTotal = -Infinity;
  for (const [boneIndex, total] of totalWeightByBoneIndex) {
    if (total > bestTotal) {
      bestTotal = total;
      bestBoneIndex = boneIndex;
    }
  }
  if (bestBoneIndex === -1) {
    throw new Error("Aucun poids de peau non nul trouvé sur ce maillage.");
  }
  return bestBoneIndex;
}

export function resolveMeshBoneKey(mesh: THREE.SkinnedMesh): BoneKey {
  const skinIndex = mesh.geometry.attributes.skinIndex as THREE.BufferAttribute;
  const skinWeight = mesh.geometry.attributes.skinWeight as THREE.BufferAttribute;
  const boneIndex = dominantBoneIndex(skinIndex, skinWeight);
  const bone = mesh.skeleton.bones[boneIndex];
  if (!bone) {
    throw new Error(`Index d'os ${boneIndex} hors limites du squelette (mesh "${mesh.name}").`);
  }
  return bone.name as BoneKey;
}

export interface MeshSegmentRouting {
  segment: RulaSegment | null;
  side: "left" | "right" | null;
}

export function resolveMeshRouting(mesh: THREE.SkinnedMesh): MeshSegmentRouting {
  const boneKey = resolveMeshBoneKey(mesh);
  return { segment: SEGMENT_BY_BONE[boneKey] ?? null, side: sideOfBone(boneKey) };
}
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd "web" && npx vitest run app/muscleSegments.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 5: Vérifier la compilation TypeScript**

Run: `cd "web" && npx tsc --noEmit`
Expected: aucune erreur.

- [ ] **Step 6: Lancer toute la suite Vitest (non-régression)**

Run: `cd "web" && npx vitest run`
Expected: PASS (tous les tests existants + les 7 nouveaux).

- [ ] **Step 7: Commit**

```bash
git add web/app/muscleSegments.ts web/app/muscleSegments.test.ts
git commit -m "feat: résout le segment RULA d'un muscle par son os dominant (tranche 4)"
```

---

## Task 5: Frontend — coloration par segment dans `PostureAvatar3D.tsx` et `page.tsx`

**Files:**
- Modify: `web/app/PostureAvatar3D.tsx`
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: `resolveMeshRouting`, `RulaSegment`, `RULA_SEGMENTS` (`web/app/muscleSegments.ts`, Task 4)

(Ces deux fichiers doivent être modifiés ensemble : `PostureAvatar3D` gagne une prop `side` obligatoire, et `page.tsx` est son seul appelant — la compilation TypeScript échoue si l'un est modifié sans l'autre.)

- [ ] **Step 1: Remplacer le contenu de `PostureAvatar3D.tsx`**

Remplacer entièrement `web/app/PostureAvatar3D.tsx` par :

```tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import { applyFrameToSkeleton, BONE_ORDER, BoneKey, Pose3DLandmarks } from "./pose3dSkeleton";
import { resolveMeshRouting, RULA_SEGMENTS, RulaSegment } from "./muscleSegments";

const MUSCLE_RIG_URL = "/muscle-rig.glb";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Même palette que src/tms_vision/overlay.py::_COLOR_BY_LEVEL (converti BGR -> hex RGB).
const ACTION_LEVEL_COLORS: Record<string, string> = {
  acceptable: "#4CAF50",
  investigation_recommandee: "#EBD23C",
  investigation_et_changement_bientot: "#EB9628",
  changement_immediat: "#D23232",
};
const DEFAULT_COLOR = "#9E9E9E";

export type Side = "left" | "right";

type Pose3DFrame = {
  frame_index: number;
  timestamp_seconds: number;
  detected: boolean;
  landmarks: Pose3DLandmarks | null;
  action_level: string | null;
  segment_action_levels: Record<string, string> | null;
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
  side,
}: {
  frames: Pose3DFrame[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
  side: Side;
}) {
  const gltf = useGLTF(MUSCLE_RIG_URL);

  // `useGLTF` mémoïse et partage `gltf.scene` entre tous les composants qui
  // chargent la même URL. Le traiter comme un template en clonant une copie
  // dédiée à ce montage (via SkeletonUtils.clone, qui préserve correctement
  // les liaisons squelette/SkinnedMesh, contrairement à Object3D.clone) :
  // sans cela, muter `mesh.material` directement sur la scène partagée
  // provoque une désynchronisation entre l'objet réellement affiché et
  // celui mis à jour par la boucle de coloration ci-dessous dès que le
  // composant est monté plus d'une fois sur la session (ex. Strict Mode en
  // dev, ou plusieurs analyses successives).
  const scene = useMemo(() => cloneSkeleton(gltf.scene), [gltf]);

  const skinnedMeshes = useMemo(() => {
    const meshes: THREE.SkinnedMesh[] = [];
    scene.traverse((object) => {
      if ((object as THREE.SkinnedMesh).isSkinnedMesh) {
        meshes.push(object as THREE.SkinnedMesh);
      }
    });
    return meshes;
  }, [scene]);

  // Résolu une seule fois par mesh : le skinning (skinIndex/skinWeight) est
  // figé après le chargement du .glb, il ne dépend ni de la frame ni du côté
  // analysé (`side` n'intervient que dans la boucle useFrame ci-dessous, pour
  // décider QUELLE couleur appliquer, pas quel segment un mesh représente).
  const meshRouting = useMemo(
    () => skinnedMeshes.map((mesh) => resolveMeshRouting(mesh)),
    [skinnedMeshes]
  );

  const bones = useMemo(() => {
    const skeleton = skinnedMeshes[0]?.skeleton;
    if (!skeleton) {
      throw new Error("muscle-rig.glb ne contient aucun SkinnedMesh.");
    }
    const map = {} as Record<BoneKey, THREE.Bone>;
    for (const key of BONE_ORDER) {
      const bone = skeleton.bones.find((candidate) => candidate.name === key);
      if (!bone) {
        throw new Error(`Os "${key}" introuvable dans le squelette importé (muscle-rig.glb).`);
      }
      map[key] = bone;
    }
    return map;
  }, [skinnedMeshes]);

  // Cloner les matériaux importés plutôt que les muter directement : évite
  // de modifier l'asset source partagé (mémoïsé par useGLTF) si le
  // composant est démonté/remonté. `useMemo` doit rester pur (spec React) :
  // la création des clones se fait ici, mais leur AFFECTATION à
  // `mesh.material` est déportée dans un useEffect ci-dessous plutôt que
  // faite ici en tant qu'effet de bord pendant le rendu.
  const clonedMaterials = useMemo(() => {
    return skinnedMeshes.map((mesh) => {
      const source = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
      const clone = (source as THREE.MeshStandardMaterial).clone();
      // Les matériaux Z-Anatomy exportés portent un emissiveFactor blanc
      // (1,1,1) sans texture d'émission. À pleine intensité, ce terme
      // émissif s'ajoute au rendu indépendamment de `color` et sature
      // l'image en blanc, ce qui rend invisible toute teinte appliquée
      // ci-dessous. On neutralise l'émissif pour que la teinte reste visible.
      clone.emissive.set(0x000000);
      return clone;
    });
  }, [skinnedMeshes]);

  // Affecter les clones aux meshes dans un effet (pas pendant le rendu) :
  // en Strict Mode (dev), React invoque deux fois le corps du composant
  // (et donc les initialiseurs `useMemo`) pour détecter les effets de bord
  // impurs. Un `useEffect` s'exécute après le commit et réaffecte les mêmes
  // références de façon idempotente.
  useEffect(() => {
    skinnedMeshes.forEach((mesh, index) => {
      mesh.material = clonedMaterials[index];
      // Three.js calcule la bounding sphere d'un SkinnedMesh une seule fois
      // (à partir de la géométrie en bind pose) et ne la recalcule jamais
      // lorsque les os bougent via `applyFrameToSkeleton` (boucle useFrame
      // ci-dessous). Sans désactiver le frustum culling, un membre qui
      // s'écarte largement de sa pose de repos peut disparaître à tort.
      mesh.frustumCulled = false;
    });
  }, [skinnedMeshes, clonedMaterials]);

  const groupRef = useRef<THREE.Group>(null);
  const lastKnownLandmarksRef = useRef<Partial<Pose3DLandmarks>>({});
  // Une couleur "dernière connue" par segment RULA, plus une entrée "global"
  // pour la teinte uniforme dont dépendent encore les cuisses (segment ===
  // null). Chaque entrée n'est mise à jour, frame après frame, que si sa
  // propre donnée source (segment_action_levels[segment] ou action_level)
  // est présente cette frame-là -- même principe de repli qu'avant cette
  // tranche (Tranches 1-3), simplement répété par segment au lieu d'un seul
  // ref partagé.
  const lastKnownColorsRef = useRef<Record<RulaSegment | "global", string>>({
    neck: DEFAULT_COLOR,
    trunk: DEFAULT_COLOR,
    upper_arm: DEFAULT_COLOR,
    lower_arm: DEFAULT_COLOR,
    global: DEFAULT_COLOR,
  });
  const hasDetectedOnceRef = useRef(false);

  useFrame(() => {
    const video = videoRef.current;
    const group = groupRef.current;
    if (!video || !group || frames.length === 0) return;

    const index = findNearestFrameIndex(frames, video.currentTime);
    const frame = frames[index];

    if (frame.landmarks) {
      applyFrameToSkeleton(bones, frame.landmarks, lastKnownLandmarksRef.current);
      hasDetectedOnceRef.current = true;
      group.visible = true;
      if (frame.action_level) {
        lastKnownColorsRef.current.global = ACTION_LEVEL_COLORS[frame.action_level] ?? DEFAULT_COLOR;
      }
      if (frame.segment_action_levels) {
        for (const segment of RULA_SEGMENTS) {
          const level = frame.segment_action_levels[segment];
          if (level) {
            lastKnownColorsRef.current[segment] = ACTION_LEVEL_COLORS[level] ?? DEFAULT_COLOR;
          }
        }
      }
    }

    if (!hasDetectedOnceRef.current) return;
    clonedMaterials.forEach((material, materialIndex) => {
      const routing = meshRouting[materialIndex];
      if (routing.segment === null) {
        // Cuisses (ou tout mesh sans segment RULA) : teinte uniforme
        // globale, comportement Tranche 3 inchangé.
        material.color.set(lastKnownColorsRef.current.global);
        return;
      }
      if (routing.side !== null && routing.side !== side) {
        // Bras/avant-bras du côté NON analysé : aucune donnée mesurée pour
        // ce côté, teinte neutre fixe en permanence.
        material.color.set(DEFAULT_COLOR);
        return;
      }
      material.color.set(lastKnownColorsRef.current[routing.segment]);
    });
  });

  return (
    <group ref={groupRef} visible={false}>
      <primitive object={scene} />
    </group>
  );
}

useGLTF.preload(MUSCLE_RIG_URL);

export function PostureAvatar3D({
  pose3dUrl,
  videoRef,
  side,
}: {
  pose3dUrl: string;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  side: Side;
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
    return <p className="text-sm text-gray-500">Aucune posture détectée sur cette vidéo.</p>;
  }

  return (
    <div className="w-full">
      <div className="aspect-video w-full overflow-hidden rounded-lg bg-gray-900">
        <Canvas camera={{ position: [0, 0, 2.5], fov: 50 }}>
          <ambientLight intensity={0.6} />
          <directionalLight position={[2, 2, 2]} intensity={0.8} />
          <Rig frames={frames} videoRef={videoRef} side={side} />
          <OrbitControls target={[0, 0, 0]} />
        </Canvas>
      </div>
      <p className="mt-1 text-xs text-gray-400">
        Modèle musculaire dérivé de Z-Anatomy (BodyParts3D), licence CC BY-SA 4.0.
        Voir NOTICE.md.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Mettre à jour `page.tsx`**

Dans `web/app/page.tsx`, étendre le type `AnalysisResponse` (lignes 23-28) :

```ts
type AnalysisResponse = {
  summary: AnalysisSummary;
  annotated_video_url: string;
  csv_url: string;
  pose3d_url: string;
  side: Side;
};
```

Puis, dans le rendu du résultat (ligne 403), passer `side` à `PostureAvatar3D` en le lisant depuis la réponse stockée, pas depuis l'état local du formulaire :

```tsx
            <PostureAvatar3D pose3dUrl={result.pose3d_url} videoRef={resultVideoRef} side={result.side} />
```

- [ ] **Step 3: Vérifier la compilation TypeScript**

Run: `cd "web" && npx tsc --noEmit`
Expected: aucune erreur.

- [ ] **Step 4: Vérifier le lint**

Run: `cd "web" && npm run lint`
Expected: aucune erreur (avertissements pré-existants sans rapport avec ces fichiers acceptables).

- [ ] **Step 5: Vérifier que le build de production passe**

Run: `cd "web" && npm run build`
Expected: build réussi, sans erreur.

- [ ] **Step 6: Relancer toute la suite Vitest (non-régression)**

Run: `cd "web" && npx vitest run`
Expected: PASS, aucune régression (ce composant n'a pas de test dédié — la vérification manuelle se fait Task 6).

- [ ] **Step 7: Commit**

```bash
git add web/app/PostureAvatar3D.tsx web/app/page.tsx
git commit -m "feat: colore chaque muscle par son propre segment RULA (tranche 4)"
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

- [ ] **Step 2: Vérifier sur une vraie vidéo avec la coloration par segment**

Utiliser Playwright (skill `playwright-skill`) pour : ouvrir `http://localhost:3000`, importer
`.playwright-mcp/moi coupe.mp4` (bouton "Importer une vidéo"), sélectionner un côté (ex. "droit"),
remplir le reste du formulaire, lancer l'analyse, puis une fois le résultat affiché :
- Vérifier que le cou, le tronc, le bras droit et l'avant-bras droit se colorent chacun
  indépendamment au fil de la lecture (pas forcément la même couleur au même instant — c'est
  attendu, chaque segment a son propre sous-score).
- Vérifier que le bras et l'avant-bras GAUCHES (côté non analysé) restent en gris fixe pendant
  toute la lecture, quelle que soit la couleur affichée ailleurs sur l'avatar.
- Vérifier que les cuisses suivent toujours la teinte globale uniforme (comportement Tranche 3,
  inchangé) — comparer visuellement à une capture d'écran de la Tranche 3 si disponible dans
  `.playwright-mcp/`.
- Vérifier dans la console du navigateur l'absence d'erreur (en particulier aucune erreur levée par
  `resolveMeshBoneKey`/`resolveMeshRouting`, qui indiquerait un mesh dont le skinning ne pointe vers
  aucun os connu).
- Refaire le test avec le sélecteur sur "gauche" : confirmer que c'est cette fois le bras/avant-bras
  droit qui reste gris fixe, et le gauche qui se colore par segment (symétrique du test précédent).

- [ ] **Step 3: Vérifier le fallback "aucune détection"**

Importer `samples/synthetic_smoke_test.mp4` (vidéo sans personne). Vérifier que le message
"Aucune posture détectée sur cette vidéo." s'affiche toujours, sans erreur console.

- [ ] **Step 4: Mettre à jour le README**

Dans `README.md`, section "8. Feuille de Route de Déploiement", ajouter une entrée juste après le
bloc "Avatar 3D de posture, Tranche 3" (avant "#### Reste à faire pour la suite de la Phase 2",
actuellement ligne 419) :

```markdown
#### ✅ Avatar 3D de posture, Tranche 4 (coloration par segment anatomique) — TERMINÉE

- **Contexte** : la Tranche 3 appliquait une teinte uniforme (`action_level` global) à tous les
  muscles importés. Cette tranche colore chaque segment indépendamment à partir des sous-scores
  RULA déjà calculés par `compute_rula_score()` mais jusqu'ici jetés avant d'atteindre le frontend.
- **Backend** : `Pose3DFrameRecord` (`pose3d_export.py`) gagne un champ additif
  `segment_action_levels` (cou/tronc/bras/avant-bras, réutilisant `action_level()` telle quelle sur
  chaque sous-score) ; `side` (le côté analysé) est ajouté à la réponse JSON de `POST /analyses`,
  pas à `pose3d.json`.
- **`web/app/muscleSegments.ts`** (nouveau, module pur) : résout le segment RULA de chaque muscle
  importé par son os dominant (somme des poids de peau `skinIndex`/`skinWeight`), via une table de 9
  entrées (une par os) plutôt qu'une duplication des ~30 noms de muscles Z-Anatomy.
- **`PostureAvatar3D.tsx`** : chaque muscle est coloré par son propre segment (cou, tronc, bras,
  avant-bras) ; le bras/avant-bras du côté NON analysé reste en gris fixe en permanence (aucune
  donnée mesurée pour ce côté) ; les cuisses gardent la teinte uniforme de la Tranche 3 (le score
  `legs` est une constante jamais mesurée depuis la vidéo).
- **Vérifié manuellement (2026-09-21)** sur `moi coupe.mp4`, dans les deux sens (côté "droit" puis
  "gauche") : chaque segment se colore indépendamment, le côté non analysé reste gris, les cuisses
  suivent toujours la teinte globale, fallback "aucune posture détectée" toujours correct sur
  `synthetic_smoke_test.mp4`.
- **Ce qui n'est pas dans cette tranche** : analyse simultanée des deux côtés, coloration des
  cuisses par un vrai signal mesuré, segments `wrist`/`wrist_twist` (pas d'os poignet dans le rig) —
  voir la spec `docs/superpowers/specs/2026-09-21-3d-posture-muscle-segment-coloring-design.md`.
```

Et mettre à jour la liste des documents de référence en haut de la section 8 (après la ligne
concernant `docs/superpowers/plans/2026-09-20-3d-posture-muscle-mesh-implementation.md`) pour
ajouter :

```markdown
- `docs/superpowers/specs/2026-09-21-3d-posture-muscle-segment-coloring-design.md` — la spec de la
  tranche 4 de l'avatar 3D de posture (coloration par segment anatomique).
- `docs/superpowers/plans/2026-09-21-3d-posture-muscle-segment-coloring-plan.md` — le plan
  d'implémentation de cette tranche.
```

Enfin, dans la section "Reste à faire pour la suite de la Phase 2", supprimer le bullet devenu
obsolète :

```markdown
- Avatar 3D de posture, Tranche 4 (future, non planifiée) : coloration/activation des muscles par
  segment anatomique à partir des sous-scores RULA déjà calculés (`neck`, `trunk`, `upper_arm`,
  `lower_arm`, `wrist`), à la place de la teinte uniforme sur l'ensemble des muscles livrée en
  Tranche 3.
```

(cette tranche n'est plus "future, non planifiée" — elle vient d'être livrée, décrite par le nouveau
bloc "✅ ... TERMINÉE" ajouté ci-dessus).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: tranche 4 livrée — coloration par segment anatomique de l'avatar 3D"
```
