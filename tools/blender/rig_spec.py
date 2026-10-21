"""Squelette à 24 os et table des muscles Z-Anatomy de l'avatar du corps complet
(Tranche 4, voir docs/superpowers/specs/2026-10-22-avatar-corps-complet-design.md).

Dupliqué intentionnellement depuis `web/app/pose3dSkeleton.ts` (BONE_ORDER et PARENT_OF) : pas de
partage de source entre TypeScript et Blender, à tenir synchronisé à la main.

Ce module s'exécute UNIQUEMENT dans l'interpréteur Python embarqué de Blender
(`blender --background --python ...`) : `bpy` et `mathutils` ne s'installent pas avec pip.

Repère de Blender (Z vers le haut) : le côté gauche du modèle est +x, son avant est -y. L'export
glTF convertit en Y vers le haut, avant +z, gauche +x.
"""

import bpy
from mathutils import Vector

CENTRAL_BONES = ["root", "spine", "neck", "head"]
SIDED_BONES = [
    "clavicle",
    "upper_arm",
    "forearm",
    "hand",
    "fingers",
    "thumb",
    "thigh",
    "shin",
    "foot",
    "toes",
]
# Ordre parent avant enfant, côté gauche puis droit pour chaque os pairé.
BONE_ORDER = CENTRAL_BONES + [f"{side}_{bone}" for bone in SIDED_BONES for side in ("L", "R")]

_SIDED_PARENT = {
    "clavicle": "spine",
    "upper_arm": "clavicle",
    "forearm": "upper_arm",
    "hand": "forearm",
    "fingers": "hand",
    "thumb": "hand",
    "thigh": "root",
    "shin": "thigh",
    "foot": "shin",
    "toes": "foot",
}
PARENT_OF = {"spine": "root", "neck": "spine", "head": "neck"}
for _side in ("L", "R"):
    for _bone, _parent in _SIDED_PARENT.items():
        PARENT_OF[f"{_side}_{_bone}"] = _parent if _parent in CENTRAL_BONES else f"{_side}_{_parent}"

# Demi-largeur (en mètres) de la zone de fondu autour de chaque articulation, mesurée le long de
# l'axe de l'os distal. Plus étroite aux doigts et aux orteils.
DEFAULT_BLEND_HALF_WIDTH = 0.04
BLEND_HALF_WIDTH = {
    "hand": 0.03,
    "fingers": 0.02,
    "thumb": 0.02,
    "toes": 0.02,
    "foot": 0.03,
    "thigh": 0.05,
    "upper_arm": 0.05,
}

# Articulations pondérées par proximité plutôt que par plan : (os proximal, os distal) -> (distance
# en dessous de laquelle le sommet suit entièrement l'os distal, distance au-delà de laquelle il ne
# le suit plus du tout), en mètres. Voir export_muscle_rig.chain_weights.
PROXIMITY_JOINTS = {
    ("spine", "upper_arm"): (0.04, 0.11),
    ("clavicle", "upper_arm"): (0.04, 0.11),
    ("spine", "clavicle"): (0.02, 0.08),
}

# Régions colorées par l'application (les quatre premières sont les zones RULA mesurées).
REGIONS = [
    "neck",
    "trunk",
    "upper_arm",
    "lower_arm",
    "head",
    "shoulder",
    "hand",
    "hip",
    "thigh",
    "lower_leg",
    "foot",
]

