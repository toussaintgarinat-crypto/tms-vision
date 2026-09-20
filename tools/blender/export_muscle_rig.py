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


def unhide_all_collections(layer_collection: bpy.types.LayerCollection) -> None:
    """Certaines collections du fichier source sont exclues de la view
    layer par défaut (atlas à ~7000 objets, organisé par système
    anatomique) : un objet dans une collection exclue reste invisible
    (`obj.visible_get() == False`) même après avoir démasqué ses propres
    flags (`hide_set`/`hide_viewport`), et `select_set(True)` n'a alors
    aucun effet réel sur lui. Corrige ceci récursivement, à tous les
    niveaux de la hiérarchie de collections."""
    layer_collection.exclude = False
    layer_collection.hide_viewport = False
    layer_collection.collection.hide_viewport = False
    for child in layer_collection.children:
        unhide_all_collections(child)


def is_degenerate_mesh(obj: bpy.types.Object) -> bool:
    """Vrai si l'objet mesh n'a aucune face réelle. Repéré concrètement sur
    le vrai Startup.blend : l'objet "Erector spinae.j" (celui que
    `rig_spec` résout par son nom réel, vérifié) ne contient que 2 sommets
    et 0 face — un stub/placeholder cassé du fichier source, pas une
    géométrie musculaire valide (les seules autres variantes "Erector
    spinae" du fichier sont les duplicata outline/highlight ".ol"/".or",
    déjà exclus par convention du projet et de toute façon trop petits —
    52 sommets — pour être une vraie géométrie). Un tel objet ne peut ni
    être skinné (rien à pondérer) ni être exporté correctement en glTF :
    l'exportateur Blender le remplace silencieusement par un icosphère
    générique par défaut (42 sommets) au lieu d'échouer proprement, d'où
    l'objet "Icosphere" parasite observé dans les exports précédents. On
    l'exclut donc explicitement ici, en amont, plutôt que de laisser
    l'exportateur produire ce succédané."""
    return len(obj.data.polygons) == 0


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
    unhide_all_collections(bpy.context.view_layer.layer_collection)

    muscles_by_bone = rig_spec.resolve_muscle_objects()
    resolved_count = sum(len(objs) for objs in muscles_by_bone.values())
    print(f"Muscles résolus : {resolved_count} objets sur {len(muscles_by_bone)} os.")

    degenerate_names = []
    for bone_key, objs in muscles_by_bone.items():
        kept, dropped = [], []
        for obj in objs:
            (dropped if is_degenerate_mesh(obj) else kept).append(obj)
        muscles_by_bone[bone_key] = kept
        degenerate_names.extend(obj.name for obj in dropped)
    if degenerate_names:
        print(
            f"ATTENTION : {len(degenerate_names)} objet(s) exclu(s) de l'export "
            f"(géométrie dégénérée, 0 face — voir is_degenerate_mesh) : "
            f"{degenerate_names}"
        )
    all_muscle_objects = [obj for objs in muscles_by_bone.values() for obj in objs]
    print(f"Muscles exportés après filtrage : {len(all_muscle_objects)} objets.")

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

    # Avant parent_set : Z-Anatomy partage un même datablock mesh entre les
    # objets .l et .r (duplicata liés, miroir par la matrice d'objet). Les
    # poids de vertex vivant dans le mesh, Automatic Weights écraserait les
    # poids d'un côté par ceux de l'autre.
    for obj in all_muscle_objects:
        if obj.data.users > 1:
            obj.data = obj.data.copy()
    assert all(obj.data.users == 1 for obj in all_muscle_objects)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in all_muscle_objects:
        obj.select_set(True)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")

    # Filet de sécurité : le solveur "Bone Heat Weighting" de Blender peut
    # échouer de façon non déterministe pour un petit sous-ensemble de
    # maillages (observé concrètement sur le vrai Startup.blend : 2-3
    # objets sur 55 selon l'exécution, ex. "Descending part of trapezius
    # muscle.l"/".r" — maillages fermés, manifold, sans anomalie
    # topologique ni de normales détectable par rapport aux maillages
    # voisins qui, eux, se skinnent sans problème ; log Blender :
    # "Bone Heat Weighting: failed to find solution for one or more
    # bones"). Dans ce cas, un modifier Armature ET des groupes de vertex
    # (un par os) sont bien créés, mais avec un poids total nul partout —
    # l'exportateur glTF considère alors le maillage comme non skinné et
    # n'émet aucune donnée de skin pour lui. Pour tout objet sans aucun
    # poids non nul après Automatic Weights, on applique un repli
    # déterministe : rattachement rigide (poids 1.0 sur tous les sommets)
    # à son os logique, déjà connu via `muscles_by_bone`.
    obj_to_bone_key = {
        obj.name: bone_key for bone_key, objs in muscles_by_bone.items() for obj in objs
    }
    heat_weighting_failures = []
    for obj in all_muscle_objects:
        has_weight = any(g.weight > 0.0 for v in obj.data.vertices for g in v.groups)
        if has_weight:
            continue
        heat_weighting_failures.append(obj.name)
        bone_key = obj_to_bone_key[obj.name]
        vg = obj.vertex_groups.get(bone_key) or obj.vertex_groups.new(name=bone_key)
        vg.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
            modifier.object = armature_obj
    if heat_weighting_failures:
        print(
            f"ATTENTION : repli poids rigide appliqué (Bone Heat Weighting sans "
            f"solution) pour {len(heat_weighting_failures)} objet(s) : "
            f"{heat_weighting_failures}"
        )

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
