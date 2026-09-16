"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { applyFrameToSkeleton, BoneKey, buildSkeleton, Pose3DLandmarks } from "./pose3dSkeleton";
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
  const geometry = useMemo(() => buildTestSkinnedGeometry(), []);

  const rigRef = useRef<{ skeleton: THREE.Skeleton; bones: Record<BoneKey, THREE.Bone> } | null>(null);
  if (rigRef.current === null) {
    rigRef.current = buildSkeleton();
  }

  const meshRef = useRef<THREE.SkinnedMesh>(null);
  const materialRef = useRef<THREE.MeshStandardMaterial>(null);
  const lastKnownLandmarksRef = useRef<Partial<Pose3DLandmarks>>({});
  const lastKnownColorRef = useRef<string>(DEFAULT_COLOR);
  const hasDetectedOnceRef = useRef(false);

  useEffect(() => {
    const mesh = meshRef.current;
    const rig = rigRef.current;
    if (!mesh || !rig) return;
    mesh.add(rig.bones.root);
    mesh.bind(rig.skeleton);
    mesh.visible = false;
  }, []);

  useFrame(() => {
    const video = videoRef.current;
    const mesh = meshRef.current;
    const material = materialRef.current;
    const rig = rigRef.current;
    if (!video || !mesh || !material || !rig || frames.length === 0) return;

    const index = findNearestFrameIndex(frames, video.currentTime);
    const frame = frames[index];

    if (frame.landmarks) {
      applyFrameToSkeleton(rig.bones, frame.landmarks, lastKnownLandmarksRef.current);
      hasDetectedOnceRef.current = true;
      mesh.visible = true;
      // `action_level` peut être null même quand une pose est détectée (les
      // angles RULA n'ont pas pu être calculés cette frame-là) : dans ce cas
      // on conserve la dernière couleur connue plutôt que de retomber sur le
      // gris par défaut (même principe qu'en Tranche 1).
      if (frame.action_level) {
        lastKnownColorRef.current = ACTION_LEVEL_COLORS[frame.action_level] ?? DEFAULT_COLOR;
      }
    }

    if (!hasDetectedOnceRef.current) return;
    material.color.set(lastKnownColorRef.current);
  });

  return (
    <skinnedMesh ref={meshRef} geometry={geometry}>
      <meshStandardMaterial ref={materialRef} color={DEFAULT_COLOR} />
    </skinnedMesh>
  );
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
