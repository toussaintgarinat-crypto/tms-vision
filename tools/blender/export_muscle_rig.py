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
