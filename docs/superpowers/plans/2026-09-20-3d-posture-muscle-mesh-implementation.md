# Avatar 3D — Tranche 3 (vrais maillages musculaires) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le maillage de test (cylindres) de la Tranche 2 par de vrais maillages musculaires Z-Anatomy, skinnés sur le squelette articulé existant, via un pipeline Blender → glTF.

**Architecture:** Un script Blender headless (`tools/blender/export_muscle_rig.py`) construit une armature (même hiérarchie/noms d'os que `pose3dSkeleton.ts`), y rattache ~17 groupes musculaires Z-Anatomy via l'algorithme **Automatic Weights** de Blender, puis exporte le tout en `.glb`. `PostureAvatar3D.tsx` charge ce `.glb` au runtime (`useGLTF`), retrouve les os par nom, et leur applique exactement le même calcul de rotation par frame qu'en Tranche 2 (`applyFrameToSkeleton`, inchangé).

**Tech Stack:** Blender 4.5 LTS (scripting Python `bpy`, déjà installé — `blender --version` → `Blender 4.5.14 LTS`), Three.js/`@react-three/fiber`/`@react-three/drei` (déjà en place), Next.js/TypeScript.

## Global Constraints

- `pose3dSkeleton.ts` n'est **pas modifié** dans cette tranche — `applyFrameToSkeleton` est réutilisé tel quel.
- Aucun skinning fait main : uniquement l'algorithme **Automatic Weights** de Blender (`bpy.ops.object.parent_set(type='ARMATURE_AUTO')`), pas de poids codés à la main.
- Sous-ensemble de muscles **fixé** à la liste de la spec (~17 groupes, voir Task 2) — pas la musculature complète (~600 muscles), hors périmètre.
- Sélection de muscle : suffixes `.l`/`.r` exacts uniquement — jamais `.el`/`.er`/`.ol`/`.or` (variantes/LOD repérées pendant le brainstorming).
- Erreur explicite (le script s'arrête, pas de `try/except` silencieux) si un objet muscle attendu est introuvable, ou si un `BoneKey` attendu est absent du `.glb` exporté — jamais de sous-ensemble partiel silencieux.
- `Startup.blend` (source Z-Anatomy, ~293 Mo) **n'est jamais commité**. Seul `web/public/muscle-rig.glb` (résultat de l'export) est commité.
- Attribution CC BY-SA 4.0 obligatoire : `NOTICE.md` + mention visible dans l'UI près de l'avatar.
- Couleur uniforme par frame (celle de l'`action_level` courant) appliquée à **tous** les matériaux importés — pas de coloration par muscle (reportée à une Tranche 4 future).
- Correctifs manuels ponctuels après Automatic Weights sont attendus et acceptés, pas un signe d'échec du pipeline.

## Note d'implémentation — écart documenté par rapport au libellé littéral de la spec

La spec (section « Détail — `tools/blender/export_muscle_rig.py` ») décrit la construction de
l'armature comme répliquant `BONE_LENGTH`/`BONE_SPECS` de `pose3dSkeleton.ts` « exactement comme
`buildSkeleton()` le fait ». Or `buildSkeleton()` construit une pose de repos **dégénérée** :
tous les os empilés le long d'un seul axe vertical (`position.set(0, BONE_LENGTH[parent], 0)`,
sans écart latéral gauche/droite), parce qu'en Tranche 2 seule la *rotation* par frame compte —
`applyFrameToSkeleton` écrase la rotation locale de chaque os avec une valeur calculée en espace
monde à partir des landmarks (`swingQuaternion`), indépendamment de l'orientation de repos
importée. Reproduire cette pose dégénérée dans l'armature Blender placerait les os loin de la
géométrie réelle des muscles Z-Anatomy (bras/jambes écartés du corps), ce qui casserait le calcul
Automatic Weights (diffusion de chaleur basée sur la proximité géométrie ↔ os).

**Décision prise dans ce plan** : les os sont positionnés à partir de la **bounding box monde
réelle** des objets muscle qui leur sont assignés (voir Task 3, `bone_head_tail`), pas depuis les
longueurs fixes `BONE_LENGTH`. Ce qui est répliqué à l'identique — et c'est la seule chose dont
`PostureAvatar3D.tsx` a réellement besoin au runtime — c'est **la hiérarchie et les 9 noms de
`BoneKey`** (`BONE_ORDER`/`PARENT_OF` dans `tools/blender/rig_spec.py`, Task 2). Cet écart est
sans risque pour le contrat runtime : `applyFrameToSkeleton` ignore de toute façon l'orientation de
repos importée.

---

## Task 1 : Attribution — `NOTICE.md` et `tools/blender/README.md`

**Files:**
- Create: `NOTICE.md`
- Create: `tools/blender/README.md`

**Interfaces:**
- Produces: instructions de téléchargement/exécution que Task 5 (exécution réelle du pipeline) suit littéralement.

- [ ] **Step 1: Écrire `NOTICE.md`**

```markdown
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
```

- [ ] **Step 2: Écrire `tools/blender/README.md`**

```markdown
# Export du rig musculaire (Tranche 3)

Génère `web/public/muscle-rig.glb` à partir des maillages Z-Anatomy. Étape
manuelle, exécutée une fois (ou à chaque changement du sous-ensemble de
muscles ou de la hiérarchie d'os) — pas embarquée dans l'application.

## 1. Télécharger la source Z-Anatomy

Le fichier source (`Startup.blend`, ~293 Mo) n'est PAS commité au dépôt.

\`\`\`bash
curl -L -o /tmp/Z-Anatomy.zip \
  https://github.com/Z-Anatomy/The-blend/raw/master/Z-Anatomy.zip
unzip -o /tmp/Z-Anatomy.zip -d /tmp/z-anatomy
# Fichier attendu : /tmp/z-anatomy/Startup.blend
\`\`\`

Si ce lien a changé (nom de branche, chemin du zip), vérifier
https://github.com/Z-Anatomy/The-blend avant de lancer la commande.

## 2. Exporter le rig

\`\`\`bash
blender --background --python tools/blender/export_muscle_rig.py -- \
  /tmp/z-anatomy/Startup.blend \
  web/public/muscle-rig.glb
\`\`\`

## 3. Valider le fichier exporté

\`\`\`bash
blender --background --python tools/blender/validate_muscle_rig.py -- \
  web/public/muscle-rig.glb
\`\`\`

Sortie attendue : `OK: 9 os, N maillages skinnés.` (N >= 20). Toute erreur
(os manquant, maillage non skinné) fait échouer le script (`assert`, code de
sortie différent de 0) — ne pas committer le `.glb` si cette étape échoue.

## 4. Vérification visuelle

Ouvrir `web/public/muscle-rig.glb` dans un viewer glTF (ex.
https://gltf-viewer.donmccurdy.com/, ou Blender) : vérifier l'absence de
déformation aberrante ou de bavure de poids visible aux jointures avant de
committer. Corriger manuellement dans Blender si besoin (repeindre les poids
des muscles concernés), ré-exporter, puis relancer l'étape 3.
```

- [ ] **Step 3: Commit**

```bash
git add NOTICE.md tools/blender/README.md
git commit -m "docs: attribution CC BY-SA et instructions d'export du rig musculaire (tranche 3)"
```

---

## Task 2 : `tools/blender/rig_spec.py` — hiérarchie d'os et table de sélection des muscles

**Files:**
- Create: `tools/blender/rig_spec.py`

**Interfaces:**
- Consumes: rien (module de données pur, s'exécute dans l'interpréteur Python embarqué de Blender — `bpy`/`mathutils` disponibles).
- Produces: `BONE_ORDER: list[str]`, `PARENT_OF: dict[str, str]`, `ASCENDING_BONES: set[str]`, `resolve_muscle_objects() -> dict[str, list[bpy.types.Object]]`, `combined_world_bbox(objects) -> tuple[Vector, Vector]`, `bone_head_tail(objects, ascending: bool) -> tuple[Vector, Vector]` — consommés par Task 3 (`export_muscle_rig.py`) et Task 4 (`validate_muscle_rig.py`, pour `BONE_ORDER` uniquement).

- [ ] **Step 1: Écrire `tools/blender/rig_spec.py`**

```python
"""Hiérarchie d'os et table de sélection des muscles Z-Anatomy pour la
Tranche 3 de l'avatar 3D. Dupliqué intentionnellement depuis
`web/app/pose3dSkeleton.ts` (BONE_ORDER/PARENT_OF ci-dessous) : pas de
partage de source entre TypeScript et Blender, à tenir synchronisé
manuellement si le squelette de `pose3dSkeleton.ts` change.

Ce module s'exécute UNIQUEMENT dans l'interpréteur Python embarqué de
Blender (`blender --background --python ...`) : `bpy`/`mathutils` ne sont
pas installables via pip standard.
"""

import bpy
from mathutils import Vector

# Même 9 clés, même ordre que `BONE_ORDER` dans web/app/pose3dSkeleton.ts.
BONE_ORDER = [
    "root",
    "spine",
    "neck",
    "L_upper_arm",
    "L_forearm",
    "R_upper_arm",
    "R_forearm",
    "L_thigh",
    "R_thigh",
]

# Même relations parent-enfant que `BONE_SPECS` dans pose3dSkeleton.ts.
PARENT_OF = {
    "spine": "root",
    "neck": "spine",
    "L_upper_arm": "spine",
    "L_forearm": "L_upper_arm",
    "R_upper_arm": "spine",
    "R_forearm": "R_upper_arm",
    "L_thigh": "root",
    "R_thigh": "root",
}

# Os "ascendants" (tronc/cou : la tête de l'os est en bas, la queue en haut)
# vs. os de membre (la tête est en haut/proximal, la queue en bas/distal).
# Voir `bone_head_tail` ci-dessous.
ASCENDING_BONES = {"spine", "neck"}

# Muscles du tronc/cou : pas de bone gauche/droite séparé, donc les variantes
# `.l` ET `.r` (si les deux existent) sont toutes les deux rattachées au même
# os. Noms vérifiés dans Startup.blend pendant le brainstorming de la
# Tranche 3 (voir la spec, section "Liste des muscles retenus").
TRUNK_NECK_MUSCLES = {
    "spine": [
        "Erector spinae",
        "Rectus abdominis muscle",
        "External abdominal oblique muscle",
        "Latissimus dorsi muscle",
    ],
    "neck": [
        "Ascending part of trapezius muscle",
        "Transverse part of trapezius muscle",
        "Descending part of trapezius muscle",
        "Sternocleidomastoid muscle",
    ],
}

# Muscles de membre : une entrée par catégorie de membre ("upper_arm",
# "forearm", "thigh"), appliquée aux deux côtés (L_<catégorie>/R_<catégorie>).
# mode "exact" : nom d'objet vérifié tel quel dans la spec.
# mode "contains" : le Deltoïde a 3 parties dont les noms d'objet exacts
# n'ont PAS été vérifiés pendant le brainstorming (seule la structure
# "3 parties, comme le trapèze" est confirmée) — on sélectionne donc par
# sous-chaîne "deltoid" (insensible à la casse) plutôt que d'inventer des
# noms exacts non vérifiés. `resolve_muscle_objects` échoue explicitement si
# aucune part n'est trouvée pour un côté donné.
LIMB_MUSCLES = {
    "upper_arm": [
        ("deltoid", "contains"),
        ("Biceps brachii muscle", "exact"),
        ("Triceps brachii muscle", "exact"),
    ],
    "forearm": [
        ("Brachioradialis", "exact"),
        ("Flexor carpi ulnaris", "exact"),
        ("Extensor carpi ulnaris", "exact"),
        ("Extensor digitorum", "exact"),
    ],
    "thigh": [
        ("Quadriceps femoris muscle", "exact"),
        ("Biceps femoris muscle", "exact"),
    ],
}

LIMB_BONE_OF = {
    "L": {"upper_arm": "L_upper_arm", "forearm": "L_forearm", "thigh": "L_thigh"},
    "R": {"upper_arm": "R_upper_arm", "forearm": "R_forearm", "thigh": "R_thigh"},
}

_EXCLUDED_SUFFIXES = {"el", "er", "ol", "or"}


def _mesh_objects_by_exact_name(name: str) -> list:
    return [obj for obj in bpy.data.objects if obj.type == "MESH" and obj.name == name]


def _mesh_objects_by_side_suffix(base_name: str, side: str, mode: str) -> list:
    """side: 'l' ou 'r'. mode: 'exact' (nom == f"{base_name}.{side}") ou
    'contains' (nom se termine par f".{side}" et contient base_name, sans
    casse). Dans les deux cas, les suffixes `.el`/`.er`/`.ol`/`.or` sont
    explicitement exclus (variantes/LOD repérées pendant le brainstorming)."""
    target_suffix = f".{side}"
    matches = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.name.endswith(target_suffix):
            continue
        stem = obj.name[: -len(target_suffix)]
        stem_suffix = stem.rsplit(".", 1)[-1] if "." in stem else ""
        if stem_suffix in _EXCLUDED_SUFFIXES:
            continue
        if mode == "exact" and stem == base_name:
            matches.append(obj)
        elif mode == "contains" and base_name.lower() in stem.lower():
            matches.append(obj)
    return matches


def resolve_muscle_objects() -> dict:
    """Retourne {bone_key: [objets muscle assignés]}. Lève RuntimeError avec
    un message explicite si un muscle attendu est introuvable — jamais de
    sous-ensemble partiel silencieux (contrainte de la spec)."""
    result: dict = {key: [] for key in BONE_ORDER if key != "root"}

    for bone_key, base_names in TRUNK_NECK_MUSCLES.items():
        for base_name in base_names:
            found = _mesh_objects_by_exact_name(f"{base_name}.l")
            found += _mesh_objects_by_exact_name(f"{base_name}.r")
            if not found:
                # Repli : objet médian unique, sans suffixe de côté.
                found = _mesh_objects_by_exact_name(base_name)
            if not found:
                raise RuntimeError(
                    f"Muscle '{base_name}' introuvable pour l'os '{bone_key}' "
                    f"(essayé '{base_name}.l', '{base_name}.r', '{base_name}')."
                )
            result[bone_key].extend(found)

    for side in ("L", "R"):
        side_suffix = side.lower()
        for category, entries in LIMB_MUSCLES.items():
            bone_key = LIMB_BONE_OF[side][category]
            for base_name, mode in entries:
                found = _mesh_objects_by_side_suffix(base_name, side_suffix, mode)
                if not found:
                    raise RuntimeError(
                        f"Muscle '{base_name}' (mode={mode}) introuvable pour "
                        f"l'os '{bone_key}' (suffixe .{side_suffix})."
                    )
                result[bone_key].extend(found)

    return result


def combined_world_bbox(objects: list) -> tuple:
    """Bounding box monde combinée d'une liste d'objets mesh. Lève
    ValueError si `objects` est vide."""
    if not objects:
        raise ValueError("combined_world_bbox: liste d'objets vide.")
    min_corner = Vector((float("inf"),) * 3)
    max_corner = Vector((float("-inf"),) * 3)
    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            min_corner = Vector(min(a, b) for a, b in zip(min_corner, world_corner))
            max_corner = Vector(max(a, b) for a, b in zip(max_corner, world_corner))
    return min_corner, max_corner


def bone_head_tail(objects: list, ascending: bool) -> tuple:
    """Dérive tête/queue d'un os depuis la bounding box monde réelle des
    objets qui lui sont assignés (voir la Note d'implémentation du plan pour
    la justification de cet écart par rapport à BONE_LENGTH). `ascending`
    True pour les os de tronc (tête en bas, queue en haut), False pour les
    os de membre (tête en haut/proximal, queue en bas/distal)."""
    min_corner, max_corner = combined_world_bbox(objects)
    center_x = (min_corner.x + max_corner.x) / 2
    center_y = (min_corner.y + max_corner.y) / 2
    if ascending:
        head = Vector((center_x, center_y, min_corner.z))
        tail = Vector((center_x, center_y, max_corner.z))
    else:
        head = Vector((center_x, center_y, max_corner.z))
        tail = Vector((center_x, center_y, min_corner.z))
    return head, tail
```

- [ ] **Step 2: Vérifier la syntaxe (sans le fichier Startup.blend)**

```bash
blender --background --python-expr "import sys; sys.path.insert(0, 'tools/blender'); import rig_spec; print('rig_spec importé sans erreur, BONE_ORDER =', rig_spec.BONE_ORDER)"
```

Attendu : `rig_spec importé sans erreur, BONE_ORDER = ['root', 'spine', 'neck', 'L_upper_arm', 'L_forearm', 'R_upper_arm', 'R_forearm', 'L_thigh', 'R_thigh']` (ce test ne peut pas exercer `resolve_muscle_objects()`, qui a besoin du fichier réel — couvert par Task 5).

- [ ] **Step 3: Commit**

```bash
git add tools/blender/rig_spec.py
git commit -m "feat: table de hiérarchie d'os et de sélection des muscles Z-Anatomy (tranche 3)"
```

---

## Task 3 : `tools/blender/export_muscle_rig.py` — construction de l'armature et export

**Files:**
- Create: `tools/blender/export_muscle_rig.py`

**Interfaces:**
- Consumes: `rig_spec.BONE_ORDER`, `rig_spec.PARENT_OF`, `rig_spec.ASCENDING_BONES`, `rig_spec.resolve_muscle_objects`, `rig_spec.bone_head_tail` (Task 2).
- Produces: `<output_glb_path>` (fichier `.glb`, argument CLI) — consommé par Task 4 (validation) et Task 6 (`PostureAvatar3D.tsx`, via `web/public/muscle-rig.glb`).

- [ ] **Step 1: Écrire `tools/blender/export_muscle_rig.py`**

```python
"""Construit une armature (même hiérarchie que web/app/pose3dSkeleton.ts),
y rattache le sous-ensemble de muscles Z-Anatomy défini dans rig_spec.py via
Automatic Weights, puis exporte le tout en .glb.

Usage (voir tools/blender/README.md) :
    blender --background --python tools/blender/export_muscle_rig.py -- \
        <chemin/vers/Startup.blend> <chemin/de/sortie/muscle-rig.glb>
"""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).parent))
import rig_spec  # noqa: E402


def parse_args() -> tuple[str, str]:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    if len(argv) != 2:
        raise SystemExit(
            "Usage: blender --background --python export_muscle_rig.py -- "
            "<Startup.blend> <sortie.glb>"
        )
    return argv[0], argv[1]


def build_armature(bone_positions: dict) -> bpy.types.Object:
    armature_data = bpy.data.armatures.new("MuscleRigArmature")
    armature_obj = bpy.data.objects.new("MuscleRigArmature", armature_data)
    bpy.context.scene.collection.objects.link(armature_obj)
    bpy.context.view_layer.objects.active = armature_obj

    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature_data.edit_bones
    created = {}
    for bone_key in rig_spec.BONE_ORDER:
        eb = edit_bones.new(bone_key)
        head, tail = bone_positions[bone_key]
        eb.head = head
        eb.tail = tail
        created[bone_key] = eb
    for bone_key, parent_key in rig_spec.PARENT_OF.items():
        created[bone_key].parent = created[parent_key]
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature_obj


def main() -> None:
    startup_blend_path, output_glb_path = parse_args()
    bpy.ops.wm.open_mainfile(filepath=startup_blend_path)

    muscles_by_bone = rig_spec.resolve_muscle_objects()
    all_muscle_objects = [obj for objs in muscles_by_bone.values() for obj in objs]
    print(f"Muscles résolus : {len(all_muscle_objects)} objets sur {len(muscles_by_bone)} os.")

    # Racine (hanches) : position dérivée de la tête de `spine` (bas du
    # tronc), petit os "locateur" de longueur non nulle (Blender n'accepte
    # pas les os de longueur exactement nulle).
    spine_head, spine_tail = rig_spec.bone_head_tail(muscles_by_bone["spine"], ascending=True)
    root_head = spine_head
    root_tail = spine_head + type(spine_head)((0.0, 0.0, 0.02))

    bone_positions = {"root": (root_head, root_tail)}
    for bone_key in rig_spec.BONE_ORDER:
        if bone_key == "root":
            continue
        ascending = bone_key in rig_spec.ASCENDING_BONES
        bone_positions[bone_key] = rig_spec.bone_head_tail(
            muscles_by_bone[bone_key], ascending=ascending
        )

    armature_obj = build_armature(bone_positions)

    # Certaines collections du fichier source sont masquées par défaut
    # (atlas à ~7000 objets, optimisé pour un affichage sélectif par
    # système) : un objet masqué ne peut pas être sélectionné pour l'export.
    for obj in all_muscle_objects:
        obj.hide_set(False)
        obj.hide_viewport = False

    bpy.ops.object.select_all(action="DESELECT")
    for obj in all_muscle_objects:
        obj.select_set(True)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in all_muscle_objects:
        obj.select_set(True)
    armature_obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=output_glb_path,
        export_format="GLB",
        use_selection=True,
        export_skins=True,
        export_apply=False,
    )
    print(f"Export terminé : {output_glb_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add tools/blender/export_muscle_rig.py
git commit -m "feat: script d'export Blender du rig musculaire vers glb (tranche 3)"
```

(Ce script ne peut pas être exécuté de bout en bout tant que `Startup.blend`
n'est pas téléchargé — couvert par Task 5, qui l'exécute pour de vrai.)

---

## Task 4 : `tools/blender/validate_muscle_rig.py` — validation du `.glb` exporté

**Files:**
- Create: `tools/blender/validate_muscle_rig.py`

**Interfaces:**
- Consumes: `rig_spec.BONE_ORDER` (Task 2), fichier `.glb` produit par Task 3/5.
- Produces: code de sortie 0 (succès, imprime `OK: ...`) ou différent de 0 (`assert` échoué) — utilisé par Task 5 comme porte avant de committer le `.glb`.

- [ ] **Step 1: Écrire `tools/blender/validate_muscle_rig.py`**

```python
"""Valide un muscle-rig.glb exporté par export_muscle_rig.py : vérifie que
les 9 BoneKey attendus sont présents dans le squelette, et qu'au moins un
nombre plausible de maillages sont réellement skinnés (modifier Armature
présent). Pas un test Vitest classique (dépend d'un binaire externe non
commité tant que le pipeline n'a pas tourné) : voir tools/blender/README.md.

Usage:
    blender --background --python tools/blender/validate_muscle_rig.py -- \
        <chemin/vers/muscle-rig.glb>
"""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).parent))
import rig_spec  # noqa: E402

# Plancher de sécurité, pas un compte exact : dépend du nombre de variantes
# `.l`/`.r` réellement présentes par muscle dans le fichier source (inconnu
# tant que Startup.blend n'a pas été inspecté pour de vrai). ~17 groupes
# musculaires, la plupart bilatéraux, donnent un minimum plausible de 20
# objets skinnés.
MIN_EXPECTED_MESH_COUNT = 20


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    if len(argv) != 1:
        raise SystemExit(
            "Usage: blender --background --python validate_muscle_rig.py -- <muscle-rig.glb>"
        )
    glb_path = argv[0]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb_path)

    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    assert len(armatures) == 1, f"attendu 1 armature dans le glb, trouvé {len(armatures)}"
    armature = armatures[0]

    bone_names = {b.name for b in armature.data.bones}
    missing = set(rig_spec.BONE_ORDER) - bone_names
    assert not missing, f"os manquants dans le glb exporté : {sorted(missing)}"

    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    assert len(meshes) >= MIN_EXPECTED_MESH_COUNT, (
        f"attendu au moins {MIN_EXPECTED_MESH_COUNT} maillages, trouvé {len(meshes)}"
    )

    unskinned = [
        mesh.name
        for mesh in meshes
        if not any(m.type == "ARMATURE" for m in mesh.modifiers)
    ]
    assert not unskinned, f"maillages sans modifier Armature (skinning manquant) : {unskinned}"

    print(f"OK: {len(bone_names)} os, {len(meshes)} maillages skinnés.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add tools/blender/validate_muscle_rig.py
git commit -m "feat: script de validation du glb exporté (tranche 3)"
```

---

## Task 5 : Exécution réelle du pipeline — téléchargement, export, validation, commit du `.glb`

**Files:**
- Create (généré, pas écrit à la main): `web/public/muscle-rig.glb`

**Interfaces:**
- Consumes: `tools/blender/export_muscle_rig.py`, `tools/blender/validate_muscle_rig.py` (Tasks 3-4).
- Produces: `web/public/muscle-rig.glb`, consommé par Task 6.

- [ ] **Step 1: Télécharger la source Z-Anatomy**

```bash
curl -L -o /tmp/Z-Anatomy.zip \
  https://github.com/Z-Anatomy/The-blend/raw/master/Z-Anatomy.zip
unzip -o /tmp/Z-Anatomy.zip -d /tmp/z-anatomy
ls -la /tmp/z-anatomy/Startup.blend
```

Attendu : le fichier existe, taille de l'ordre de 293 Mo. Si l'URL a changé
(404, redirection inattendue), consulter directement
https://github.com/Z-Anatomy/The-blend pour trouver le chemin actuel du zip
avant de continuer — ne pas deviner une autre URL.

- [ ] **Step 2: Lancer l'export**

```bash
blender --background --python tools/blender/export_muscle_rig.py -- \
  /tmp/z-anatomy/Startup.blend \
  web/public/muscle-rig.glb
```

Attendu : le script se termine avec `Export terminé : web/public/muscle-rig.glb`
(code de sortie 0), sans `RuntimeError` de muscle introuvable. Si une
`RuntimeError` est levée (muscle absent, nom différent de ce qui est
documenté dans la spec), inspecter directement le nom réel dans Blender
(`bpy.data.objects` filtré par mot-clé) et corriger `rig_spec.py` (Task 2)
en conséquence avant de relancer — ne pas retirer silencieusement le muscle
en échec de `rig_spec.py` sans le documenter dans le message de commit
correctif.

- [ ] **Step 3: Valider le fichier exporté**

```bash
blender --background --python tools/blender/validate_muscle_rig.py -- \
  web/public/muscle-rig.glb
```

Attendu : `OK: 9 os, N maillages skinnés.` avec N >= 20 et code de sortie 0.
Si `assert` échoue, ne pas committer le `.glb` — corriger le script d'export
ou `rig_spec.py` et reprendre au Step 2.

- [ ] **Step 4: Vérification visuelle rapide**

Ouvrir `web/public/muscle-rig.glb` dans https://gltf-viewer.donmccurdy.com/
(ou Blender). Vérifier :
- silhouette humaine reconnaissable, proportions plausibles ;
- pas de maillage qui s'envole loin du reste du corps (indiquerait une
  bounding box mal résolue pour ce muscle) ;
