import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
import { BONE_ORDER, BoneKey } from "./pose3dSkeleton";
import { MeshSegmentRouting, resolveMeshRouting } from "./muscleSegments";

export const MUSCLE_RIG_URL = "/muscle-rig.glb";

export const MUSCLE_MODEL_CREDIT =
  "Modèle musculaire dérivé de Z-Anatomy (BodyParts3D), licence CC BY-SA 4.0.";

export type MuscleModel = {
  scene: THREE.Object3D;
  meshes: THREE.SkinnedMesh[];
  routing: MeshSegmentRouting[];
  materials: THREE.MeshStandardMaterial[];
  bones: Record<BoneKey, THREE.Bone>;
};

// Prépare une copie exploitable du modèle chargé : scène clonée (le `gltf.scene` de
// `useGLTF` est partagé et mémoïsé), matériaux clonés et affectés, routage de chaque
// maillage vers son segment, table des os.
//
// NB : `PostureAvatar3D.tsx::Rig` fait la même préparation en ligne, dans des hooks
// React. On ne l'extrait volontairement pas ici, pour ne pas risquer de régression sur
// l'avatar piloté par la vidéo (il n'a pas de test d'affichage automatisé) ; les deux
// doivent rester cohérents (voir les commentaires de `Rig` sur le clonage, l'émissif
// et le frustum culling), et pourront être unifiés dans un travail dédié.
export function prepareMuscleModel(gltfScene: THREE.Object3D): MuscleModel {
  const scene = cloneSkeleton(gltfScene);

  const meshes: THREE.SkinnedMesh[] = [];
  scene.traverse((object) => {
    if ((object as THREE.SkinnedMesh).isSkinnedMesh) meshes.push(object as THREE.SkinnedMesh);
  });
  if (meshes.length === 0) {
    throw new Error("muscle-rig.glb ne contient aucun SkinnedMesh.");
  }

  const routing = meshes.map((mesh) => resolveMeshRouting(mesh));

  const bones = {} as Record<BoneKey, THREE.Bone>;
  for (const key of BONE_ORDER) {
    const bone = meshes[0].skeleton.bones.find((candidate) => candidate.name === key);
    if (!bone) {
      throw new Error(`Os "${key}" introuvable dans le squelette importé (muscle-rig.glb).`);
    }
    bones[key] = bone;
  }

  const materials = meshes.map((mesh) => {
    const source = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
    const clone = (source as THREE.MeshStandardMaterial).clone();
    // Les matériaux Z-Anatomy portent un emissiveFactor blanc : sans cette
    // neutralisation, l'image sature en blanc et aucune teinte n'est visible.
    clone.emissive.set(0x000000);
    return clone;
  });
  meshes.forEach((mesh, index) => {
    mesh.material = materials[index];
    // La bounding sphere d'un SkinnedMesh n'est pas recalculée quand les os bougent :
    // sans cela, un membre très écarté de sa pose de repos disparaît à tort.
    mesh.frustumCulled = false;
  });

  return { scene, meshes, routing, materials, bones };
}
