"use client";

import { useGLTF } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import {
  Exercise,
  Position,
  applyPoseToSkeleton,
  captureRestPose,
  samplePose,
  withBasePose,
} from "./exercisePose";
import { BoneKey } from "./pose3dSkeleton";
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
  // Image (JPEG, data URL) de ce qui vient d'être rendu : à appeler juste après `renderAt`.
  snapshot: () => string;
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

// Os dont la hauteur donne le contact avec le sol (assis) ou avec le tapis (allongé).
const FEET: BoneKey[] = ["L_foot", "R_foot", "L_toes", "R_toes"];

function lowestY(bones: Record<BoneKey, THREE.Bone>, keys: BoneKey[]): number {
  const point = new THREE.Vector3();
  return Math.min(...keys.map((key) => bones[key].getWorldPosition(point).y));
}

// Demi-épaisseur du corps : les os sont au milieu du corps, le dos repose sur le tapis.
const LYING_HALF_THICKNESS = 0.1;
const MAT_THICKNESS = 0.03;
const SEAT_HEIGHT_BELOW_PELVIS = 0.1;
// Décalage qui centre le corps couché (pieds en z = 0 avant décalage, tête à -1,7) sur l origine.
const LYING_CENTER_Z = 0.85;

// Place le mannequin selon la position, une fois la pose appliquée ; renvoie de combien il est
// descendu (assis), pour le cadrage. Debout : aucune transformation, rendu identique à celui d'avant
// l'ajout des positions. Assis : les pieds restent au sol, le mannequin descend d'autant que les
// cuisses horizontales ont baissé le bassin. Allongé : couché sur le dos (l'avant +z devient le haut,
// la tête part vers -z), posé sur le tapis puis centré sur l'origine.
function placeBody(
  scene: THREE.Object3D,
  bones: Record<BoneKey, THREE.Bone>,
  position: Position,
  restFeetY: number,
): number {
  scene.rotation.set(0, 0, 0);
  scene.position.set(0, 0, 0);
  let drop = 0;
  if (position === "seated") {
    scene.updateMatrixWorld(true);
    drop = restFeetY - lowestY(bones, FEET);
    scene.position.set(0, -drop, 0);
  } else if (position === "lying") {
    scene.rotation.set(-Math.PI / 2, 0, 0);
    scene.updateMatrixWorld(true);
    const lift = LYING_HALF_THICKNESS + MAT_THICKNESS - lowestY(bones, Object.keys(bones) as BoneKey[]);
    scene.position.set(0, lift, LYING_CENTER_Z);
  }
  scene.updateMatrixWorld(true);
  return drop;
}

export function ExerciseAvatar({ onReady }: { onReady: (api: ExerciseAvatarApi) => void }) {
  const gltf = useGLTF(MUSCLE_RIG_URL);
  const model = useMemo(() => prepareMuscleModel(gltf.scene), [gltf]);
  // Orientations de repos, capturées une fois sur le squelette intact (avant toute pose).
  const rest = useMemo(() => captureRestPose(model.bones), [model]);
  const { gl, scene: rootScene, camera, size } = useThree();
  const seatRef = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.Mesh>(null);
  // Hauteur des pieds au repos (debout, mannequin intact) : référence du contact avec le sol.
  const restFeetY = useMemo(() => {
    model.scene.updateMatrixWorld(true);
    return lowestY(model.bones, FEET);
  }, [model]);

  const renderAt = useCallback(
    (exercise: Exercise, t: number) => {
      const position = exercise.position ?? "standing";
      applyPoseToSkeleton(model.bones, rest, withBasePose(position, samplePose(exercise, t)));
      const drop = placeBody(model.scene, model.bones, position, restFeetY);

      if (seatRef.current) {
        seatRef.current.visible = position === "seated";
        if (position === "seated") {
          const pelvis = model.bones.root.getWorldPosition(new THREE.Vector3());
          seatRef.current.position.set(pelvis.x, pelvis.y - SEAT_HEIGHT_BELOW_PELVIS - 0.02, pelvis.z);
        }
      }
      if (matRef.current) matRef.current.visible = position === "lying";

      const targets = new Set<string>(exercise.target_segments);
      model.routing.forEach((routing, index) => {
        const highlighted = routing.region !== null && targets.has(routing.region);
        model.materials[index].color.set(highlighted ? TARGET_COLOR : NEUTRAL_COLOR);
      });

      const framing = framingFor(exercise, drop);
      camera.position.copy(cameraPosition(exercise.view, framing));
      camera.lookAt(framing.target);
      (camera as THREE.PerspectiveCamera).updateProjectionMatrix();

      gl.render(rootScene, camera);
    },
    [model, rest, restFeetY, camera, gl, rootScene],
  );

  const snapshot = useCallback(() => gl.domElement.toDataURL("image/jpeg", 0.9), [gl]);

  // Annonce l'API une fois le modèle chargé ET le canvas mesuré (sinon le premier
  // rendu se ferait à une taille nulle).
  useEffect(() => {
    if (size.width > 0 && size.height > 0) onReady({ renderAt, snapshot });
  }, [renderAt, snapshot, onReady, size.width, size.height]);

  return (
    <>
      <color attach="background" args={[BACKGROUND_COLOR]} />
      <ambientLight intensity={1.1} />
      <directionalLight position={[2, 3, 4]} intensity={1.2} />
      <directionalLight position={[-2, 2, -3]} intensity={0.8} />
      <directionalLight position={[-3, 1, 3]} intensity={0.6} />
      <hemisphereLight args={["#ffffff", "#aab4c0", 0.5]} />
      <Floor />
      {/* Tabouret pour l'assis, tapis pour l'allongé : visibles selon la position (renderAt). */}
      <mesh ref={seatRef} visible={false}>
        <boxGeometry args={[0.5, 0.04, 0.42]} />
        <meshStandardMaterial color="#B8C2CE" />
      </mesh>
      <mesh ref={matRef} visible={false} position={[0, MAT_THICKNESS / 2, 0]}>
        <boxGeometry args={[0.75, MAT_THICKNESS, 2.1]} />
        <meshStandardMaterial color="#B8C2CE" />
      </mesh>
      <primitive object={model.scene} />
    </>
  );
}