- pas de déformation extrême aux jointures en changeant la pose de test du
  viewer (si le viewer le permet).

Si un correctif de poids est nécessaire, l'appliquer dans Blender
directement sur `/tmp/z-anatomy/Startup.blend` (ou une copie), puis
ré-exécuter le script d'export en pointant sur le fichier corrigé, puis
reprendre au Step 3.

- [ ] **Step 5: Vérifier la taille du fichier avant de committer**

```bash
ls -la web/public/muscle-rig.glb
```

Un `.glb` de plusieurs dizaines à quelques centaines de Mo committé au dépôt
Git est acceptable pour ce projet (pas de LFS en place) — mais si le fichier
dépasse ~200 Mo, le signaler explicitement avant de committer plutôt que de
committer silencieusement un fichier disproportionné.

- [ ] **Step 6: Commit**

```bash
git add web/public/muscle-rig.glb
git commit -m "feat: ajoute muscle-rig.glb (export Z-Anatomy, tranche 3)"
```

---

## Task 6 : `PostureAvatar3D.tsx` — charger et skinner les vrais muscles

**Files:**
- Modify: `web/app/PostureAvatar3D.tsx`

**Interfaces:**
- Consumes: `applyFrameToSkeleton`, `BONE_ORDER`, `BoneKey`, `Pose3DLandmarks` (`web/app/pose3dSkeleton.ts`, inchangé), `web/public/muscle-rig.glb` (Task 5), `useGLTF` (`@react-three/drei`, déjà une dépendance).
- Produces: composant `PostureAvatar3D` avec le même contrat de props qu'avant (`pose3dUrl`, `videoRef`) — aucun changement d'API pour les appelants de ce composant.

