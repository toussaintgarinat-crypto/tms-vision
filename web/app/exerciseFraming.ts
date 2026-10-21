import * as THREE from "three";
import type { Exercise } from "./exercisePose";

// Cadrage de la caméra d'une vidéo d'exercice. Mesuré sur le vrai muscle-rig.glb (corps complet) :
// le corps s'étend de y = 0 (pieds) à y = 1,70 (sommet du crâne), x de -0,36 à 0,36 (mains).
// Le titre occupe le haut de l'image et la consigne le bas : le corps entier doit tenir entre les
// deux, avec un peu de place au-dessus pour un bras levé.
export type Framing = { target: THREE.Vector3; distance: number };

const FULL_BODY: Framing = { target: new THREE.Vector3(0, 1.0, 0), distance: 3.9 };
// Zooms pour les exercices dont la cible est petite : sans eux, une main ne ferait que 40 pixels.
const HEAD: Framing = { target: new THREE.Vector3(0, 1.5, 0), distance: 1.7 };
const HANDS: Framing = { target: new THREE.Vector3(0, 1.2, 0.1), distance: 2.6 };
const FEET: Framing = { target: new THREE.Vector3(0, 0.7, 0.25), distance: 3.0 };

export function framingFor(exercise: Pick<Exercise, "target_segments">): Framing {
  const regions = exercise.target_segments;
  const only = (...allowed: string[]) => regions.every((region) => allowed.includes(region));
  if (only("head", "neck")) return HEAD;
  if (only("hand", "lower_arm")) return HANDS;
  if (only("foot")) return FEET;
  return FULL_BODY;
}

// Position de la caméra pour une vue, à la distance du cadrage.
export function cameraPosition(view: Exercise["view"], framing: Framing): THREE.Vector3 {
  const { target, distance } = framing;
  switch (view) {
    // Face au sujet (son avant est +z).
    case "front":
      return new THREE.Vector3(target.x, target.y, target.z + distance);
    // Côté droit du sujet (-x) : il regarde vers la droite de l'image.
    case "side":
      return new THREE.Vector3(target.x - distance, target.y, target.z);
    case "three_quarter":
      return new THREE.Vector3(
        target.x - distance * 0.6,
        target.y + 0.1,
        target.z + distance * 0.8,
      );
  }
}
