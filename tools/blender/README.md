# Export du rig musculaire du corps complet

Génère `web/public/muscle-rig.glb` à partir des maillages Z-Anatomy : un squelette de **24 os** et
environ **360 muscles** (tout le corps : tête, cou, tronc, épaules, bras, mains, hanches, jambes,
pieds). Étape manuelle, exécutée une fois (ou à chaque changement de la liste des muscles ou de la
hiérarchie d'os), pas embarquée dans l'application. Conception : voir
`docs/superpowers/specs/2026-10-22-avatar-corps-complet-design.md`.

## 1. Télécharger la source Z-Anatomy

Le fichier source (`Startup.blend`, ~300 Mo) n'est PAS commité au dépôt. Il est dans l'archive
`Z-Anatomy.zip` (~87 Mo) du dépôt https://github.com/Z-Anatomy/The-blend :

```bash
git clone --depth 1 https://github.com/Z-Anatomy/the-blend /tmp/the-blend
unzip -o /tmp/the-blend/Z-Anatomy.zip -d /tmp/z-anatomy
# Fichier attendu : /tmp/z-anatomy/Z-Anatomy/Startup.blend
```

Blender 4.2 LTS suffit (testé avec 4.2.3 : https://download.blender.org/release/Blender4.2/).

## 2. Exporter le rig

```bash
blender --background --python-exit-code 1 --python tools/blender/export_muscle_rig.py -- \
  /tmp/z-anatomy/Z-Anatomy/Startup.blend \
  web/public/muscle-rig.glb
```

`--python-exit-code 1` est nécessaire : sans lui, `blender --background` quitte avec le code 0 même
quand le script a échoué. Compter **5 à 15 minutes**, sans sortie pendant le calcul des poids.

Ce que fait le script :

- **Os.** Les 24 os (`rig_spec.BONE_ORDER`, même ordre que `web/app/pose3dSkeleton.ts`) sont placés
  d'après les vrais os de Z-Anatomy (tête du fémur, condyles, malléoles, métacarpes, phalanges...). Les
  positions sont imprimées dans le journal : les relire après toute modification.
- **Muscles.** `rig_spec.MUSCLES` liste chaque muscle avec sa chaîne d'os et sa région. Un nom
  introuvable fait échouer le script en les listant tous. Les variantes `.el/.er/.ol/.or` (vue
  éclatée, contours) sont ignorées. Exclus : visage, yeux, langue, larynx, pharynx, oreille, plancher
  pelvien, muscles intercostaux (très lourds), fascias et tendons.
- **Poids de peau, sans Automatic Weights** (le solveur de Blender était non déterministe). Pour
  chaque sommet : une zone de fondu autour de chaque articulation de la chaîne, mesurée le long de
  l'axe de l'os distal (`BLEND_HALF_WIDTH`), sauf à l'épaule où elle dépend de la distance à
  l'humérus (`PROXIMITY_JOINTS`) : un plan entraînerait avec le bras tout le grand dorsal et les
  pectoraux, qui couvrent le tronc. Un muscle à un seul os est rigide à 100 %.
- **Simplification.** Chaque muscle est ramené à 1 500 sommets au plus (`MAX_VERTICES_PER_MUSCLE`),
  pour tenir dans 25 Mo.
- **Matériau.** Un matériau simple partagé : les matériaux de Z-Anatomy font échouer l'export glTF
  pour certains muscles, et l'application recolore de toute façon chaque muscle.
- **Région et côté.** Chaque muscle porte sa région et son côté (`region`, `side`) comme propriété
  personnalisée, exportée dans les `extras` glTF et lue par `muscleSegments.ts` (`userData`).

Sortie normale : la liste des 24 os avec leurs positions, puis `N muscles, M sommets après
simplification.` et `Export terminé`. Le message `Error: Not freed memory blocks` à la toute fin de
Blender est sans conséquence.

## 3. Valider le fichier exporté

```bash
cd web && npx vitest run app/muscleRigInvariants.test.ts
```

Le test charge le vrai `.glb` et vérifie : nombre exact de muscles (à mettre à jour dans le test si
la liste change), taille inférieure à 25 Mo, 24 os aux noms attendus, région et côté de chaque muscle,
toutes les régions présentes des deux côtés, poids de peau de somme 1 sur chaque sommet, côté déclaré
cohérent avec l'os dominant et avec la position du muscle (gauche en +x). Ne pas committer le `.glb` si
ce test échoue.

## 4. Vérification visuelle

```bash
cd web && npm run dev                      # dans un terminal
node scripts/snapshot-exercise.mjs --definition ../exercises/<exercice>.json --out /tmp/vue
```

Ouvrir les images produites (une par pose clé) : chercher les étirements aberrants de muscles aux
articulations (épaule, hanche, poignet, cheville). Corriger `BLEND_HALF_WIDTH` ou `PROXIMITY_JOINTS`
dans `rig_spec.py`, ré-exporter, relancer l'étape 3.