- [ ] **Step 1: Remplacer les imports**

Dans `web/app/PostureAvatar3D.tsx`, remplacer :

```ts
import { applyFrameToSkeleton, buildSkeleton, Pose3DLandmarks, SkeletonRig } from "./pose3dSkeleton";
import { buildTestSkinnedGeometry } from "./testSkinnedGeometry";
```

par :

```ts
import { useGLTF } from "@react-three/drei";
import { applyFrameToSkeleton, BONE_ORDER, BoneKey, Pose3DLandmarks } from "./pose3dSkeleton";

const MUSCLE_RIG_URL = "/muscle-rig.glb";
```

(`SkeletonRig`, `buildSkeleton`, `buildTestSkinnedGeometry` ne sont plus
utilisés par ce composant — `testSkinnedGeometry.ts` reste dans le dépôt,
couvert par ses propres tests, cf. Hors périmètre de la spec.)

- [ ] **Step 2: Réécrire le composant `Rig`**

Remplacer entièrement la fonction `Rig` (lignes définissant `geometry`,
`rigRef`, `meshRef`, `materialRef`, le `useLayoutEffect` de bind, `useFrame`,
et le JSX retourné) par :

```tsx
function Rig({
  frames,
  videoRef,
}: {
  frames: Pose3DFrame[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const gltf = useGLTF(MUSCLE_RIG_URL);

  const skinnedMeshes = useMemo(() => {
    const meshes: THREE.SkinnedMesh[] = [];
    gltf.scene.traverse((object) => {
      if ((object as THREE.SkinnedMesh).isSkinnedMesh) {
        meshes.push(object as THREE.SkinnedMesh);
      }
    });
    return meshes;
  }, [gltf]);

  const bones = useMemo(() => {
    const skeleton = skinnedMeshes[0]?.skeleton;
    if (!skeleton) {
      throw new Error("muscle-rig.glb ne contient aucun SkinnedMesh.");
    }
    const map = {} as Record<BoneKey, THREE.Bone>;
    for (const key of BONE_ORDER) {
      const bone = skeleton.bones.find((candidate) => candidate.name === key);
      if (!bone) {
        throw new Error(`Os "${key}" introuvable dans le squelette importé (muscle-rig.glb).`);
      }
      map[key] = bone;
    }
    return map;
  }, [skinnedMeshes]);

  // Cloner les matériaux importés plutôt que les muter directement : évite
  // de modifier l'asset source partagé (mémoïsé par useGLTF) si le
  // composant est démonté/remonté.
  const clonedMaterials = useMemo(() => {
    return skinnedMeshes.map((mesh) => {
      const source = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
      const clone = (source as THREE.MeshStandardMaterial).clone();
      mesh.material = clone;
      return clone;
    });
  }, [skinnedMeshes]);

  const groupRef = useRef<THREE.Group>(null);
  const lastKnownLandmarksRef = useRef<Partial<Pose3DLandmarks>>({});
  const lastKnownColorRef = useRef<string>(DEFAULT_COLOR);
  const hasDetectedOnceRef = useRef(false);

  useFrame(() => {
    const video = videoRef.current;
    const group = groupRef.current;
    if (!video || !group || frames.length === 0) return;

    const index = findNearestFrameIndex(frames, video.currentTime);
    const frame = frames[index];

    if (frame.landmarks) {
      applyFrameToSkeleton(bones, frame.landmarks, lastKnownLandmarksRef.current);
      hasDetectedOnceRef.current = true;
      group.visible = true;
      if (frame.action_level) {
        lastKnownColorRef.current = ACTION_LEVEL_COLORS[frame.action_level] ?? DEFAULT_COLOR;
      }
    }

    if (!hasDetectedOnceRef.current) return;
    for (const material of clonedMaterials) {
      material.color.set(lastKnownColorRef.current);
    }
  });

  return (
    <group ref={groupRef} visible={false}>
      <primitive object={gltf.scene} />
    </group>
  );
}

useGLTF.preload(MUSCLE_RIG_URL);
```

