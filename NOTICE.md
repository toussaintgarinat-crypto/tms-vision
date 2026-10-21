# NOTICE

Ce projet inclut des maillages musculaires 3D dérivés de **Z-Anatomy**
(https://github.com/Z-Anatomy/The-blend), lui-même dérivé de **BodyParts3D**
(Database Center for Life Science, https://lifesciencedb.jp/bp3d/).

Fichier concerné : `web/public/muscle-rig.glb`, extrait et exporté par
`tools/blender/export_muscle_rig.py` à partir de `Startup.blend` (Z-Anatomy),
sous-ensemble d'environ 17 groupes musculaires majeurs (voir
`docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-design.md`).

Licence : Creative Commons Attribution-ShareAlike 4.0 International
(CC BY-SA 4.0) — https://creativecommons.org/licenses/by-sa/4.0/

Toute redistribution de `muscle-rig.glb` (ou d'un dérivé) doit conserver
cette attribution et rester sous licence CC BY-SA 4.0.

## Vidéos d'exercices générées

Les vidéos d'étirement produites par `python -m tms_vision.capsule_build` montrent ces maillages
musculaires : ce sont des œuvres dérivées d'un matériau sous licence CC BY-SA 4.0. Chaque vidéo
incruste le crédit « Modèle musculaire dérivé de Z-Anatomy (BodyParts3D), licence CC BY-SA 4.0 ».
Avant toute diffusion, vérifier les obligations de la licence (attribution, partage dans les mêmes
conditions) pour l'usage prévu, en particulier commercial.
