import { describe, expect, it, beforeAll } from "vitest";
import fs from "node:fs";
import path from "node:path";
import * as THREE from "three";
import { GLTFLoader, GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { BONE_ORDER } from "./pose3dSkeleton";
import { REGIONS, Region } from "./exercisePose";
import { resolveMeshBoneKey, resolveMeshRouting } from "./muscleSegments";

// Garde-fou de non-régression pour le fichier RÉEL et COMMITÉ
// `web/public/muscle-rig.glb`. Ce rig a déjà cassé silencieusement une fois
// dans l'historique de ce projet (Tranche 3 : 20 muscles de membre gauche
// skinnés sur les os DROITS, trouvé uniquement en décodant le binaire de
// skin à la main -- voir la correction 2026-09-20 dans
// `docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-design.md`) sans
// qu'aucun test automatisé ne l'ait détecté. Ce fichier comble ce trou : il
// réexécute la MÊME logique de résolution d'os dominant que
// `PostureAvatar3D.tsx` (via `resolveMeshBoneKey`/`resolveMeshRouting`,
// réutilisées telles quelles, pas réimplémentées) sur le vrai `.glb`, pas sur
// des données synthétiques comme `muscleSegments.test.ts`.
//
// Depuis la Tranche 4 (corps complet), le fichier a 24 os, ~360 muscles et porte la région et le
// côté de chaque muscle dans `userData` (voir tools/blender/export_muscle_rig.py).

const MUSCLE_RIG_PATH = path.resolve(__dirname, "..", "public", "muscle-rig.glb");

const GLB_JSON_CHUNK_TYPE = 0x4e4f534a; // ASCII "JSON", little-endian dans le champ chunkType du .glb

interface GltfNode {
  name?: string;
  mesh?: number;
}

interface GltfDocument {
  nodes: GltfNode[];
}

// Parse minimal du conteneur binaire .glb, uniquement pour en extraire le
// chunk JSON (le document glTF). On n'en a besoin que pour une donnée que
// GLTFLoader ne restitue pas fidèlement sur les objets THREE reconstruits :
// le nom ORIGINAL du node glTF (ex. "Acromial part of deltoid muscle.l").
// GLTFLoader sanitize les noms qu'il assigne aux objets THREE (espaces et
// points supprimés, ex. "Acromial_part_of_deltoid_musclel"), ce qui rend le
// suffixe `.l`/`.r` ambigu à relire après coup. Les données de skin
// (skinIndex/skinWeight) elles-mêmes, en revanche, viennent bien de
// GLTFLoader (pas de ce parsing manuel) : c'est la partie qui compte pour
// l'invariant testé.
function readGlbJsonDocument(buffer: Buffer): GltfDocument {
  const magic = buffer.readUInt32LE(0);
  if (magic !== 0x46546c67) {
    throw new Error("muscle-rig.glb : en-tête .glb invalide (magic incorrect).");
  }
  const totalLength = buffer.readUInt32LE(8);
  let offset = 12;
  while (offset < totalLength) {
    const chunkLength = buffer.readUInt32LE(offset);
    const chunkType = buffer.readUInt32LE(offset + 4);
    const chunkData = buffer.subarray(offset + 8, offset + 8 + chunkLength);
    if (chunkType === GLB_JSON_CHUNK_TYPE) {
      return JSON.parse(chunkData.toString("utf8")) as GltfDocument;
    }
    offset += 8 + chunkLength;
  }
  throw new Error("muscle-rig.glb : aucun chunk JSON trouvé.");
}

// Table meshIndex (index dans json.meshes, le datablock Blender) -> côté
// déduit du suffixe `.l`/`.r` du NOM DU NODE qui référence ce mesh. Validé au
// préalable (inspection manuelle du JSON réel) : les 54 meshes du rig sont
// chacun référencés par exactement un seul node (aucun datablock partagé,
// invariant garanti côté export par `validate_muscle_rig.py` depuis la
// correction du bug gauche/droite de Tranche 3), et les 54 noms de node ont
// tous un suffixe `.l`/`.r` -- donc cette table est totale sur les meshes du
// rig actuel, pas seulement partielle.
function buildMeshIndexToSide(document: GltfDocument): Map<number, "left" | "right"> {
  const map = new Map<number, "left" | "right">();
  for (const node of document.nodes) {
    if (node.mesh === undefined) continue;
    const match = /\.(l|r)$/i.exec(node.name ?? "");
    if (!match) continue;
    map.set(node.mesh, match[1].toLowerCase() === "l" ? "left" : "right");
  }
  return map;
}


const EXPECTED_MESH_COUNT = 358;
const MAX_FILE_BYTES = 25 * 1024 * 1024;

// Régions dont les muscles se trouvent d'un seul côté du plan médian (le tronc, le cou, la tête, le
// bassin et la ceinture scapulaire ont des muscles qui touchent ou franchissent le milieu).
const LATERAL_REGIONS: ReadonlySet<Region> = new Set<Region>([
  "upper_arm",
  "lower_arm",
  "hand",
  "thigh",
  "lower_leg",
  "foot",
]);

describe("invariants du rig musculaire réel (web/public/muscle-rig.glb)", () => {
  let skinnedMeshes: THREE.SkinnedMesh[];
  let nameDerivedSideByMesh: Map<THREE.SkinnedMesh, "left" | "right" | undefined>;
  let fileSize: number;

  beforeAll(async () => {
    const buffer = fs.readFileSync(MUSCLE_RIG_PATH);
    fileSize = buffer.byteLength;
    const arrayBuffer = buffer.buffer.slice(
      buffer.byteOffset,
      buffer.byteOffset + buffer.byteLength
    ) as ArrayBuffer;
    const document = readGlbJsonDocument(buffer);
    const meshIndexToSide = buildMeshIndexToSide(document);

    const loader = new GLTFLoader();
    const gltf = await new Promise<GLTF>((resolve, reject) => {
      loader.parse(arrayBuffer, "", resolve, reject);
    });

    skinnedMeshes = [];
    gltf.scene.traverse((object) => {
      if ((object as THREE.SkinnedMesh).isSkinnedMesh) {
        skinnedMeshes.push(object as THREE.SkinnedMesh);
      }
    });

    nameDerivedSideByMesh = new Map();
    for (const mesh of skinnedMeshes) {
      const reference = gltf.parser.associations.get(mesh);
      const meshIndex = reference?.meshes;
      nameDerivedSideByMesh.set(
        mesh,
        meshIndex !== undefined ? meshIndexToSide.get(meshIndex) : undefined
      );
    }
  });

  it(`contient exactement ${EXPECTED_MESH_COUNT} primitives skinnées, une par muscle`, () => {
    expect(skinnedMeshes.length).toBe(EXPECTED_MESH_COUNT);
  });

  it("tient dans 25 Mo", () => {
    expect(fileSize).toBeLessThan(MAX_FILE_BYTES);
  });

  it("a un squelette de 24 os, avec exactement les noms de BONE_ORDER", () => {
    const names = skinnedMeshes[0].skeleton.bones.map((bone) => bone.name);
    expect(new Set(names)).toEqual(new Set(BONE_ORDER));
    expect(names.length).toBe(BONE_ORDER.length);
    for (const mesh of skinnedMeshes) {
      expect(mesh.skeleton.bones.length, mesh.name).toBe(BONE_ORDER.length);
    }
  });

  it("déclare pour chaque muscle une région connue et un côté (l ou r)", () => {
    for (const mesh of skinnedMeshes) {
      expect(REGIONS as readonly string[], `${mesh.name} : région`).toContain(mesh.userData.region);
      expect(["l", "r"], `${mesh.name} : côté`).toContain(mesh.userData.side);
    }
  });

  it("couvre toutes les régions, des deux côtés", () => {
    for (const region of REGIONS) {
      for (const side of ["l", "r"]) {
        const count = skinnedMeshes.filter(
          (mesh) => mesh.userData.region === region && mesh.userData.side === side
        ).length;
        expect(count, `${region}/${side}`).toBeGreaterThan(0);
      }
    }
  });

  it("donne à chaque sommet des poids de peau positifs dont la somme vaut 1", () => {
    for (const mesh of skinnedMeshes) {
      const weights = mesh.geometry.attributes.skinWeight as THREE.BufferAttribute;
      for (let vertex = 0; vertex < weights.count; vertex++) {
        const sum = weights.getX(vertex) + weights.getY(vertex) + weights.getZ(vertex) + weights.getW(vertex);
        if (Math.abs(sum - 1) > 1e-3) {
          throw new Error(`${mesh.name} : somme des poids ${sum} au sommet ${vertex}`);
        }
      }
    }
  });

  it("ne résout jamais une primitive sur `root` pour un muscle de membre", () => {
    const sidedOnRoot = skinnedMeshes.filter(
      (mesh) =>
        LATERAL_REGIONS.has(mesh.userData.region) && resolveMeshBoneKey(mesh) === "root"
    );
    expect(sidedOnRoot.map((mesh) => mesh.name)).toEqual([]);
  });

  it("le côté déclaré (l/r) correspond au côté de l'os dominant, quand cet os est latéralisé", () => {
    let checked = 0;
    for (const mesh of skinnedMeshes) {
      const dominant = resolveMeshBoneKey(mesh);
      if (!dominant.startsWith("L_") && !dominant.startsWith("R_")) continue;
      const expected = dominant.startsWith("L_") ? "l" : "r";
      expect(mesh.userData.side, `${mesh.name} dominé par ${dominant}`).toBe(expected);
      checked += 1;
    }
    expect(checked).toBeGreaterThan(100);
  });

  it("le côté déduit du nom du node (.l/.r) est celui déclaré dans userData", () => {
    for (const mesh of skinnedMeshes) {
      const fromName = nameDerivedSideByMesh.get(mesh);
      if (fromName === undefined) continue;
      expect(mesh.userData.side, mesh.name).toBe(fromName === "left" ? "l" : "r");
    }
  });

  it("place les muscles gauches des membres en +x et les droits en -x", () => {
    let checked = 0;
    for (const mesh of skinnedMeshes) {
      if (!LATERAL_REGIONS.has(mesh.userData.region)) continue;
      mesh.geometry.computeBoundingBox();
      const centre = mesh.geometry.boundingBox!.getCenter(new THREE.Vector3());
      if (mesh.userData.side === "l") expect(centre.x, mesh.name).toBeGreaterThan(0);
      else expect(centre.x, mesh.name).toBeLessThan(0);
      checked += 1;
    }
    expect(checked).toBeGreaterThan(100);
  });

  it("route chaque muscle vers sa région déclarée", () => {
    for (const mesh of skinnedMeshes) {
      expect(resolveMeshRouting(mesh).region, mesh.name).toBe(mesh.userData.region);
    }
  });
});
