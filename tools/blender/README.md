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

## 3. Valider le fichier exporté

```bash
blender --background --python tools/blender/validate_muscle_rig.py -- \
  web/public/muscle-rig.glb
```

Sortie attendue : `OK: 9 os, N maillages skinnés.` (N >= 20). Toute erreur
(os manquant, maillage non skinné) fait échouer le script (`assert`, code de
sortie différent de 0) — ne pas committer le `.glb` si cette étape échoue.

## 4. Vérification visuelle

Ouvrir `web/public/muscle-rig.glb` dans un viewer glTF (ex.
https://gltf-viewer.donmccurdy.com/, ou Blender) : vérifier l'absence de
déformation aberrante ou de bavure de poids visible aux jointures avant de
committer. Corriger manuellement dans Blender si besoin (repeindre les poids
des muscles concernés), ré-exporter, puis relancer l'étape 3.
