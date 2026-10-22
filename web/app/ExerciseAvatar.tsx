"use client";

import { useGLTF } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo } from "react";
import * as THREE from "three";
import { Exercise, applyPoseToSkeleton, captureRestPose, samplePose } from "./exercisePose";
import { cameraPosition, framingFor } from "./exerciseFraming";
import { MUSCLE_RIG_URL, prepareMuscleModel } from "./muscleModel";

// Bleu pour les segments ciblés par l'exercice, gris neutre pour le reste (même
// gris que PostureAvatar3D : on ne colore jamais une donnée sans signification).
export const TARGET_COLOR = "#1E88E5";
export const NEUTRAL_COLOR = "#9E9E9E";
export const BACKGROUND_COLOR = "#EEF1F4";

export type ExerciseAvatarApi = {
  // Pose l'avatar à l'instant t de l'exercice et rend l'image, de façon synchrone.
  renderAt: (exercise: Exercise, t: number) => void;
};

// Sol : disque clair bordé d'un dégradé et ombre de contact sous les pieds, pour donner
// de la profondeur et un repère de contact (sans lui la silhouette flotte sur un fond uni).
function radialTexture(stops: [number, string][]): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
  stops.forEach(([at, color]) => gradient.addColorStop(at, color));
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 256, 256);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function Floor() {
  const floor = useMemo(
    () => radialTexture([[0, "rgba(255,255,255,0.95)"], [0.6, "rgba(255,255,255,0.55)"], [1, "rgba(255,255,255,0)"]]),
    [],
  );
  const shadow = useMemo(
    () => radialTexture([[0, "rgba(30,41,59,0.45)"], [0.5, "rgba(30,41,59,0.2)"], [1, "rgba(30,41,59,0)"]]),
    [],
  );
  return (
    <>
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.002, 0]}>
        <planeGeometry args={[2.4, 2.4]} />
        <meshBasicMaterial map={floor} transparent depthWrite={false} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.001, 0]}>
        <planeGeometry args={[0.9, 0.9]} />
        <meshBasicMaterial map={shadow} transparent depthWrite={false} />
      </mesh>
    </>
  );
}

export function ExerciseAvatar({ onReady }: { onReady: (api: ExerciseAvatarApi) => void }) {
  const gltf = useGLTF(MUSCLE_RIG_URL);
  const model = useMemo(() => prepareMuscleModel(gltf.scene), [gltf]);
  // Orientations de repos, capturées une fois sur le squelette intact (avant toute pose).
  const rest = useMemo(() => captureRestPose(model.bones), [model]);
  const { gl, scene: rootScene, camera, size } = useThree();

  const renderAt = useCallback(
    (exercise: Exercise, t: number) => {
      applyPoseToSkeleton(model.bones, rest, samplePose(exercise, t));

      const targets = new Set<string>(exercise.target_segments);
      model.routing.forEach((routing, index) => {
        const highlighted = routing.region !== null && targets.has(routing.region);
        model.materials[index].color.set(highlighted ? TARGET_COLOR : NEUTRAL_COLOR);
      });

      const framing = framingFor(exercise);
      camera.position.copy(cameraPosition(exercise.view, framing));
      camera.lookAt(framing.target);
      (camera as THREE.PerspectiveCamera).updateProjectionMatrix();

      gl.render(rootScene, camera);
    },
    [model, rest, camera, gl, rootScene],
  );

  // Annonce l'API une fois le modèle chargé ET le canvas mesuré (sinon le premier
  // rendu se ferait à une taille nulle).
  useEffect(() => {
    if (size.width > 0 && size.height > 0) onReady({ renderAt });
  }, [renderAt, onReady, size.width, size.height]);

  return (
    <>
      <color attach="background" args={[BACKGROUND_COLOR]} />
      <ambientLight intensity={1.1} />
      <directionalLight position={[2, 3, 4]} intensity={1.2} />
      <directionalLight position={[-2, 2, -3]} intensity={0.8} />
      <directionalLight position={[-3, 1, 3]} intensity={0.6} />
      <hemisphereLight args={["#ffffff", "#aab4c0", 0.5]} />
      <Floor />
      <primitive object={model.scene} />
    </>
  );
}
