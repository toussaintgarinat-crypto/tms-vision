"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { Capsule, OrbitControls, Sphere } from "@react-three/drei";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Mêmes segments que src/tms_vision/overlay.py::_SKELETON_CONNECTIONS.
const SKELETON_CONNECTIONS: [string, string][] = [
  ["LEFT_SHOULDER", "RIGHT_SHOULDER"],
  ["LEFT_SHOULDER", "LEFT_ELBOW"],
  ["LEFT_ELBOW", "LEFT_WRIST"],
  ["RIGHT_SHOULDER", "RIGHT_ELBOW"],
  ["RIGHT_ELBOW", "RIGHT_WRIST"],
  ["LEFT_SHOULDER", "LEFT_HIP"],
  ["RIGHT_SHOULDER", "RIGHT_HIP"],
  ["LEFT_HIP", "RIGHT_HIP"],
  ["LEFT_HIP", "LEFT_KNEE"],
  ["RIGHT_HIP", "RIGHT_KNEE"],
];
const HEAD_LANDMARK = "NOSE";
const CAPSULE_RADIUS = 0.05;
const HEAD_RADIUS = 0.12;

// Même palette que src/tms_vision/overlay.py::_COLOR_BY_LEVEL (converti BGR -> hex RGB).
const ACTION_LEVEL_COLORS: Record<string, string> = {
  acceptable: "#4CAF50",
  investigation_recommandee: "#EBD23C",
  investigation_et_changement_bientot: "#EB9628",
  changement_immediat: "#D23232",
};
const DEFAULT_COLOR = "#9E9E9E";

type Pose3DLandmarks = Record<string, [number, number, number]>;

type Pose3DFrame = {
  frame_index: number;
  timestamp_seconds: number;
  detected: boolean;
  landmarks: Pose3DLandmarks | null;
  action_level: string | null;
};

function toThreeVector(coords: [number, number, number]): THREE.Vector3 {
  const [x, y, z] = coords;
  // MediaPipe pose_world_landmarks : x droite, y vers le bas (même
  // orientation que les landmarks 2D image), origine au centre des
  // hanches. Three.js est y-vers-le-haut : on inverse y. À vérifier
  // visuellement sur une vraie vidéo (Task 8) -- inverser un autre axe ici
  // si l'avatar apparaît miroir ou de travers.
  return new THREE.Vector3(x, -y, z);
}

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
  const capsuleRefs = useRef<(THREE.Mesh | null)[]>([]);
  const capsuleMaterialRefs = useRef<(THREE.MeshStandardMaterial | null)[]>([]);
  const headRef = useRef<THREE.Mesh | null>(null);
  const headMaterialRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const lastKnownLandmarksRef = useRef<Pose3DLandmarks | null>(null);
  const lastKnownColorRef = useRef<string>(DEFAULT_COLOR);

  useFrame(() => {
    const video = videoRef.current;
    if (!video || frames.length === 0) return;

    const index = findNearestFrameIndex(frames, video.currentTime);
    const frame = frames[index];
    if (frame.landmarks) {
      lastKnownLandmarksRef.current = frame.landmarks;
      lastKnownColorRef.current = frame.action_level
        ? ACTION_LEVEL_COLORS[frame.action_level] ?? DEFAULT_COLOR
        : DEFAULT_COLOR;
    }
    const landmarks = lastKnownLandmarksRef.current;
    if (!landmarks) return;
    const color = lastKnownColorRef.current;

    SKELETON_CONNECTIONS.forEach(([startName, endName], i) => {
      const mesh = capsuleRefs.current[i];
      const material = capsuleMaterialRefs.current[i];
      const startCoords = landmarks[startName];
      const endCoords = landmarks[endName];
      if (!mesh || !material || !startCoords || !endCoords) return;

      const start = toThreeVector(startCoords);
      const end = toThreeVector(endCoords);
      const direction = new THREE.Vector3().subVectors(end, start);
      const boneLength = direction.length();
      const midpoint = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);

      mesh.position.copy(midpoint);
      if (boneLength > 1e-4) {
        mesh.quaternion.setFromUnitVectors(
          new THREE.Vector3(0, 1, 0),
          direction.clone().normalize()
        );
        mesh.scale.set(1, boneLength, 1);
      }
      material.color.set(color);
    });

    const headCoords = landmarks[HEAD_LANDMARK];
    if (headRef.current && headMaterialRef.current && headCoords) {
      headRef.current.position.copy(toThreeVector(headCoords));
      headMaterialRef.current.color.set(color);
    }
  });

  return (
    <>
      {SKELETON_CONNECTIONS.map(([startName, endName], i) => (
        <Capsule
          key={`${startName}-${endName}`}
          ref={(mesh) => {
            capsuleRefs.current[i] = mesh;
          }}
          args={[CAPSULE_RADIUS, 1, 4, 8]}
        >
          <meshStandardMaterial
            ref={(material) => {
              capsuleMaterialRefs.current[i] = material;
            }}
            color={DEFAULT_COLOR}
          />
        </Capsule>
      ))}
      <Sphere ref={headRef} args={[HEAD_RADIUS, 16, 16]}>
        <meshStandardMaterial ref={headMaterialRef} color={DEFAULT_COLOR} />
      </Sphere>
    </>
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
  if (!frames.some((frame) => frame.detected)) {
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
