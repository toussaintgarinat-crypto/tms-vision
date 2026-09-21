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
