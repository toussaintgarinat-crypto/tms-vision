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
# os. Noms RÉELLEMENT vérifiés en inspectant `bpy.data.objects` sur le
# Startup.blend téléchargé pendant la Tranche 3, Task 5 (le brainstorming
# antérieur ne l'avait pas encore fait tourner).
#
# Correction Task 5 : "Erector spinae" seul (sans suffixe) n'existe pas dans
# le fichier réel — les objets présents sont "Erector spinae.j" (mesh unique
# couvrant tout le muscle, comme "Deltoid muscle.j"/"Trapezius muscle.j"/
# "Triceps brachii muscle.j"/"Biceps brachii muscle.j" pour ces autres
# muscles : une version "joined" à objet unique, par opposition aux variantes
# "el"/"er" = duplicata exploded-view et "ol"/"or" = duplicata outline/
# highlight de l'appli Z-Anatomy) et "Erector spinae.ol"/"Erector spinae.or"
# (duplicata outline). Comme "spine" est un os unique sans côté gauche/droite
# séparé, le mesh "joined" unique est fonctionnellement équivalent à une
# paire .l/.r et correspond à la vraie géométrie du muscle (pas un proxy de
# highlight) : on utilise donc "Erector spinae.j", qui matche via le repli
# "objet médian unique" déjà prévu dans `resolve_muscle_objects` (aucun
# changement de logique nécessaire, seulement la chaîne de nom).
TRUNK_NECK_MUSCLES = {
    "spine": [
        "Erector spinae.j",
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
# mode "exact" : nom d'objet vérifié tel quel dans le Startup.blend réel
# (Task 5). mode "contains" : conservé dans le code de résolution mais plus
# utilisé par aucune entrée ci-dessous depuis la correction Task 5 (voir
# note Deltoïde).
#
# Correction Task 5 — constat général : dans le fichier réel, la plupart des
# muscles composés (Deltoïde, Biceps brachii, Triceps brachii, Flexor/
# Extensor carpi ulnaris, Quadriceps femoris, Biceps femoris) n'ont PAS de
# mesh unique nommé "<Muscle> muscle.l"/".r" — seules leurs parties/chefs
# anatomiques individuels portent ce suffixe bare ".l"/".r" ; le nom composé
# lui-même n'existe qu'en variantes ".el"/".er" (exploded-view) ou ".j"
# (mesh unique), toutes deux exclues par la logique `exact`/`contains` sur
# suffixe bare. Chaque entrée ci-dessous a donc été remplacée par la liste
# de ses parties/chefs réels, vérifiés un par un via `bpy.data.objects`.
#
# Deltoïde : la note de risque du plan notait que les noms exacts des 3
# parties n'étaient pas vérifiés (seule "3 parties comme le trapèze" était
# confirmée) — on utilisait donc un mode "contains" sur "deltoid" en repli.
# Task 5 a vérifié les 3 noms exacts ET découvert que "contains" aurait en
# prime capturé "Deltoid fascia.l/.r" (fascia, pas du muscle) et
# "Deltoid region.l/.r" (probablement un proxy de sélection/hover de
# l'appli, pas de la géométrie musculaire) : on bascule donc sur les 3 noms
# exacts, plus précis et sans ce risque de pollution.
LIMB_MUSCLES = {
    "upper_arm": [
        ("Acromial part of deltoid muscle", "exact"),
        ("Clavicular part of deltoid muscle", "exact"),
        ("Scapular spinal part of deltoid muscle", "exact"),
        ("Long head of biceps brachii", "exact"),
        ("Short head of biceps brachii", "exact"),
        ("Lateral head of triceps brachii", "exact"),
        ("Long head of triceps brachii", "exact"),
        ("Medial head of triceps brachii", "exact"),
    ],
    "forearm": [
        ("Brachioradialis muscle", "exact"),
        ("Humeral head of flexor carpi ulnaris", "exact"),
        ("Ulnar head of flexor carpi ulnaris", "exact"),
        ("Humeral head of extensor carpi ulnaris", "exact"),
        ("Ulnar head of extensor carpi ulnaris", "exact"),
        ("Extensor digitorum", "exact"),
    ],
    "thigh": [
        ("Rectus femoris muscle", "exact"),
        ("Vastus intermedius muscle", "exact"),
        ("Vastus lateralis muscle", "exact"),
        ("Vastus medialis muscle", "exact"),
        ("Long head of biceps femoris", "exact"),
        ("Short head of biceps femoris", "exact"),
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
