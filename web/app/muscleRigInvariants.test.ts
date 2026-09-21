import { describe, expect, it, beforeAll } from "vitest";
import fs from "node:fs";
import path from "node:path";
import * as THREE from "three";
import { GLTFLoader, GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { BoneKey } from "./pose3dSkeleton";
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

const EXPECTED_BONE_COUNTS: Record<BoneKey, number> = {
  root: 0,
  spine: 10,
  neck: 16,
  L_upper_arm: 16,
  R_upper_arm: 16,
  L_forearm: 12,
  R_forearm: 12,
  L_thigh: 12,
  R_thigh: 12,
};
const EXPECTED_TOTAL_PRIMITIVES = 106;

describe("invariants du rig musculaire réel (web/public/muscle-rig.glb)", () => {
  let skinnedMeshes: THREE.SkinnedMesh[];
  let nameDerivedSideByMesh: Map<THREE.SkinnedMesh, "left" | "right" | undefined>;

  beforeAll(async () => {
    const buffer = fs.readFileSync(MUSCLE_RIG_PATH);
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

  it("contient exactement 106 primitives skinnées", () => {
    expect(skinnedMeshes.length).toBe(EXPECTED_TOTAL_PRIMITIVES);
  });

  it("résout chaque primitive sur un os dominant sensé, avec la répartition exacte attendue", () => {
    // Réutilise `resolveMeshBoneKey` (donc `dominantBoneIndex`) telle quelle
    // -- même logique que le composant de rendu, pas une réimplémentation
    // séparée susceptible de diverger silencieusement de la vraie logique de
    // coloration.
    const boneCounts: Record<BoneKey, number> = {
      root: 0,
      spine: 0,
      neck: 0,
      L_upper_arm: 0,
      R_upper_arm: 0,
      L_forearm: 0,
      R_forearm: 0,
      L_thigh: 0,
      R_thigh: 0,
    };
    for (const mesh of skinnedMeshes) {
      const boneKey = resolveMeshBoneKey(mesh);
      boneCounts[boneKey] += 1;
    }
    expect(boneCounts).toEqual(EXPECTED_BONE_COUNTS);
  });

  it("ne résout jamais une primitive sur `root` (locateur de longueur nulle, jamais un vrai muscle)", () => {
    const rootCount = skinnedMeshes.filter((mesh) => resolveMeshBoneKey(mesh) === "root").length;
    expect(rootCount).toBe(0);
  });

  it("le côté déduit du nom de chaque primitive (.l/.r) correspond au préfixe L_/R_ de son os dominant", () => {
    let checked = 0;
    for (const mesh of skinnedMeshes) {
      const nameDerivedSide = nameDerivedSideByMesh.get(mesh);
      const routing = resolveMeshRouting(mesh);
      if (routing.side === null) {
        // Os sans variante gauche/droite (spine/neck) : rien à comparer.
        continue;
      }
      expect(nameDerivedSide, `primitive "${mesh.name}" sans côté déductible de son nom`).toBeDefined();
      expect(routing.side).toBe(nameDerivedSide);
      checked += 1;
    }
    // Les 4 os de membre (L/R upper_arm, L/R forearm, L/R thigh) totalisent
    // 16+16+12+12+12+12 = 80 primitives sur les 106 -- s'assurer que la
    // comparaison ci-dessus a bien porté sur ce nombre, pas silencieusement
    // sauté faute de correspondance trouvée.
    expect(checked).toBe(80);
  });
});
