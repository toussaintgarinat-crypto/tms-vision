# Avatar du corps complet : plan d'implémentation (Tranche 4)

Spec : `docs/superpowers/specs/2026-10-22-avatar-corps-complet-design.md`. Ordre : le rig d'abord (tout
dépend du fichier 3D), puis le code web, puis le format et le contenu des exercices, puis la documentation.

## Tâche 1 : le rig (Blender)

- `tools/blender/rig_spec.py` : 24 os, hiérarchie, positions déduites des os réels de Z-Anatomy,
  table de 179 entrées `(muscle, chaîne d'os, région)` (358 objets, côtés gauche et droit), zones de
  fondu et articulations pondérées par proximité.
- `tools/blender/export_muscle_rig.py` : armature, simplification (1 500 sommets au plus), poids par
  zone d'articulation, un matériau simple partagé, région et côté dans les `extras` glTF.
- Sortie : `web/public/muscle-rig.glb` (moins de 25 Mo).
- Vérification : `muscleRigInvariants.test.ts` sur le vrai fichier.

## Tâche 2 : le code web

- `pose3dSkeleton.ts` : `BONE_ORDER` à 24 os, `PARENT_OF`, `BONE_LENGTH`, points de repère MediaPipe
  des nouveaux os ; les os sans point (tête, clavicule, doigts, orteils) suivent leur parent.
- `exercisePose.ts` : angles relatifs au parent, troisième angle `twist`, régions.
- `muscleSegments.ts` : région et côté lus dans `userData` (repli : os dominant).
- `exerciseFraming.ts` : cadrage automatique (corps entier, ou zoom tête, mains, pieds).
- Tests mis à jour et ajoutés dans chacun de ces modules.

## Tâche 3 : format et contenu des exercices

- `src/tms_vision/exercises.py` : 23 os, trois angles, onze régions (les quatre zones RULA restent
  `ZONES`, utilisées par le programme d'étirements).
- Migration des quatre exercices existants aux angles relatifs ; treize nouveaux exercices.
- `web/scripts/snapshot-exercise.mjs` : images fixes d'un exercice pour le contrôle visuel.

## Tâche 4 : documentation

`README.md`, `exercises/README.md`, `tools/blender/README.md`, `NOTICE.md`.

## Suite : Tranche 5 (faite)

Mains et pieds mesurés par vidéo : voir `docs/superpowers/specs/2026-10-22-mains-pieds-design.md`.
Il reste à calibrer les seuils avec l'ostéopathe.
