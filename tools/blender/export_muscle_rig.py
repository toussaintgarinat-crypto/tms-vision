"""Construit l'armature à 24 os (même hiérarchie que web/app/pose3dSkeleton.ts), y rattache les
muscles Z-Anatomy listés dans rig_spec.py avec des poids de peau calculés par zone d'articulation,
puis exporte le tout en .glb.

Usage (voir tools/blender/README.md) :
    blender --background --python-exit-code 1 --python tools/blender/export_muscle_rig.py -- \
        <chemin/vers/Startup.blend> <chemin/de/sortie/muscle-rig.glb>
"""

import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).parent))
import rig_spec  # noqa: E402

# Nombre maximal de sommets conservés par muscle (simplification pour tenir dans ~25 Mo).
MAX_VERTICES_PER_MUSCLE = 1500
# Poids inférieur à ce seuil : ignoré (au plus 4 influences par sommet dans glTF).
MIN_WEIGHT = 0.01


def parse_args() -> tuple[str, str]:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    if len(argv) != 2:
        raise SystemExit(
            "Usage: blender --background --python export_muscle_rig.py -- <Startup.blend> <sortie.glb>"
        )
    return argv[0], argv[1]


def unhide_all_collections(layer_collection: bpy.types.LayerCollection) -> None:
    """Certaines collections du fichier source sont exclues de la view layer : un objet qui y
    est reste invisible et ne peut pas être sélectionné pour l'export. Corrige à tous les niveaux."""
    layer_collection.exclude = False
    layer_collection.hide_viewport = False
    layer_collection.collection.hide_viewport = False
    for child in layer_collection.children:
        unhide_all_collections(child)


def build_armature(positions: dict) -> bpy.types.Object:
    armature_data = bpy.data.armatures.new("MuscleRigArmature")
    armature_obj = bpy.data.objects.new("MuscleRigArmature", armature_data)
    bpy.context.scene.collection.objects.link(armature_obj)
    bpy.context.view_layer.objects.active = armature_obj

    bpy.ops.object.mode_set(mode="EDIT")
    created = {}
    for bone_key in rig_spec.BONE_ORDER:
        edit_bone = armature_data.edit_bones.new(bone_key)
        head, tail = positions[bone_key]
        edit_bone.head = head
        edit_bone.tail = tail
        created[bone_key] = edit_bone
    for bone_key, parent_key in rig_spec.PARENT_OF.items():
        created[bone_key].parent = created[parent_key]
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature_obj


def decimate(obj: bpy.types.Object) -> None:
    """Réduit le maillage à MAX_VERTICES_PER_MUSCLE sommets au plus (modificateur appliqué)."""
    count = len(obj.data.vertices)
    if count <= MAX_VERTICES_PER_MUSCLE:
        return
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new(name="Decimate", type="DECIMATE")
    modifier.ratio = MAX_VERTICES_PER_MUSCLE / count
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def smoothstep(value: float) -> float:
    value = min(max(value, 0.0), 1.0)
    return value * value * (3.0 - 2.0 * value)


def distance_to_segment(point: Vector, head: Vector, tail: Vector) -> float:
    axis = tail - head
    t = min(max((point - head).dot(axis) / axis.length_squared, 0.0), 1.0)
    return (point - (head + axis * t)).length


def chain_weights(point: Vector, chain: list, positions: dict) -> list:
    """Poids d'un sommet pour chaque os de la chaîne (somme = 1). Pour chaque articulation,
    `passed` vaut 0 du côté de l'os proximal et 1 du côté de l'os distal.

    Deux modes selon l'articulation (voir rig_spec.PROXIMITY_JOINTS) :
    - par plan : mesuré le long de l'axe de l'os distal, avec une zone de fondu autour de
      l'articulation (coude, poignet, genou, cheville, doigts...) ;
    - par proximité : selon la distance au segment de l'os distal. Pour l'épaule, un plan
      entraînerait avec le bras tout le grand dorsal et les pectoraux, qui couvrent le tronc :
      seuls les sommets proches de l'humérus doivent le suivre."""
    if len(chain) == 1:
        return [1.0]
    passed = []
    for proximal, bone in zip(chain, chain[1:]):
        head, tail = positions[bone]
        key = (proximal.removeprefix("L_").removeprefix("R_"), bone.removeprefix("L_").removeprefix("R_"))
        if key in rig_spec.PROXIMITY_JOINTS:
            near, far = rig_spec.PROXIMITY_JOINTS[key]
            passed.append(1.0 - smoothstep((distance_to_segment(point, head, tail) - near) / (far - near)))
            continue
        axis = (tail - head).normalized()
        base = key[1]
        half_width = rig_spec.BLEND_HALF_WIDTH.get(base, rig_spec.DEFAULT_BLEND_HALF_WIDTH)
        passed.append(smoothstep(((point - head).dot(axis) + half_width) / (2.0 * half_width)))
    weights = []
    carried = 1.0
    for value in passed:
        weights.append(carried * (1.0 - value))
        carried *= value
    weights.append(carried)
    return weights