# Une entrée par muscle : (nom Z-Anatomy sans suffixe, chaîne d'os du proximal au distal, région).
# Les os pairés s'écrivent sans préfixe (`upper_arm`) et prennent le côté de l'objet (`.l` ou `.r`) ;
# `root`, `spine`, `neck` et `head` ne sont jamais préfixés. Chaque articulation entre deux os de la
# chaîne devient une zone de fondu : un biceps passe progressivement de `upper_arm` à `forearm`.
# Une chaîne d'un seul os est un rattachement rigide à 100 %.
MUSCLES = [
    # --- Tête et mâchoire (rigides sur la tête)
    ("Temporalis muscle", ["head"], "head"),
    ("Deep part of masseter", ["head"], "head"),
    ("Superficial part of masseter", ["head"], "head"),
    ("Frontalis muscle", ["head"], "head"),
    ("Occipitalis muscle", ["head"], "head"),
    # --- Cou
    ("Sternocleidomastoid muscle", ["spine", "neck", "head"], "neck"),
    ("Ascending part of trapezius muscle", ["spine", "neck"], "neck"),
    ("Transverse part of trapezius muscle", ["spine", "neck"], "neck"),
    ("Descending part of trapezius muscle", ["spine", "neck"], "neck"),
    ("Splenius capitis muscle", ["spine", "neck", "head"], "neck"),
    ("Splenius colli muscle", ["spine", "neck"], "neck"),
    ("Semispinalis colli muscle", ["spine", "neck"], "neck"),
    ("Longissimus capitis muscle", ["spine", "neck", "head"], "neck"),
    ("Longissimus colli muscle", ["spine", "neck"], "neck"),
    ("Spinalis capitis muscle", ["spine", "neck", "head"], "neck"),
    ("Spinalis colli muscle", ["spine", "neck"], "neck"),
    ("Iliocostalis colli muscle", ["spine", "neck"], "neck"),
    ("Multifidus colli muscle", ["spine", "neck"], "neck"),
    ("Interspinales colli muscles", ["spine", "neck"], "neck"),
    ("Rectus posterior major capitis muscle", ["neck", "head"], "neck"),
    ("Rectus posterior minor capitis muscle", ["neck", "head"], "neck"),
    ("Rectus anterior capitis muscle", ["neck", "head"], "neck"),
    ("Rectus lateralis capitis muscle", ["neck", "head"], "neck"),
    ("Obliquus inferior capitis muscle", ["neck", "head"], "neck"),
    ("Obliquus superior capitis muscle", ["neck", "head"], "neck"),
    ("Longus capitis muscle", ["spine", "neck", "head"], "neck"),
    ("Longus colli muscle", ["spine", "neck"], "neck"),
    ("Scalenus anterior muscle", ["spine", "neck"], "neck"),
    ("Scalenus medius muscle", ["spine", "neck"], "neck"),
    ("Scalenus posterior muscle", ["spine", "neck"], "neck"),
    ("Levator scapulae", ["spine", "neck"], "neck"),
    ("Platysma", ["spine", "neck"], "neck"),
    ("Omohyoid muscle", ["neck"], "neck"),
    ("Sternohyoid muscle", ["neck"], "neck"),
    ("Sternothyroid muscle", ["neck"], "neck"),
    ("Thyrohyoid muscle", ["neck"], "neck"),
    ("Mylohyoid muscle", ["neck", "head"], "neck"),
    ("Geniohyoid muscle", ["neck", "head"], "neck"),
    ("Stylohyoid muscle", ["neck", "head"], "neck"),
    ("Anterior belly of digastric muscle", ["neck", "head"], "neck"),
    ("Posterior belly of digastric muscle", ["neck", "head"], "neck"),
    # --- Tronc
    ("Latissimus dorsi muscle", ["spine", "upper_arm"], "trunk"),
    ("Rectus abdominis muscle", ["root", "spine"], "trunk"),
    ("Pyramidalis muscle", ["root", "spine"], "trunk"),
    ("External abdominal oblique muscle", ["root", "spine"], "trunk"),
    ("Internal abdominal oblique muscle", ["root", "spine"], "trunk"),
    ("Transversus abdominis muscle", ["root", "spine"], "trunk"),
    ("Quadratus lumborum muscle", ["root", "spine"], "trunk"),
    ("Iliocostalis lumborum muscle", ["root", "spine"], "trunk"),
    ("Iliocostalis thoracis muscle", ["root", "spine"], "trunk"),
    ("Longissimus thoracis muscle", ["root", "spine"], "trunk"),
    ("Spinalis thoracis muscle", ["root", "spine"], "trunk"),
    ("Multifidus lumborum muscle", ["root", "spine"], "trunk"),
    ("Multifidus thoracis muscle", ["root", "spine"], "trunk"),
    ("Semispinalis thoracis muscle", ["spine"], "trunk"),
    ("Rotatores", ["spine"], "trunk"),
    ("Interspinales lumborum muscles", ["root", "spine"], "trunk"),
    ("Interspinales thoracis muscles", ["spine"], "trunk"),
    ("Dorsal parts of lateral intertransversarii lumborum muscles", ["root", "spine"], "trunk"),
    ("Ventral parts of lateral intertransversarii lumborum muscles", ["root", "spine"], "trunk"),
    ("Levatores breves costarum", ["spine"], "trunk"),
    ("Levatores longi costarum", ["spine"], "trunk"),
    ("Serratus posterior superior muscle", ["spine"], "trunk"),
    ("Serratus posterior inferior muscle", ["spine"], "trunk"),
    ("Transversus thoracis muscle", ["spine"], "trunk"),
    # --- Épaule (ceinture scapulaire)
    ("Serratus anterior muscle", ["spine", "upper_arm"], "shoulder"),
    ("Rhomboid major muscle", ["spine", "clavicle"], "shoulder"),
    ("Rhomboid minor muscle", ["spine", "clavicle"], "shoulder"),
    ("Subclavius muscle", ["spine", "clavicle"], "shoulder"),
    ("Pectoralis minor muscle", ["spine", "upper_arm"], "shoulder"),
    ("Clavicular head of pectoralis major muscle", ["spine", "upper_arm"], "shoulder"),
    ("Sternocostal head of pectoralis major muscle", ["spine", "upper_arm"], "shoulder"),
    ("(Abdominal part of pectoralis major muscle)", ["spine", "upper_arm"], "shoulder"),
    ("Supraspinatus muscle", ["clavicle", "upper_arm"], "shoulder"),
    ("Infraspinatus muscle", ["clavicle", "upper_arm"], "shoulder"),
    ("Teres minor muscle", ["clavicle", "upper_arm"], "shoulder"),
    ("Teres major muscle", ["clavicle", "upper_arm"], "shoulder"),
    ("Subscapularis muscle", ["clavicle", "upper_arm"], "shoulder"),
    # --- Bras
    ("Acromial part of deltoid muscle", ["clavicle", "upper_arm"], "upper_arm"),
    ("Clavicular part of deltoid muscle", ["clavicle", "upper_arm"], "upper_arm"),
    ("Scapular spinal part of deltoid muscle", ["clavicle", "upper_arm"], "upper_arm"),
    ("Long head of biceps brachii", ["clavicle", "upper_arm", "forearm"], "upper_arm"),
    ("Short head of biceps brachii", ["clavicle", "upper_arm", "forearm"], "upper_arm"),
    ("Coracobrachialis muscle", ["upper_arm"], "upper_arm"),
    ("Brachialis muscle", ["upper_arm", "forearm"], "upper_arm"),
    ("Long head of triceps brachii", ["clavicle", "upper_arm", "forearm"], "upper_arm"),
    ("Lateral head of triceps brachii", ["upper_arm", "forearm"], "upper_arm"),
    ("Medial head of triceps brachii", ["upper_arm", "forearm"], "upper_arm"),
    ("Anconeus muscle", ["upper_arm", "forearm"], "upper_arm"),
    # --- Avant-bras
    ("Brachioradialis muscle", ["upper_arm", "forearm"], "lower_arm"),
    ("Superficial head of pronator teres", ["upper_arm", "forearm"], "lower_arm"),
    ("Deep head of pronator teres", ["upper_arm", "forearm"], "lower_arm"),
    ("Supinator", ["upper_arm", "forearm"], "lower_arm"),
    ("Pronator quadratus", ["forearm"], "lower_arm"),
    ("Flexor carpi radialis", ["forearm", "hand"], "lower_arm"),
    ("Palmaris longus muscle", ["forearm", "hand"], "lower_arm"),
    ("Humeral head of flexor carpi ulnaris", ["forearm", "hand"], "lower_arm"),
    ("Ulnar head of flexor carpi ulnaris", ["forearm", "hand"], "lower_arm"),
    ("Humero-ulnar head of flexor digitorum superficialis", ["forearm", "hand", "fingers"], "lower_arm"),
    ("Radial head of flexor digitorum superficialis", ["forearm", "hand", "fingers"], "lower_arm"),
    ("Flexor digitorum profundus", ["forearm", "hand", "fingers"], "lower_arm"),
    ("Flexor pollicis longus", ["forearm", "hand", "thumb"], "lower_arm"),
    ("Extensor carpi radialis longus", ["forearm", "hand"], "lower_arm"),
    ("Extensor carpi radialis brevis", ["forearm", "hand"], "lower_arm"),
    ("Humeral head of extensor carpi ulnaris", ["forearm", "hand"], "lower_arm"),
    ("Ulnar head of extensor carpi ulnaris", ["forearm", "hand"], "lower_arm"),
    ("Extensor digitorum", ["forearm", "hand", "fingers"], "lower_arm"),
    ("Extensor digiti minimi", ["forearm", "hand", "fingers"], "lower_arm"),
    ("Extensor indicis", ["forearm", "hand", "fingers"], "lower_arm"),
    ("Abductor pollicis longus", ["forearm", "hand", "thumb"], "lower_arm"),
    ("Extensor pollicis brevis", ["forearm", "hand", "thumb"], "lower_arm"),
    ("Extensor pollicis longus", ["forearm", "hand", "thumb"], "lower_arm"),
    # --- Main
    ("Abductor pollicis brevis", ["hand", "thumb"], "hand"),
    ("Opponens pollicis muscle", ["hand", "thumb"], "hand"),
    ("Superficial head of flexor pollicis brevis", ["hand", "thumb"], "hand"),
    ("Deep head of flexor pollicis brevis", ["hand", "thumb"], "hand"),
    ("Oblique head of adductor pollicis", ["hand", "thumb"], "hand"),
    ("Transverse head of adductor pollicis", ["hand", "thumb"], "hand"),
    ("Abductor digiti minimi of hand", ["hand", "fingers"], "hand"),
    ("Flexor digiti minimi of hand", ["hand", "fingers"], "hand"),
    ("Opponens digiti minimi muscle of hand", ["hand"], "hand"),
    ("Lumbrical muscles of hand", ["hand", "fingers"], "hand"),
    ("Dorsal interossei muscles of hand", ["hand", "fingers"], "hand"),
    ("Palmar interossei muscles", ["hand", "fingers"], "hand"),
    # --- Hanche et bassin
    ("Gluteus maximus muscle", ["root", "thigh"], "hip"),
    ("Gluteus medius muscle", ["root", "thigh"], "hip"),
    ("Gluteus minimus muscle", ["root", "thigh"], "hip"),
    ("Piriformis muscle", ["root", "thigh"], "hip"),
    ("Obturator internus", ["root", "thigh"], "hip"),
    ("Obturator externus", ["root", "thigh"], "hip"),
    ("Superior gemellus muscle", ["root", "thigh"], "hip"),
    ("Inferior gemellus muscle", ["root", "thigh"], "hip"),
    ("Quadratus femoris muscle", ["root", "thigh"], "hip"),
    ("Iliacus muscle", ["root", "thigh"], "hip"),
    ("Psoas major", ["root", "thigh"], "hip"),
    ("Pectineus muscle", ["root", "thigh"], "hip"),
    # --- Cuisse
    ("Adductor longus", ["root", "thigh"], "thigh"),
    ("Adductor brevis", ["root", "thigh"], "thigh"),
    ("Adductor magnus", ["root", "thigh"], "thigh"),
    ("(Adductor minimus)", ["root", "thigh"], "thigh"),
    ("Gracilis muscle", ["root", "thigh", "shin"], "thigh"),
    ("Sartorius muscle", ["root", "thigh", "shin"], "thigh"),
    ("Rectus femoris muscle", ["root", "thigh", "shin"], "thigh"),
    ("Vastus intermedius muscle", ["thigh", "shin"], "thigh"),
    ("Vastus lateralis muscle", ["thigh", "shin"], "thigh"),
    ("Vastus medialis muscle", ["thigh", "shin"], "thigh"),
    ("Long head of biceps femoris", ["root", "thigh", "shin"], "thigh"),
    ("Short head of biceps femoris", ["thigh", "shin"], "thigh"),
    ("Semimembranosus muscle", ["root", "thigh", "shin"], "thigh"),
    ("Semitendinosus muscle", ["root", "thigh", "shin"], "thigh"),
    # --- Jambe
    ("Medial head of gastrocnemius", ["thigh", "shin", "foot"], "lower_leg"),
    ("Lateral head of gastrocnemius", ["thigh", "shin", "foot"], "lower_leg"),
    ("Plantaris muscle", ["thigh", "shin", "foot"], "lower_leg"),
    ("Popliteus muscle", ["thigh", "shin"], "lower_leg"),
    ("Soleus muscle", ["shin", "foot"], "lower_leg"),
    ("Tibialis anterior muscle", ["shin", "foot"], "lower_leg"),
    ("Tibialis posterior muscle", ["shin", "foot"], "lower_leg"),
    ("Fibularis longus muscle", ["shin", "foot"], "lower_leg"),
    ("Fibularis brevis muscle", ["shin", "foot"], "lower_leg"),
    ("Fibularis tertius muscle", ["shin", "foot"], "lower_leg"),
    ("Extensor digitorum longus", ["shin", "foot", "toes"], "lower_leg"),
    ("Extensor hallucis longus", ["shin", "foot", "toes"], "lower_leg"),
    ("Flexor digitorum longus", ["shin", "foot", "toes"], "lower_leg"),
    ("Flexor hallucis longus", ["shin", "foot", "toes"], "lower_leg"),
    # --- Pied
    ("Extensor digitorum brevis", ["foot", "toes"], "foot"),
    ("Extensor hallucis brevis", ["foot", "toes"], "foot"),
    ("Abductor hallucis", ["foot", "toes"], "foot"),
    ("Flexor digitorum brevis", ["foot", "toes"], "foot"),
    ("Abductor digiti minimi of foot", ["foot", "toes"], "foot"),
    ("Quadratus plantae muscle", ["foot"], "foot"),
    ("Lateral head of flexor hallucis brevis", ["foot", "toes"], "foot"),
    ("Medial head of flexor hallucis brevis", ["foot", "toes"], "foot"),
    ("Oblique head of adductor hallucis", ["foot", "toes"], "foot"),
    ("Transverse head of adductor hallucis", ["foot", "toes"], "foot"),
    ("Flexor digiti minimi of foot", ["foot", "toes"], "foot"),
    ("(Opponens digiti minimi muscle of foot)", ["foot"], "foot"),
    ("Lumbrical muscles of foot", ["foot", "toes"], "foot"),
    ("Dorsal interossei muscles of foot", ["foot", "toes"], "foot"),
    ("Plantar interossei muscles", ["foot", "toes"], "foot"),
]

