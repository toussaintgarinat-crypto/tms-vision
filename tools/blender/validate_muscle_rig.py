"""Valide un muscle-rig.glb exporté par export_muscle_rig.py : vérifie que
les 9 BoneKey attendus sont présents dans le squelette, que le nombre exact
de maillages attendu est présent et réellement skinné (modifier Armature),
qu'aucun maillage exporté ne partage son datablock mesh avec un autre (la
cause racine du binding gauche/droite inversé, cf. correction "Critical #1"
du 2026-09-20 dans docs/superpowers/specs/2026-09-20-3d-posture-muscle-mesh-
design.md), et que chaque objet `.l`/`.r` est bien dominé par un os de son
propre côté. Pas un test Vitest classique (dépend d'un binaire externe non
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

# Compte exact, pas un plancher : vérifié par exécution réelle du pipeline
# contre le vrai Startup.blend (Tranche 3, correction du 2026-09-20). Sur les
# 55 objets muscle résolus par `rig_spec.resolve_muscle_objects()`, un seul
# ("Erector spinae.j") est une géométrie dégénérée (0 face) exclue par
# `export_muscle_rig.is_degenerate_mesh` — d'où 54, pas 55. Si ce nombre
# change (nouvelle version de Z-Anatomy, sous-ensemble de muscles modifié
# dans rig_spec.py), le mettre à jour ici en le re-vérifiant par exécution
# réelle, jamais en l'estimant.
EXPECTED_MESH_COUNT = 54

# Préfixes d'os valides côté gauche/droite. Un os "non latéralisé" (tronc/
# cou/racine) est un choix valide des deux côtés : un muscle de tronc comme
# "Rectus abdominis muscle.l" doit dominer sur `spine`, pas sur un os `L_*`
# qui n'existe pas pour lui.
NON_SIDED_BONES = {"root", "spine", "neck"}

# Muscles tronc/cou (rig_spec.TRUNK_NECK_MUSCLES) : depuis la correction de
# spec du 2026-09-20 (poids rigide déterministe, pas d'Automatic Weights —
# voir export_muscle_rig.apply_rigid_weight), ces objets doivent porter
# EXACTEMENT 100 % de poids sur leur unique os connu (spine/neck), 0 %
# partout ailleurs — une garantie mathématique exacte, pas juste "dominant".
# Table nom de base -> os, dérivée directement de rig_spec pour ne jamais
# désynchroniser ce validateur de la source de vérité.
TRUNK_NECK_BASE_NAMES = {
    base_name: bone_key
    for bone_key, base_names in rig_spec.TRUNK_NECK_MUSCLES.items()
    for base_name in base_names
}


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

    # Filtre "Icosphere" (primitive par défaut Blender, 42 sommets/80
    # faces) : repro isolée et confirmée (Blender 4.5.14 LTS) — même un
    # cube trivial + armature à 2 os, exporté via
    # `parent_set(ARMATURE_AUTO)` puis réimporté ici, fait apparaître un
    # objet "Icosphere" parasite. Le JSON glTF du .glb exporté (inspecté
    # directement, en dehors de Blender, octet par octet) ne contient
    # AUCUNE trace de cet objet : ni mesh, ni node de ce nom, quel que soit
    # le fichier (Z-Anatomy réel ou repro minimal). C'est donc un artefact
    # du RÉIMPORTATEUR glTF de Blender lui-même (déclenché par tout glTF
    # skinné via cette méthode, indépendamment des données Z-Anatomy),
    # jamais présent dans le fichier réellement exporté — on l'exclut donc
    # par son nom exact plutôt que de le traiter comme un défaut du .glb.
    meshes = [
        obj for obj in bpy.data.objects if obj.type == "MESH" and obj.name != "Icosphere"
    ]
    assert len(meshes) == EXPECTED_MESH_COUNT, (
        f"attendu exactement {EXPECTED_MESH_COUNT} maillages, trouvé {len(meshes)} : "
        f"{sorted(m.name for m in meshes)}"
    )

    unskinned = [
        mesh.name
        for mesh in meshes
        if not any(m.type == "ARMATURE" for m in mesh.modifiers)
    ]
    assert not unskinned, f"maillages sans modifier Armature (skinning manquant) : {unskinned}"

    # Invariant qui aurait détecté le Critical #1 (binding gauche/droite
    # inversé) : deux objets exportés ne doivent JAMAIS partager le même
    # datablock mesh. Z-Anatomy lie certains objets `.l`/`.r` au même
    # datablock (duplicata liés, miroir par la matrice d'objet) ; les poids
    # de vertex vivent dans le datablock, donc un partage fait que
    # `parent_set(ARMATURE_AUTO)` écrase les poids d'un côté par ceux de
    # l'autre pour la paire entière. `export_muscle_rig.py` dédoublonne
    # (`obj.data = obj.data.copy()`) avant de skinner ; on revérifie ici sur
    # le fichier réellement exporté, pas seulement sur le code source.
    datablock_owners: dict[str, list[str]] = {}
    for mesh in meshes:
        datablock_owners.setdefault(mesh.data.name, []).append(mesh.name)
    shared_datablocks = {
        data_name: owners for data_name, owners in datablock_owners.items() if len(owners) > 1
    }
    assert not shared_datablocks, (
        "des objets exportés partagent le même datablock mesh (binding "
        f"gauche/droite potentiellement inversé) : {shared_datablocks}"
    )
    assert all(mesh.data.users == 1 for mesh in meshes), (
        "au moins un datablock mesh a users != 1 malgré l'absence de "
        "doublon détecté par nom — incohérence à investiguer"
    )

    # Cohérence gauche/droite : pour tout objet `.l`/`.r`, l'os DOMINANT
    # (celui qui porte le plus de poids total, sommé sur tous les sommets et
    # tous les groupes de vertex de l'objet) doit être de son propre côté
    # (préfixe `L_`/`R_`) ou un os non latéralisé (tronc/cou/racine, valide
    # des deux côtés). "Dominant par poids total sommé" plutôt que, par
    # exemple, un vote par sommet : un même total pondéré par les poids
    # eux-mêmes (pas juste un décompte de groupes) reflète mieux quel os
    # anime réellement le maillage en moyenne à l'écran, et c'est directement
    # ce que `parent_set(ARMATURE_AUTO)` a écrit dans WEIGHTS_0 — c'est donc
    # l'agrégat le plus fidèle à ce qu'on veut vérifier (pas une approximation
    # jugée "équivalente", mais la définition la plus directe de "quel os
    # domine ce maillage").
    def dominant_bone(obj: bpy.types.Object) -> str | None:
        totals: dict[str, float] = {}
        for vertex in obj.data.vertices:
            for group_element in vertex.groups:
                weight = group_element.weight
                if weight <= 0.0:
                    continue
                bone_name = obj.vertex_groups[group_element.group].name
                totals[bone_name] = totals.get(bone_name, 0.0) + weight
        if not totals:
            return None
        return max(totals, key=totals.get)

    side_violations = []
    for mesh in meshes:
        if mesh.name.endswith(".l"):
            expected_prefix = "L_"
        elif mesh.name.endswith(".r"):
            expected_prefix = "R_"
        else:
            # Objet médian (repli "objet unique" de rig_spec, ex. un futur
            # muscle de tronc sans variante .l/.r) : aucun côté à vérifier.
            continue
        dominant = dominant_bone(mesh)
        if dominant is None:
            side_violations.append(f"{mesh.name}: aucun poids de vertex non nul")
            continue
        if dominant in NON_SIDED_BONES:
            continue
        if not dominant.startswith(expected_prefix):
            side_violations.append(
                f"{mesh.name}: os dominant '{dominant}' (attendu préfixe "
                f"'{expected_prefix}' ou un os non latéralisé {sorted(NON_SIDED_BONES)})"
            )
    assert not side_violations, (
        "binding gauche/droite incohérent (os dominant du mauvais côté) :\n"
        + "\n".join(side_violations)
    )

    # Poids rigide déterministe des muscles tronc/cou (correction de spec du
    # 2026-09-20, "poids rigide déterministe" — voir
    # export_muscle_rig.apply_rigid_weight) : pour chaque objet dont le nom
    # de base (sans suffixe `.l`/`.r`) figure dans `rig_spec.TRUNK_NECK_MUSCLES`,
    # on exige un poids de vertex EXACTEMENT 100 % sur son unique os connu et
    # 0 % partout ailleurs — pas seulement "dominant" (contrairement au
    # contrôle gauche/droite ci-dessus, qui tolère une bavure secondaire).
    # Rend cette garantie permanente et vérifiée mécaniquement, pas seulement
    # mesurée une fois au moment du correctif.
    rigid_violations = []
    for mesh in meshes:
        base_name = mesh.name[:-2] if mesh.name.endswith((".l", ".r")) else mesh.name
        expected_bone = TRUNK_NECK_BASE_NAMES.get(base_name)
        if expected_bone is None:
            continue
        nonzero_group_names = set()
        bad_weight_sum_vertices = 0
        for vertex in mesh.data.vertices:
            vertex_total = 0.0
            for group_element in vertex.groups:
                weight = group_element.weight
                if weight <= 0.0:
                    continue
                nonzero_group_names.add(mesh.vertex_groups[group_element.group].name)
                vertex_total += weight
            if abs(vertex_total - 1.0) > 1e-4:
                bad_weight_sum_vertices += 1
        if nonzero_group_names != {expected_bone}:
            rigid_violations.append(
                f"{mesh.name}: groupe(s) de vertex à poids non nul {sorted(nonzero_group_names)} "
                f"(attendu exactement {{'{expected_bone}'}}, poids rigide 100 % sur ce seul os)"
            )
        elif bad_weight_sum_vertices:
            rigid_violations.append(
                f"{mesh.name}: {bad_weight_sum_vertices} sommet(s) avec un poids total != 1.0 "
                f"sur '{expected_bone}' (attendu exactement 1.0 partout)"
            )
    assert not rigid_violations, (
        "poids rigide tronc/cou non exact (attendu 100 % sur l'os unique connu, 0 % ailleurs) :\n"
        + "\n".join(rigid_violations)
    )

    print(
        f"OK: {len(bone_names)} os, {len(meshes)} maillages skinnés, binding gauche/droite "
        f"cohérent, poids rigide tronc/cou exact sur {len(TRUNK_NECK_BASE_NAMES)} nom(s) de base."
    )


if __name__ == "__main__":
    main()
