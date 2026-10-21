"use client";

import { useGLTF } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo } from "react";
import * as THREE from "three";
import { Exercise, applyPoseToSkeleton, captureRestPose, samplePose } from "./exercisePose";
import { MUSCLE_RIG_URL, prepareMuscleModel } from "./muscleModel";

// Bleu pour les segments ciblés par l'exercice, gris neutre pour le reste (même
// gris que PostureAvatar3D : on ne colore jamais une donnée sans signification).
export const TARGET_COLOR = "#1E88E5";
export const NEUTRAL_COLOR = "#9E9E9E";
export const BACKGROUND_COLOR = "#EEF1F4";

// Cadrage de la caméra par vue. Mesuré sur le vrai muscle-rig.glb au repos : le corps
// s'étend de y = 0.37 (bas des cuisses) à y = 1.58 (haut du cou), x de -0.32 à 0.32.
// On laisse de la place au-dessus (avant-bras levé, titre) : cible un peu au-dessus du
// centre du corps, et recul suffisant pour que l'avant-bras levé (jusqu'à y ≈ 1.9) reste
// sous le bandeau de titre.
const TARGET = new THREE.Vector3(0, 1.08, 0);
const DISTANCE = 3.2;
const CAMERA_POSITIONS: Record<Exercise["view"], THREE.Vector3> = {
  // Face au sujet (son avant est +z).
  front: new THREE.Vector3(0, TARGET.y, DISTANCE),
  // Côté droit du sujet (-x) : il regarde vers la droite de l'image.
  side: new THREE.Vector3(-DISTANCE, TARGET.y, 0),
  three_quarter: new THREE.Vector3(-DISTANCE * 0.6, TARGET.y + 0.1, DISTANCE * 0.8),
};

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
        const highlighted = routing.segment !== null && targets.has(routing.segment);
        model.materials[index].color.set(highlighted ? TARGET_COLOR : NEUTRAL_COLOR);
      });

      camera.position.copy(CAMERA_POSITIONS[exercise.view]);
      camera.lookAt(TARGET);
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