# Noms d'objets sources dont on sait qu'un des deux côtés manque ou est mal suffixé dans le fichier
# Z-Anatomy ; l'autre côté est alors cherché sans suffixe. Vérifié sur Startup.blend.
_EXCLUDED_SUFFIXES = {"el", "er", "ol", "or"}

# Maillages squelettiques (nom sans suffixe) servant à placer les articulations.
SKELETAL_NAMES = [
    "Humerus", "Radius", "Ulna", "Femur", "Tibia", "Clavicle", "Talus",
    "Third metatarsal bone", "Distal phalanx of third finger of foot",
    "Third metacarpal bone", "Distal phalanx of third finger of hand",
    "First metacarpal bone", "Distal phalanx of first finger of hand",
]
CENTRAL_SKELETAL_NAMES = ["Vertebra T1", "Atlas (C1)", "Sacrum", "Frontal bone", "Occipital bone"]


def _ancestors(bone: str) -> set:
    found = set()
    while bone in PARENT_OF:
        bone = PARENT_OF[bone]
        found.add(bone)
    return found


def check_chain(base_name: str, chain_template: list) -> None:
    """Chaque os de la chaîne doit descendre du précédent : la zone de fondu d'une articulation
    est orientée selon l'axe de l'os distal, ce qui n'a de sens que dans cet ordre."""
    for proximal, distal in zip(chain_template, chain_template[1:]):
        probe = distal if distal in CENTRAL_BONES else f"L_{distal}"
        ancestors = {a.removeprefix("L_") for a in _ancestors(probe)}
        if proximal not in ancestors:
            raise RuntimeError(
                f"Chaîne invalide pour '{base_name}' : '{distal}' ne descend pas de '{proximal}'."
            )


