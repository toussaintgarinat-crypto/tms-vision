"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import { applyFrameToSkeleton, BONE_ORDER, BoneKey, Pose3DLandmarks } from "./pose3dSkeleton";

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
  const gltf = useGLTF(MUSCLE_RIG_URL);

  const skinnedMeshes = useMemo(() => {
    const meshes: THREE.SkinnedMesh[] = [];
    gltf.scene.traverse((object) => {
      if ((object as THREE.SkinnedMesh).isSkinnedMesh) {
        meshes.push(object as THREE.SkinnedMesh);
      }
    });
    return meshes;
  }, [gltf]);

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
  // composant est démonté/remonté.
  const clonedMaterials = useMemo(() => {
    return skinnedMeshes.map((mesh) => {
      const source = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
      const clone = (source as THREE.MeshStandardMaterial).clone();
      mesh.material = clone;
      return clone;
    });
  }, [skinnedMeshes]);

  const groupRef = useRef<THREE.Group>(null);
  const lastKnownLandmarksRef = useRef<Partial<Pose3DLandmarks>>({});
  const lastKnownColorRef = useRef<string>(DEFAULT_COLOR);
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
        lastKnownColorRef.current = ACTION_LEVEL_COLORS[frame.action_level] ?? DEFAULT_COLOR;
      }
    }

    if (!hasDetectedOnceRef.current) return;
    for (const material of clonedMaterials) {
      material.color.set(lastKnownColorRef.current);
    }
  });

  return (
    <group ref={groupRef} visible={false}>
      <primitive object={gltf.scene} />
    </group>
  );
}

useGLTF.preload(MUSCLE_RIG_URL);

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
      <p className="mt-1 text-xs text-gray-400">
        Modèle musculaire dérivé de Z-Anatomy (BodyParts3D), licence CC BY-SA 4.0.
        Voir NOTICE.md.
      </p>
    </div>
  );
}
