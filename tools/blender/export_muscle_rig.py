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


def apply_rigid_weight(obj: bpy.types.Object, bone_key: str, armature_obj: bpy.types.Object) -> None:
    """Rattache `obj` de façon rigide et déterministe (poids 1.0 sur tous les
    sommets, 0.0 partout ailleurs) à l'os `bone_key` de `armature_obj` : crée
    un groupe de vertex nommé `bone_key` avec un poids plein sur tous les
    sommets, supprime tout autre groupe de vertex préexistant sur l'objet
    (garantit qu'aucune contribution résiduelle d'un autre groupe ne peut
    diluer ce poids dans `WEIGHTS_0` à l'export — 100 % sur ce seul os, pas
    "surtout" ce os), et s'assure qu'un modifier Armature pointant vers
    `armature_obj` existe.

    Utilisée pour deux cas distincts :
    1. Filet de sécurité historique quand le solveur "Bone Heat Weighting"
       (Automatic Weights) échoue à trouver une solution pour un muscle
       bi-articulaire de membre (voir l'appel dans `main()`, section
       automatic_weight_objects).
    2. Assignation SYSTÉMATIQUE et INCONDITIONNELLE pour tout muscle assigné
       à un os de `rig_spec.RIGID_WEIGHT_BONE_KEYS` (voir `main()`, section
       rigid_weight_objects) — ces objets ne passent jamais par le solveur
       heat-diffusion du tout. Contrairement aux muscles bi-articulaires
       (Biceps doit se répartir entre `L_upper_arm` et `L_forearm` pour bien
       se déformer à l'articulation du coude), les muscles tronc/cou/cuisse
       sont assignés avec certitude à un SEUL os (`spine`/`neck`, table
       `TRUNK_NECK_MUSCLES`, ou `L_thigh`/`R_thigh`) et ne traversent aucune
       articulation à préserver dans ce squelette à 9 os (pas d'os "jambe"
       sous la cuisse). Le blending heat-diffusion n'apporte donc aucun
       bénéfice pour eux et s'est révélé activement nuisible en pratique :
       dominante à tort pour le tronc/cou sur deux tentatives précédentes
       (voir la correction de spec 2026-09-20 sur le Latissimus dorsi :
       dominante à tort sur `L_upper_arm`/`R_upper_arm` puis, après un
       premier correctif, sur `neck` — jamais `spine` malgré deux
       repositionnements d'os successifs) et une bavure de poids mesurée
       vers `L_forearm`/`R_forearm` pour les muscles de cuisse (voir la
       correction de spec 2026-09-21 : jusqu'à 36 % sur ~5 % des sommets de
       `Vastus lateralis muscle.l`, bras qui pend près de la cuisse en pose
       de repos Z-Anatomy). Le poids rigide déterministe élimine cette
       classe de défaut par construction plutôt que par ajustement
       empirique."""
    for vg in list(obj.vertex_groups):
        obj.vertex_groups.remove(vg)
    vg = obj.vertex_groups.new(name=bone_key)
    vg.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    if not any(m.type == "ARMATURE" for m in obj.modifiers):
        modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
        modifier.object = armature_obj


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

    # L_upper_arm/R_upper_arm : position dérivée du vrai repère squelettique
    # (Humerus.l/.r), pas de la bbox des muscles Deltoïde+Biceps+Triceps qui
    # lui sont assignés. Motivation D'ORIGINE (2026-09-20, désormais
    # historique) : réduire la bavure de poids du Latissimus dorsi, dont la
    # bbox Deltoïde+Biceps+Triceps chevauchait géométriquement le muscle et
    # faisait ressortir l'os de bras comme dominant à tort sous Automatic
    # Weights. Cette motivation est SUPERSÉDÉE : le Latissimus dorsi (et tout
    # le tronc/cou) ne passe plus du tout par Automatic Weights depuis la
    # correction de spec du 2026-09-20 "fix définitif" — poids rigide
    # déterministe à la place (voir `rig_spec.RIGID_WEIGHT_BONE_KEYS` et
    # `apply_rigid_weight` ci-dessous), mécanisme totalement indépendant de ce
    # repositionnement d'os.
    #
    # CE N'EST PAS DU CODE MORT — ne pas supprimer sous prétexte que la
    # justification Latissimus dorsi d'origine est obsolète. Raison ACTUELLE,
    # toujours valide : ce repositionnement reste nécessaire pour la qualité
    # du skinning des ~28 muscles upper_arm/forearm qui, eux, passent
    # toujours par Automatic Weights (seul cas réellement bi-articulaire —
    # coude — de ce squelette à 9 os). Repositionner l'os sur le vrai humérus
    # a mesurablement amélioré leur pondération aussi, pas seulement celle du
    # Latissimus dorsi : ex. `Long head of biceps brachii.r` passait de
    # justesse de `R_forearm` (53,5 %) devant `R_upper_arm` (46,5 % —
    # risque de dominante côté os du coude au lieu du bras) avant ce
    # correctif ; après, `R_upper_arm` domine clairement à 83,8 % (voir la
    # correction de spec du 2026-09-20 sur le repositionnement humérus).
    # Uniquement ces deux os : les autres (spine, neck, forearm, thigh)
    # restent dérivés de la bbox des muscles, correctif ciblé pour ne pas
    # risquer de régression ailleurs.
    skeletal_landmarks = rig_spec.resolve_skeletal_landmarks()

    bone_positions = {"root": (root_head, root_tail)}
    for bone_key in rig_spec.BONE_ORDER:
        if bone_key == "root":
            continue
        if bone_key in skeletal_landmarks:
            bone_positions[bone_key] = rig_spec.bone_head_tail(
                [skeletal_landmarks[bone_key]], ascending=False
            )
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

    obj_to_bone_key = {
        obj.name: bone_key for bone_key, objs in muscles_by_bone.items() for obj in objs
    }

    # Séparation poids rigide déterministe (tronc/cou/cuisse) vs. Automatic
    # Weights (heat-diffusion, blending bi-articulaire genuinement utile
    # pour ces os). La frontière n'est plus "est-ce un objet tronc/cou ?"
    # mais, généralisée : "l'os assigné a-t-il un partenaire bi-articulaire
    # (une seconde articulation représentée dans ce squelette à 9 os) à
    # préserver ?" — `rig_spec.RIGID_WEIGHT_BONE_KEYS` (spine, neck,
    # L_thigh, R_thigh) répond non ; `L_upper_arm`/`L_forearm`/
    # `R_upper_arm`/`R_forearm` (seuls os hors de cet ensemble) répondent
    # oui, coude réel entre les deux. Pour les os "non" : le solveur
    # heat-diffusion de Blender, qui considère toute l'armature et toute la
    # topologie du maillage plutôt que le seul os le plus proche, ne trouve
    # pas de dominante correcte pour le tronc/cou (voir la correction de
    # spec 2026-09-20 sur le Latissimus dorsi : dominante à tort sur
    # `L_upper_arm`/`R_upper_arm` puis sur `neck`, jamais `spine`) et
    # produit une bavure de poids mesurée vers `L_forearm`/`R_forearm` pour
    # la cuisse, où le bras pend à proximité en pose de repos Z-Anatomy
    # (correction de spec 2026-09-21) — voir `apply_rigid_weight` ci-dessus
    # pour la justification complète.
    rigid_weight_objects = [
        obj
        for bone_key in rig_spec.RIGID_WEIGHT_BONE_KEYS
        for obj in muscles_by_bone[bone_key]
    ]
    automatic_weight_objects = [
        obj
        for bone_key, objs in muscles_by_bone.items()
        if bone_key not in rig_spec.RIGID_WEIGHT_BONE_KEYS
        for obj in objs
    ]
    assert len(rigid_weight_objects) + len(automatic_weight_objects) == len(all_muscle_objects)
    print(
        f"Poids rigide déterministe (tronc/cou/cuisse) : {len(rigid_weight_objects)} objet(s). "
        f"Automatic Weights (upper_arm/forearm) : {len(automatic_weight_objects)} objet(s)."
    )

    # Tronc/cou/cuisse : parentage à l'armature SANS calcul de poids
    # (type="ARMATURE", pas "ARMATURE_AUTO" — aucun solveur heat-diffusion
    # n'est jamais invoqué pour ces objets), puis poids rigide 1.0
    # déterministe appliqué directement sur l'os connu de chaque objet.
    if rigid_weight_objects:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in rigid_weight_objects:
            obj.select_set(True)
        armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.parent_set(type="ARMATURE")
        for obj in rigid_weight_objects:
            apply_rigid_weight(obj, obj_to_bone_key[obj.name], armature_obj)

    # Upper_arm/forearm : Automatic Weights (heat-diffusion) — seul cas
    # bi-articulaire de ce squelette (ex. Biceps brachii doit se répartir
    # entre `L_upper_arm` et `L_forearm` pour bien se déformer au coude),
    # déjà vérifié sans régression lors des corrections de spec précédentes.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in automatic_weight_objects:
        obj.select_set(True)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")

    # Filet de sécurité (upper_arm/forearm uniquement — les objets
    # tronc/cou/cuisse ne passent jamais par le solveur heat-diffusion, cet
    # échec ne peut donc pas les concerner) : le solveur "Bone Heat
    # Weighting" de Blender peut échouer de façon non déterministe pour un
    # petit sous-ensemble de maillages (observé concrètement sur le vrai
    # Startup.blend : 1-3 objets selon l'exécution — maillages fermés,
    # manifold, sans anomalie topologique ni de normales détectable par
    # rapport aux maillages voisins qui, eux, se skinnent sans problème ;
    # log Blender : "Bone Heat Weighting: failed to find solution for one or
    # more bones"). Dans ce cas, un modifier Armature ET des groupes de
    # vertex (un par os) sont bien créés, mais avec un poids total nul
    # partout — l'exportateur glTF considère alors le maillage comme non
    # skinné et n'émet aucune donnée de skin pour lui. Pour tout objet sans
    # aucun poids non nul après Automatic Weights, on applique le même
    # repli déterministe que le tronc/cou/cuisse (`apply_rigid_weight`) :
    # rattachement rigide à son os logique, déjà connu via `muscles_by_bone`.
    heat_weighting_failures = []
    for obj in automatic_weight_objects:
        has_weight = any(g.weight > 0.0 for v in obj.data.vertices for g in v.groups)
        if has_weight:
            continue
        heat_weighting_failures.append(obj.name)
        apply_rigid_weight(obj, obj_to_bone_key[obj.name], armature_obj)
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
