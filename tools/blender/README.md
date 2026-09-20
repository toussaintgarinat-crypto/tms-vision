# Export du rig musculaire (Tranche 3)

Génère `web/public/muscle-rig.glb` à partir des maillages Z-Anatomy. Étape
manuelle, exécutée une fois (ou à chaque changement du sous-ensemble de
muscles ou de la hiérarchie d'os) — pas embarquée dans l'application.

## 1. Télécharger la source Z-Anatomy

Le fichier source (`Startup.blend`, ~293 Mo) n'est PAS commité au dépôt.

```bash
curl -L -o /tmp/Z-Anatomy.zip \
  https://github.com/Z-Anatomy/The-blend/raw/master/Z-Anatomy.zip
unzip -o /tmp/Z-Anatomy.zip -d /tmp/z-anatomy
# Fichier attendu : /tmp/z-anatomy/Startup.blend
```

Si ce lien a changé (nom de branche, chemin du zip), vérifier
https://github.com/Z-Anatomy/The-blend avant de lancer la commande.

## 2. Exporter le rig

```bash
blender --background --python tools/blender/export_muscle_rig.py -- \
  /tmp/z-anatomy/Startup.blend \
  web/public/muscle-rig.glb
```

Sortie normale d'un run réussi (ne pas confondre avec un échec) : le script
imprime deux lignes `ATTENTION :`, attendues et sans conséquence sur la
validité du rig —

- `ATTENTION : 1 objet(s) exclu(s) de l'export (géométrie dégénérée, 0 face
  — voir is_degenerate_mesh) : ['Erector spinae.j']` — le seul objet
  "Erector spinae" du fichier source est un stub cassé (2 sommets, 0 face),
  exclu avant l'export plutôt que laissé à l'exportateur glTF (qui le
  remplacerait silencieusement par un icosphère). D'où 54 muscles exportés,
  pas 55.
- `ATTENTION : repli poids rigide appliqué (Bone Heat Weighting sans
  solution) pour N objet(s) : [...]` — le solveur de diffusion de chaleur de
  Blender échoue de façon non déterministe sur 1 à 3 des 54 muscles selon
  l'exécution (observé notamment sur "Descending part of trapezius muscle"
  et "Sternocleidomastoid muscle"). Le script applique alors un rattachement
  rigide (poids 1.0) à l'os logique déjà connu — le muscle reste skinné à
  100 %, juste sans diffusion de chaleur pour ces quelques objets. La liste
  exacte peut varier d'un run à l'autre.

Avant `parent_set(ARMATURE_AUTO)`, le script dédoublonne aussi tout
datablock mesh partagé entre plusieurs objets exportés (`obj.data.copy()`
si `obj.data.users > 1`) : Z-Anatomy lie certains objets `.l`/`.r` au même
datablock (duplicata liés, miroir par la matrice d'objet), et les poids de
vertex vivant dans le datablock, un partage non corrigé fait que Automatic
Weights écrase les poids d'un côté par ceux de l'autre pour toute la paire
— voir la correction du 2026-09-20 dans
`docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-design.md`.

## 3. Valider le fichier exporté

```bash
blender --background --python tools/blender/validate_muscle_rig.py -- \
  web/public/muscle-rig.glb
```

Sortie attendue (exacte) : `OK: 9 os, 54 maillages skinnés, binding
gauche/droite cohérent.` Le compte de maillages est une valeur EXACTE (54),
pas un plancher — voir `EXPECTED_MESH_COUNT` dans `validate_muscle_rig.py`.
Le validateur vérifie aussi qu'aucun objet exporté ne partage son datablock
mesh avec un autre, et que l'os dominant de chaque objet `.l`/`.r` est bien
de son propre côté (ou un os non latéralisé — tronc/cou/racine). Toute
erreur (os manquant, maillage non skinné, datablock partagé, binding
gauche/droite incohérent, compte de maillages différent de 54) fait échouer
le script (`assert`, code de sortie différent de 0) — ne pas committer le
`.glb` si cette étape échoue.

## 4. Vérification visuelle

Ouvrir `web/public/muscle-rig.glb` dans un viewer glTF (ex.
https://gltf-viewer.donmccurdy.com/, ou Blender) : vérifier l'absence de
déformation aberrante ou de bavure de poids visible aux jointures avant de
committer. Corriger manuellement dans Blender si besoin (repeindre les poids
des muscles concernés), ré-exporter, puis relancer l'étape 3.
