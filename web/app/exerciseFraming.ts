import * as THREE from "three";
import type { Exercise } from "./exercisePose";

// Cadrage de la caméra d'une vidéo d'exercice. Mesuré sur le vrai muscle-rig.glb (corps complet) :
// le corps s'étend de y = 0 (pieds) à y = 1,70 (sommet du crâne), x de -0,36 à 0,36 (mains).
// Le titre occupe le haut de l'image (jusqu'à ~85 px sur 640) et la consigne le bas (à partir de
// ~535 px) : le corps entier, des pieds (~520 px) au crâne (~95 px), tient entre les deux.
export type Framing = { target: THREE.Vector3; distance: number };

const FULL_BODY: Framing = { target: new THREE.Vector3(0, 0.8, 0), distance: 3.5 };
// Zooms pour les exercices dont la cible est petite : sans eux, une main ne ferait que 40 pixels.
const HEAD: Framing = { target: new THREE.Vector3(0, 1.5, 0), distance: 1.7 };
const HANDS: Framing = { target: new THREE.Vector3(0, 1.2, 0.1), distance: 2.6 };
const FEET: Framing = { target: new THREE.Vector3(0, 0.7, 0.25), distance: 3.0 };

// Allongé sur le dos : le corps est horizontal (tête vers -z, pieds vers +z, voir ExerciseAvatar),
// centré sur l'origine et d'environ 1,70 m de long. Pas de zoom : tout le corps, de profil.
const LYING: Framing = { target: new THREE.Vector3(0, 0.3, 0), distance: 3.4 };

// `drop` : de combien le mannequin est descendu (assis), pour garder le cadrage sur lui.
export function framingFor(
  exercise: Pick<Exercise, "target_segments" | "position">,
  drop = 0,
): Framing {
  if (exercise.position === "lying") return LYING;
  const framing = standingFraming(exercise.target_segments);
  if (drop === 0) return framing;
  return { target: framing.target.clone().add(new THREE.Vector3(0, -drop, 0)), distance: framing.distance };
}

function standingFraming(regions: Exercise["target_segments"]): Framing {
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
