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
      <primitive object={model.scene} />
    </>
  );
}