def mesh_object(name: str):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH":
        raise RuntimeError(f"Objet maillage '{name}' introuvable dans le fichier source.")
    return obj


def world_vertices(obj) -> list:
    matrix = obj.matrix_world
    return [matrix @ vertex.co for vertex in obj.data.vertices]


def _centroid(points: list) -> Vector:
    total = Vector((0.0, 0.0, 0.0))
    for point in points:
        total += point
    return total / len(points)


def extreme_centroid(obj, axis: int, high: bool, fraction: float = 0.06) -> Vector:
    """Centre des sommets situés dans la fraction `fraction` la plus haute (ou basse) de l'objet
    selon `axis` (0 = x, 1 = y, 2 = z)."""
    points = world_vertices(obj)
    values = [p[axis] for p in points]
    low, top = min(values), max(values)
    margin = (top - low) * fraction
    chosen = [p for p in points if (p[axis] >= top - margin if high else p[axis] <= low + margin)]
    return _centroid(chosen)


def farthest_vertex(obj, origin: Vector) -> Vector:
    return max(world_vertices(obj), key=lambda p: (p - origin).length)


def _side_object(base: str, side: str):
    return mesh_object(f"{base}.{side.lower()}")


def joint_positions(side: str) -> dict:
    """Positions monde (Blender) des articulations d'un côté, déduites des os réels de Z-Anatomy."""
    humerus = _side_object("Humerus", side)
    radius = _side_object("Radius", side)
    ulna = _side_object("Ulna", side)
    femur = _side_object("Femur", side)
    tibia = _side_object("Tibia", side)
    clavicle = _side_object("Clavicle", side)

    # Tête du fémur : le haut de l'os, moitié la plus proche du plan médian (le grand trochanter
    # est du côté externe).
    top_points = world_vertices(femur)
    z_values = [p.z for p in top_points]
    z_top, z_low = max(z_values), min(z_values)
    head_points = [p for p in top_points if p.z >= z_top - 0.1 * (z_top - z_low)]
    x_mid = (min(p.x for p in head_points) + max(p.x for p in head_points)) / 2
    medial = [p for p in head_points if abs(p.x) < abs(x_mid)]
    hip = _centroid(medial or head_points)

    shoulder = extreme_centroid(humerus, 2, True)
    elbow = (extreme_centroid(humerus, 2, False) + extreme_centroid(ulna, 2, True)) / 2
    wrist = (extreme_centroid(radius, 2, False, 0.04) + extreme_centroid(ulna, 2, False, 0.04)) / 2
    knee = (extreme_centroid(femur, 2, False, 0.05) + extreme_centroid(tibia, 2, True, 0.05)) / 2
    ankle = extreme_centroid(tibia, 2, False, 0.04)

    metacarpal3 = _side_object("Third metacarpal bone", side)
    knuckle = extreme_centroid(metacarpal3, 2, False, 0.08)
    fingertip = farthest_vertex(_side_object("Distal phalanx of third finger of hand", side), knuckle)
    metacarpal1 = _side_object("First metacarpal bone", side)
    thumb_base = extreme_centroid(metacarpal1, 2, True, 0.08)
    thumb_tip = farthest_vertex(_side_object("Distal phalanx of first finger of hand", side), thumb_base)

    metatarsal3 = _side_object("Third metatarsal bone", side)
    ball = extreme_centroid(metatarsal3, 1, False, 0.08)  # l'avant du pied est -y
    toe_tip = farthest_vertex(_side_object("Distal phalanx of third finger of foot", side), ball)

    sternal_end = extreme_centroid(clavicle, 0, side == "r", 0.08)
    acromial_end = extreme_centroid(clavicle, 0, side == "l", 0.08)

    return {
        "hip": hip, "knee": knee, "ankle": ankle, "ball": ball, "toe_tip": toe_tip,
        "shoulder": shoulder, "elbow": elbow, "wrist": wrist, "knuckle": knuckle,
        "fingertip": fingertip, "thumb_base": thumb_base, "thumb_tip": thumb_tip,
        "sternal_end": sternal_end, "acromial_end": acromial_end,
    }


