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