def apply_skin_weights(entry: dict, armature_obj: bpy.types.Object, positions: dict) -> None:
    obj = entry["object"]
    chain = entry["chain"]
    for group in list(obj.vertex_groups):
        obj.vertex_groups.remove(group)
    group_index = {bone: obj.vertex_groups.new(name=bone).index for bone in chain}
    matrix = obj.matrix_world

    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    deform = mesh.verts.layers.deform.verify()
    for vertex in mesh.verts:
        weights = chain_weights(matrix @ vertex.co, chain, positions)
        kept = [(bone, w) for bone, w in zip(chain, weights) if w >= MIN_WEIGHT]
        total = sum(w for _, w in kept)
        for bone, weight in kept:
            vertex[deform][group_index[bone]] = weight / total
    mesh.to_mesh(obj.data)
    mesh.free()

    if not any(m.type == "ARMATURE" for m in obj.modifiers):
        modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
        modifier.object = armature_obj
    obj["region"] = entry["region"]
    obj["side"] = entry["side"]


def single_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    """Un seul matériau simple et partagé par muscle. Les matériaux de Z-Anatomy ont des arbres de
    nœuds que l'export glTF ne sait pas lire pour certains muscles, et l'application les recolore de
    toute façon (gris neutre ou bleu de la cible) : elle n'utilise jamais leur couleur d'origine."""
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0


def make_muscle_material() -> bpy.types.Material:
    material = bpy.data.materials.new("Muscle")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.75, 0.3, 0.3, 1.0)
    principled.inputs["Roughness"].default_value = 0.6
    return material


def main() -> None:
    startup_blend_path, output_glb_path = parse_args()
    bpy.ops.wm.open_mainfile(filepath=startup_blend_path)
    unhide_all_collections(bpy.context.view_layer.layer_collection)

    entries = rig_spec.resolve_muscles()
    print(f"Muscles résolus : {len(entries)} objets.")
    dropped = [e["object"].name for e in entries if len(e["object"].data.polygons) == 0]
    if dropped:
        print(f"ATTENTION : {len(dropped)} objet(s) sans face exclu(s) : {dropped}")
    entries = [e for e in entries if len(e["object"].data.polygons) > 0]

    seen = set()
    for entry in entries:
        if entry["object"].name in seen:
            raise RuntimeError(f"Objet muscle en double : {entry['object'].name}")
        seen.add(entry["object"].name)

    positions = rig_spec.bone_positions()
    for bone_key in rig_spec.BONE_ORDER:
        head, tail = positions[bone_key]
        print(f"  {bone_key:14s} tête=({head.x:.3f}, {head.y:.3f}, {head.z:.3f}) "
              f"queue=({tail.x:.3f}, {tail.y:.3f}, {tail.z:.3f})")
    # Le fichier source compte ~7000 objets : chaque opération Blender recalculerait tout. Une fois
    # les articulations calculées, on supprime tout ce qui n'est pas un muscle retenu.
    keep = {entry["object"].name for entry in entries}
    for obj in list(bpy.data.objects):
        if obj.name not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)

    armature_obj = build_armature(positions)

    for entry in entries:
        obj = entry["object"]
        obj.hide_set(False)
        obj.hide_viewport = False
        # Z-Anatomy partage un même datablock entre les objets .l et .r : les poids vivant dans
        # le maillage, un partage écraserait ceux d'un côté par ceux de l'autre.
        if obj.data.users > 1:
            obj.data = obj.data.copy()
    assert all(entry["object"].data.users == 1 for entry in entries)

    material = make_muscle_material()
    for entry in entries:
        single_material(entry["object"], material)
        decimate(entry["object"])

    bpy.ops.object.select_all(action="DESELECT")
    for entry in entries:
        entry["object"].select_set(True)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.parent_set(type="ARMATURE")

    for entry in entries:
        apply_skin_weights(entry, armature_obj, positions)

    total_vertices = sum(len(e["object"].data.vertices) for e in entries)
    print(f"{len(entries)} muscles, {total_vertices} sommets après simplification.")

    bpy.ops.object.select_all(action="DESELECT")
    for entry in entries:
        entry["object"].select_set(True)
    armature_obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=output_glb_path,
        export_format="GLB",
        use_selection=True,
        export_skins=True,
        export_apply=False,
        export_extras=True,
        export_animations=False,
        export_cameras=False,
        export_lights=False,
    )
    print(f"Export terminé : {output_glb_path}")


if __name__ == "__main__":
    main()