def bone_positions() -> dict:
    """{os: (tête, queue)} en coordonnées monde de Blender."""
    left = joint_positions("l")
    right = joint_positions("r")
    t1 = world_vertices(mesh_object("Vertebra T1"))
    atlas = world_vertices(mesh_object("Atlas (C1)"))
    skull = world_vertices(mesh_object("Frontal bone")) + world_vertices(mesh_object("Occipital bone"))

    # Colonne : verticale, dans le plan médian, à la profondeur des corps vertébraux.
    spine_y = _centroid(t1).y
    hip_height = (left["hip"].z + right["hip"].z) / 2
    pelvis = Vector((0.0, spine_y, hip_height))
    c7 = Vector((0.0, spine_y, _centroid(t1).z))
    skull_base = Vector((0.0, spine_y, _centroid(atlas).z))
    skull_top = Vector((0.0, spine_y, max(p.z for p in skull)))

    positions = {
        "root": (pelvis, pelvis + Vector((0.0, 0.0, 0.02))),
        "spine": (pelvis, c7),
        "neck": (c7, skull_base),
        "head": (skull_base, skull_top),
    }
    for prefix, joints in (("L", left), ("R", right)):
        positions[f"{prefix}_clavicle"] = (joints["sternal_end"], joints["acromial_end"])
        positions[f"{prefix}_upper_arm"] = (joints["shoulder"], joints["elbow"])
        positions[f"{prefix}_forearm"] = (joints["elbow"], joints["wrist"])
        positions[f"{prefix}_hand"] = (joints["wrist"], joints["knuckle"])
        positions[f"{prefix}_fingers"] = (joints["knuckle"], joints["fingertip"])
        positions[f"{prefix}_thumb"] = (joints["thumb_base"], joints["thumb_tip"])
        positions[f"{prefix}_thigh"] = (joints["hip"], joints["knee"])
        positions[f"{prefix}_shin"] = (joints["knee"], joints["ankle"])
        positions[f"{prefix}_foot"] = (joints["ankle"], joints["ball"])
        positions[f"{prefix}_toes"] = (joints["ball"], joints["toe_tip"])
    return positions


