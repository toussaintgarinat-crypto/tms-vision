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
blender --background --python-exit-code 1 --python tools/blender/export_muscle_rig.py -- \
  /tmp/z-anatomy/Startup.blend \
  web/public/muscle-rig.glb
```

`--python-exit-code 1` est nécessaire : sans lui, `blender --background` avale les
exceptions Python (y compris `AssertionError`/`RuntimeError`) et quitte avec le
code 0 même quand le script a échoué avant la fin — le script contient ses
propres garde-fous (`assert obj.data.users == 1`, `RuntimeError` de
`rig_spec.resolve_muscle_objects`/`resolve_skeletal_landmarks` si un muscle ou
un repère squelettique attendu est introuvable) qui doivent pouvoir faire
échouer un pipeline CI/script shell en amont.

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
  Blender échoue de façon non déterministe sur 1 à 3 des 28 muscles
  upper_arm/forearm (les seuls qui passent encore par Automatic Weights)
  selon l'exécution ; les 26 muscles tronc/cou/cuisse (dont "Descending part
  of trapezius muscle", "Sternocleidomastoid muscle" et, depuis la
  correction de spec du 2026-09-21, tous les muscles de cuisse — "Rectus
  femoris muscle", "Vastus lateralis muscle", etc.) ne passent plus jamais
  par ce solveur du tout (poids rigide déterministe systématique, voir
  `export_muscle_rig.apply_rigid_weight`) et ne peuvent donc plus
  structurellement déclencher ce repli. Le script applique alors un
  rattachement rigide (poids 1.0) à l'os logique déjà connu — le muscle reste
  skinné à 100 %, juste sans diffusion de chaleur pour ces quelques objets.
  La liste exacte peut varier d'un run à l'autre.

**Quel muscle passe par quel chemin de poids** (voir `rig_spec.RIGID_WEIGHT_BONE_KEYS`
et la correction de spec du 2026-09-21 dans
`docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-design.md`) :
Automatic Weights (heat-diffusion) est utilisé UNIQUEMENT pour les muscles
`upper_arm`/`forearm` (28 objets, 2 côtés) — le seul cas réellement
bi-articulaire de ce squelette à 9 os (coude entre `L_upper_arm` et
`L_forearm`, et son symétrique droit). Tous les autres muscles — tronc,
cou (`rig_spec.TRUNK_NECK_MUSCLES`, 14 objets) et cuisse
(`rig_spec.LIMB_MUSCLES["thigh"]`, 12 objets, depuis le 2026-09-21) — passent
par le poids rigide déterministe (`apply_rigid_weight`), jamais par
Automatic Weights, parce qu'aucun d'eux ne traverse une seconde articulation
représentée dans ce squelette (pas d'os "jambe" sous la cuisse, pas de
second os sous le tronc/cou).

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
blender --background --python-exit-code 1 --python tools/blender/validate_muscle_rig.py -- \
  web/public/muscle-rig.glb
```

`--python-exit-code 1` est nécessaire ici aussi et pour la même raison qu'à
l'étape 2 : sans lui, un `assert` qui échoue dans ce script quitte quand même
avec le code 0 (comportement `--background` de Blender), ce qui rendrait
cette étape invisible à un pipeline CI/script shell qui teste le code de
sortie — vérifié empiriquement (exit 0 sans le flag sur un `.glb` invalide,
exit 1 avec le flag).

Sortie attendue (exacte) : `OK: 9 os, 54 maillages skinnés, binding
gauche/droite cohérent, poids rigide déterministe exact sur 26 objet(s)
(tronc/cou : 14, cuisse : 12 — couverture vérifiée), Automatic Weights
(upper_arm/forearm) sur 28 objet(s).` Le compte de maillages est une valeur
EXACTE (54), pas un plancher — voir `EXPECTED_MESH_COUNT` dans
`validate_muscle_rig.py`. Les comptes de 14 objets tronc/cou et 12 objets
cuisse sont eux aussi des valeurs EXACTES, dérivées (pas codées en dur) et
re-vérifiées chacune par une assertion de couverture séparée — voir
`EXPECTED_TRUNK_NECK_OBJECT_COUNT` et `EXPECTED_THIGH_OBJECT_COUNT` dans
`validate_muscle_rig.py`.
Le validateur vérifie aussi qu'aucun objet exporté ne partage son datablock
mesh avec un autre, et que l'os dominant de chaque objet `.l`/`.r` est bien
de son propre côté (ou un os non latéralisé — tronc/cou/racine). Toute
erreur (os manquant, maillage non skinné, datablock partagé, binding
gauche/droite incohérent, compte de maillages différent de 54, couverture du
contrôle tronc/cou ou cuisse incorrecte) fait échouer le script (`assert`,
code de sortie différent de 0 GRÂCE À `--python-exit-code 1` ci-dessus) — ne
pas committer le `.glb` si cette étape échoue.

## 4. Vérification visuelle

Ouvrir `web/public/muscle-rig.glb` dans un viewer glTF (ex.
https://gltf-viewer.donmccurdy.com/, ou Blender) : vérifier l'absence de
déformation aberrante ou de bavure de poids visible aux jointures avant de
committer. Corriger manuellement dans Blender si besoin (repeindre les poids
des muscles concernés), ré-exporter, puis relancer l'étape 3.
