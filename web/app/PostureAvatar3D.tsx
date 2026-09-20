"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
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

  // `useGLTF` mémoïse et partage `gltf.scene` entre tous les composants qui
  // chargent la même URL. Le traiter comme un template en clonant une copie
  // dédiée à ce montage (via SkeletonUtils.clone, qui préserve correctement
  // les liaisons squelette/SkinnedMesh, contrairement à Object3D.clone) :
  // sans cela, muter `mesh.material` directement sur la scène partagée
  // provoque une désynchronisation entre l'objet réellement affiché et
  // celui mis à jour par la boucle de coloration ci-dessous dès que le
  // composant est monté plus d'une fois sur la session (ex. Strict Mode en
  // dev, ou plusieurs analyses successives) — chaque montage réattribue
  // `mesh.material` sur les mêmes objets partagés, et le montage devenu
  // obsolète peut rester celui dont la référence `.material` colle
  // effectivement à la scène rendue, alors que sa propre boucle useFrame
  // ne tourne plus. Constaté visuellement le 2026-09-20 : les muscles
  // restaient gris quel que soit l'action_level tant que ce clonage
  // n'était pas fait.
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
      // (1,1,1) sans texture d'émission (vérifié dans muscle-rig.glb : les
      // 12 matériaux). À pleine intensité, ce terme émissif s'ajoute au
      // rendu indépendamment de `color` et sature l'image en blanc, ce qui
      // rend invisible toute teinte appliquée par action_level ci-dessous.
      // On neutralise l'émissif pour que la teinte reste visible.
      clone.emissive.set(0x000000);
      return clone;
    });
  }, [skinnedMeshes]);

  // Affecter les clones aux meshes dans un effet (pas pendant le rendu) :
  // en Strict Mode (dev), React invoque deux fois le corps du composant
  // (et donc les initialiseurs `useMemo`) pour détecter les effets de bord
  // impurs. Affecter `mesh.material = clone` DANS le `useMemo` ci-dessus
  // (comme le faisait une version antérieure de ce code) crée deux
  // générations de clones et mute les meshes partagés à chaque passage :
  // le mesh réellement affiché pouvait alors garder le matériau de la
  // première passe (jamais recoloré par la boucle ci-dessous), tandis que
  // `clonedMaterials` référençait la seconde — désynchronisation constatée
  // visuellement le 2026-09-20 (muscles restés gris quel que soit
  // l'action_level, malgré `material.color` correctement mis à jour côté
  // JS). Un `useEffect` s'exécute après le commit et réaffecte les mêmes
  // références de façon idempotente, ce qui règle le problème même s'il
  // est aussi rejoué deux fois par Strict Mode.
  useEffect(() => {
    skinnedMeshes.forEach((mesh, index) => {
      mesh.material = clonedMaterials[index];
      // Three.js calcule la bounding sphere d'un SkinnedMesh une seule fois
      // (à partir de la géométrie en bind pose) et ne la recalcule jamais
      // lorsque les os bougent via `applyFrameToSkeleton` (boucle useFrame
      // ci-dessous). Sans désactiver le frustum culling, un membre qui
      // s'écarte largement de sa pose de repos (ex. un bras très levé) peut
      // sortir du volume englobant mis en cache et disparaître à tort dès
      // qu'il dépasse les limites de la caméra calculées pour la pose de
      // repos.
      mesh.frustumCulled = false;
    });
  }, [skinnedMeshes, clonedMaterials]);

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
      <primitive object={scene} />
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
    <div className="w-full">
      <div className="aspect-video w-full overflow-hidden rounded-lg bg-gray-900">
        <Canvas camera={{ position: [0, 0, 2.5], fov: 50 }}>
          <ambientLight intensity={0.6} />
          <directionalLight position={[2, 2, 2]} intensity={0.8} />
          <Rig frames={frames} videoRef={videoRef} />
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