def _objects_for_side(base_name: str, side: str) -> list:
    """Objets maillage d'un muscle pour un côté ('l' ou 'r'). Les variantes `.el/.er/.ol/.or`
    (vue éclatée, contour) sont ignorées. Si le côté demandé manque mais que l'autre existe, on
    accepte l'objet sans suffixe (cas d'un côté mal nommé dans la source)."""
    found = [
        obj for obj in bpy.data.objects
        if obj.type == "MESH" and obj.name == f"{base_name}.{side}"
    ]
    if found:
        return found
    other = "r" if side == "l" else "l"
    if any(obj.type == "MESH" and obj.name == f"{base_name}.{other}" for obj in bpy.data.objects):
        return [obj for obj in bpy.data.objects if obj.type == "MESH" and obj.name == base_name]
    return []


def resolve_muscles() -> list:
    """Retourne une liste de dicts {object, chain, region, side} pour tous les muscles de MUSCLES.
    Lève RuntimeError si un muscle est introuvable : jamais de sous-ensemble silencieux."""
    resolved = []
    missing = []
    for base_name, chain_template, region in MUSCLES:
        check_chain(base_name, chain_template)
        total = 0
        for side in ("l", "r"):
            objects = _objects_for_side(base_name, side)
            prefix = side.upper()
            chain = [
                bone if bone in CENTRAL_BONES else f"{prefix}_{bone}" for bone in chain_template
            ]
            for obj in objects:
                resolved.append(
                    {"object": obj, "chain": chain, "region": region, "side": side, "base": base_name}
                )
            total += len(objects)
        if total == 0:
            missing.append(base_name)
    if missing:
        raise RuntimeError(f"Muscles introuvables (essayé .l, .r et sans suffixe) : {missing}")
    return resolved