- [ ] **Step 3: Ajouter le crédit d'attribution dans l'UI**

Dans le composant `PostureAvatar3D` (export principal), juste après la
balise fermante `</Canvas>` (avant la fermeture du `<div>` englobant),
ajouter :

```tsx
<p className="mt-1 text-xs text-gray-400">
  Modèle musculaire dérivé de Z-Anatomy (BodyParts3D), licence CC BY-SA 4.0.
  Voir NOTICE.md.
</p>
```

- [ ] **Step 4: Vérifier le typecheck**

```bash
cd web && npx tsc --noEmit
```

Attendu : aucune erreur (en particulier, aucune référence résiduelle à
`buildSkeleton`, `SkeletonRig`, ou `buildTestSkinnedGeometry` dans ce
fichier).

- [ ] **Step 5: Lancer la suite de tests existante (non-régression)**

```bash
cd web && npm run test
```

Attendu : les 11 tests de `pose3dSkeleton.test.ts` passent toujours
(module non modifié) ; `testSkinnedGeometry.test.ts` passe toujours (module
non modifié, plus utilisé par `PostureAvatar3D.tsx` mais toujours testé
isolément) ; `skinning-integration.test.ts` — si ce test importe
`PostureAvatar3D.tsx` ou dépend de `buildTestSkinnedGeometry` via ce
composant, il peut casser : inspecter son contenu et l'adapter au nouveau
chargement par `useGLTF` si besoin (pas anticipable précisément sans lire
ce fichier au moment de l'exécution).

- [ ] **Step 6: Commit**

```bash
git add web/app/PostureAvatar3D.tsx
git commit -m "feat: PostureAvatar3D charge les vrais muscles Z-Anatomy via muscle-rig.glb (tranche 3)"
```

---

## Task 7 : Vérification manuelle obligatoire et finalisation

**Files:** aucun fichier nouveau (vérification + éventuels correctifs ponctuels).

**Interfaces:** N/A (dernière tâche du plan).

- [ ] **Step 1: Démarrer l'application et rejouer `moi coupe.mp4`**

```bash
cd web && npm run dev
```

Ouvrir la page contenant `PostureAvatar3D`, charger `moi coupe.mp4`,
lancer la lecture.

- [ ] **Step 2: Comparer visuellement à la Tranche 2**

Vérifier :
- les muscles suivent la posture en synchro avec la vidéo (même logique
  qu'avant, `applyFrameToSkeleton` inchangé) ;
- pas de distorsion aberrante aux jointures (coude, épaule, genou, hanche) ;
- le masquage des os jamais détectés (`HIDDEN_SCALE`, correctif de la
  Tranche 2 — `LEFT_ELBOW`/`LEFT_KNEE` sur cette vidéo filmée de profil)
  fonctionne toujours visuellement avec les vrais muscles (le membre
  concerné doit disparaître, pas rester figé en pose de repos) ;
- absence de mannequin fantôme à `t=0` avant toute détection (`group.visible`
  reste `false` tant que `hasDetectedOnceRef.current` est `false`, même
  logique que la Tranche 2) ;
- la couleur du matériau change bien avec l'`action_level` courant, sur
  l'ensemble des muscles simultanément (pas un sous-ensemble).

- [ ] **Step 3: Vérifier le crédit d'attribution**

Confirmer que la mention CC BY-SA ajoutée à l'étape précédente (Task 6,
Step 3) s'affiche bien sous l'avatar 3D dans l'interface.

- [ ] **Step 4: Documenter tout écart constaté**

Si un correctif de poids ou une correction de `rig_spec.py` a été nécessaire
pendant cette vérification, committer ce correctif séparément avec un
message explicite (pas un `--amend` silencieux des commits précédents) et
mettre à jour la spec (`docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-design.md`)
avec un bloc « Correction (date) » si le comportement décrit s'avère faux à
l'usage — même convention que les Tranches 1 et 2.

- [ ] **Step 5: Mettre à jour le README**

Dans `README.md`, remplacer la mention de la Tranche 3 comme
« implémentation reportée » par une description de ce qui a été livré
(muscles réels Z-Anatomy, pipeline Blender → glb, attribution CC BY-SA),
dans le même style que les entrées existantes pour les Tranches 1 et 2.

```bash
git add README.md docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-design.md
git commit -m "docs: tranche 3 livrée — vrais muscles Z-Anatomy intégrés à l'avatar 3D"
```

## Hors périmètre (rappel, cf. spec)

- Musculature complète (~600 muscles).
- Coloration/activation par muscle individuel selon les sous-scores RULA (Tranche 4 future).
- Correction du roll/torsion des os.
- Correction du risque de cascade d'échelle sur hanche jamais détectée.
- Suppression ou conservation de `testSkinnedGeometry.ts` : conservé tel quel dans ce plan (décision de suppression explicitement laissée hors périmètre par la spec).
