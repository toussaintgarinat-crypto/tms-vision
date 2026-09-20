# Avatar 3D de posture — Tranche 3 : vrais maillages musculaires (Z-Anatomy)

**Date** : 2026-09-20
**Statut** : Approuvé (implémentation reportée à une session ultérieure, à la demande de l'utilisateur du projet)

## Note sur la numérotation des tranches

La spec de la Tranche 1 (`2026-09-16-3d-posture-avatar-design.md`) désignait par « Tranche 2 » l'intégration des muscles et par « Tranche 3 » leur coloration/activation. La Tranche 2 réellement livrée (`2026-09-16-3d-posture-skeleton-rig-design.md`) a consommé ce numéro pour le squelette articulé (préalable technique découvert nécessaire en cours de route). **Ce document adopte la numérotation réelle** : Tranche 2 = squelette articulé (livrée), Tranche 3 (ce document) = vrais maillages musculaires, une Tranche 4 future = coloration/activation par muscle selon les sous-scores RULA. Le README et `docs/superpowers/specs/2026-09-16-3d-posture-skeleton-rig-design.md` référencent déjà cette tranche sous ce nom.

## Contexte

La Tranche 2 a livré un squelette articulé (`web/app/pose3dSkeleton.ts` — 8 os + racine, `THREE.Bone`/`THREE.Skeleton`, bind pose en espace monde, longueurs fixes par os en mètres) et un maillage de test non anatomique (cylindres) pour prouver que le mécanisme de skinning fonctionne. Cette tranche remplace ce maillage de test par de vrais muscles.

**Recherche faite avant ce document** (voir aussi le brainstorming de la Tranche 2, qui avait identifié ces inconnues) :

- **Z-Anatomy est un atlas statique, confirmé sans armature ni poids de peau.** Vérifié à la fois par la documentation du dépôt (`github.com/Z-Anatomy/The-blend`) et en inspectant directement le fichier `Startup.blend` réel via un script Blender headless (`bpy.data.objects` filtré sur `type == "ARMATURE"` → liste vide, sur 7184 objets). Il existe un rig communautaire séparé (« Z-Biomechanics ») qui riggue le squelette osseux, mais explicitement pas les muscles/tissus mous, sans dépôt officiel (partagé via des liens de paste temporaires sur un forum) — non réutilisable pour cette tranche.
- **Le weight-painting manuel de la musculature complète (~600 muscles, décision prise en Tranche 2) est un chantier de plusieurs semaines, confirmé et non plus hypothétique.** Décision prise avec l'utilisateur du projet : réduire le périmètre à un sous-ensemble de muscles majeurs pour cette tranche, la musculature complète devenant une extension future explicitement hors périmètre ici.
- **Le modèle Z-Anatomy est à l'échelle métrique réelle**, vérifié par inspection directe du fichier : silhouette totale ≈ 1,88 m (bounding box), humérus mesuré à 31,8 cm (`bpy` sur l'objet `Humerus.r`), axe Z vers le haut, unités Blender = mètres (`unit_settings.system == "METRIC"`, `scale_length == 1.0`). Compatible sans conversion avec les données MediaPipe (déjà en mètres) utilisées par `pose3dSkeleton.ts`.
- **Chaque structure anatomique est nommée individuellement** selon la Terminologia Anatomica (ex. collection « Deltoid muscle » contenant 3 objets : parties acromiale/claviculaire/scapulaire, suffixes `.l`/`.r` pour gauche/droite). Sélectionner un sous-ensemble de muscles par leur nom de collection est direct.
- **Blender est installé et scriptable en local** (`brew install --cask blender`, exécution headless via `blender --background --python script.py` déjà vérifiée sur le fichier réel).

Cette recherche change l'approche technique par rapport à ce qui était envisagé en Tranche 2 (weight-painting manuel ou skinning approximatif par proximité géométrique codé à la main) : Blender fournit un algorithme de skinning automatique testé (**Automatic Weights**, diffusion de chaleur), et son exportateur **glTF** intégré gère nativement les données de skinning et la conversion d'axes Z-up → Y-up. Le pipeline recommandé s'appuie dessus plutôt que de réinventer ces deux briques.

## Décisions de cadrage

- **Sous-ensemble de muscles majeurs, pas la musculature complète.** ~17 groupes musculaires (voir liste ci-dessous), choisis pour leur pertinence RULA (couvrent les zones déjà scorées : cou, tronc, épaule/bras, avant-bras) et leur correspondance directe avec les 8 os existants. La musculature complète (~600 muscles) est un chantier futur explicitement hors périmètre.
- **Pipeline d'export Blender → glTF, pas de skinning fait main.** Une armature Blender est générée par script avec exactement la même hiérarchie que `pose3dSkeleton.ts` (mêmes noms d'os, mêmes longueurs `BONE_LENGTH`), les muscles sélectionnés y sont rattachés via **Automatic Weights** (algorithme de diffusion de chaleur natif de Blender — gère les muscles bi-articulaires mieux qu'un rattachement rigide au bone le plus proche), puis le tout est exporté en un fichier **`.glb`** (glTF binaire, autoporteur) via l'exportateur glTF intégré de Blender.
- **`pose3dSkeleton.ts` n'est pas modifié.** Le calcul de rotation par frame (`applyFrameToSkeleton`) reste exactement le même ; au runtime, on retrouve les os du squelette **importé** par leur nom (`BoneKey`) et on leur applique les mêmes rotations qu'au squelette de test de la Tranche 2. C'est le principal bénéfice architectural de la Tranche 2 : le calcul de pose est découplé du maillage qui l'affiche.
- **Couleur uniforme par frame, inchangée depuis la Tranche 1/2.** Pas de coloration par muscle individuel dans cette tranche (reportée à une Tranche 4 future, cohérent avec ce qui était déjà prévu). Concrètement, la teinte de l'`action_level` courant est appliquée à **tous** les matériaux des muscles importés (potentiellement plusieurs dizaines de matériaux, un par muscle/partie), pas à un seul matériau comme en Tranche 2.

  > **Correction (2026-09-20, vérification manuelle Task 7)** : cette teinte ne s'affichait en
  > réalité **jamais** avant correctif, pour deux raisons invisibles en revue de code statique
  > (Tasks 1-6) et détectées uniquement en faisant réellement tourner l'avatar dans un navigateur.
  >
  > 1. **Les 12 matériaux exportés par le pipeline Blender portent un `emissiveFactor` blanc
  >    (1, 1, 1) sans texture d'émission** (confirmé en parsant directement le JSON glTF de
  >    `muscle-rig.glb`). À pleine intensité, ce terme émissif s'ajoute au rendu indépendamment de
  >    `material.color` et sature l'image en blanc — origine probable : un réglage d'émission par
  >    défaut du matériau Blender/Principled BSDF de Z-Anatomy, jamais neutralisé par
  >    `export_muscle_rig.py`. Non corrigé côté Blender (aurait obligé à rejouer tout le pipeline
  >    Automatic Weights, non déterministe — voir la correction ci-dessus sur le solveur) ; corrigé
  >    côté rendu en mettant `clone.emissive` à zéro sur chaque matériau cloné dans
  >    `PostureAvatar3D.tsx`.
  > 2. **`mesh.material = clone` était affecté comme effet de bord à l'intérieur d'un `useMemo`**,
  >    qui doit rester pur. En Strict Mode (React 18, actif par défaut en `next dev` — l'environnement
  >    utilisé pour toute vérification manuelle de ce projet), React rejoue deux fois le corps du
  >    composant pour détecter ce genre d'impureté ; cela créait deux générations de matériaux
  >    clonés et laissait le mesh réellement affiché attaché à la mauvaise génération (jamais
  >    recolorée par la boucle `useFrame`), démontré par inspection directe des `uuid` des matériaux
  >    en jeu. Corrigé en clonant `gltf.scene` par montage (`SkeletonUtils.clone`, qui préserve les
  >    liaisons squelette/SkinnedMesh, contrairement à un `Object3D.clone` nu) plutôt que de muter la
  >    scène partagée/mémoïsée par `useGLTF`, et en déplaçant l'affectation `mesh.material` dans un
  >    `useEffect` séparé et idempotent.
  >
  > Revérifié en direct dans le navigateur après correctif (commit séparé) : la couleur de l'avatar
  > change bien (jaune/orange/rouge, les trois niveaux non « acceptable » observés sur
  > `moi coupe.mp4`) en suivant l'`action_level` courant au fil de la lecture, uniformément sur
  > l'ensemble des muscles. Enseignement pour la suite du projet : une mutation d'effet de bord
  > (`objet.propriété = valeur` sur un objet THREE.js externe à React) ne doit jamais être placée
  > dans un `useMemo`, même quand ça « marche » en apparence — Strict Mode la rend visible dès qu'on
  > regarde vraiment le rendu, pas seulement le code.

- **Attribution CC BY-SA obligatoire.** Les maillages sont dérivés de BodyParts3D via Z-Anatomy (licence CC BY-SA 4.0). Un fichier `NOTICE.md` à la racine du projet et un crédit visible dans l'interface (ex. pied de page ou info-bulle près de l'avatar 3D) sont requis avant toute mise en production. Le wording exact est à finaliser à l'implémentation, pas figé ici.
- **Le fichier source Z-Anatomy (`Startup.blend`, ~293 Mo) n'est pas commité au dépôt.** Trop volumineux, re-téléchargeable depuis `github.com/Z-Anatomy/The-blend` (fichier `Z-Anatomy.zip` à la racine du dépôt). Le script d'export documente l'URL et les instructions de téléchargement. Seul le `.glb` final (résultat de l'export, attendu nettement plus petit — à mesurer à l'implémentation) est commité dans `web/public/`.
- **Correctifs manuels après Automatic Weights, attendus et acceptés.** L'algorithme de diffusion de chaleur n'est pas parfait (ex. bavures de poids entre muscles proches de l'avant-bras). Une passe de vérification visuelle après export (et retouche manuelle ponctuelle dans Blender si besoin) fait partie du travail normal de cette tranche, pas un signe d'échec du pipeline.

  > **Correction (2026-09-20, après exécution réelle du pipeline)** : l'exécution contre le vrai
  > `Startup.blend` a révélé deux limites non anticipées par ce document.
  >
  > 1. **« Erector spinae » n'a aucune géométrie utilisable dans le fichier source.** Le seul objet
  >    de ce nom résolu par `rig_spec.py` (`Erector spinae.j`) ne contient que 2 sommets et 0 face
  >    (stub cassé du fichier Z-Anatomy) ; les seules autres variantes (`.ol`/`.or`) sont des
  >    duplicata outline explicitement exclus par convention. `export_muscle_rig.py` détecte et
  >    exclut désormais tout maillage dégénéré (0 face) avant l'export plutôt que de laisser
  >    l'exportateur glTF le remplacer silencieusement par un icosphère par défaut. Conséquence :
  >    le rig final contient **54 muscles, pas 55** — le tronc (os `spine`) n'a plus que Rectus
  >    abdominis, External abdominal oblique et Latissimus dorsi (les érecteurs du rachis manquent).
  >    Limite de donnée source, pas de choix arbitraire ; reste à corriger si une version plus
  >    complète de Z-Anatomy devient disponible.
  > 2. **Le solveur "Bone Heat Weighting" de Blender échoue parfois, de façon non déterministe,
  >    sur 1 à 3 des 54 muscles selon l'exécution** (observé sur plusieurs runs, ex. « Descending
  >    part of trapezius muscle »), sans anomalie topologique détectable sur les maillages
  >    concernés (manifold, une seule île, normales cohérentes avec leurs voisins qui, eux, se
  >    skinnent sans problème) — limitation connue du solveur sur des maillages anatomiques
  >    complexes, pas un défaut de nos données ou de notre script. **Décision utilisateur** : plutôt
  >    que de laisser ces muscles totalement non skinnés ou de faire échouer tout l'export sur un
  >    solveur non déterministe, `export_muscle_rig.py` applique un filet de sécurité — poids
  >    rigide 1.0, codé en dur, sur l'os logique déjà connu via `rig_spec.resolve_muscle_objects()`
  >    — pour tout muscle dont Automatic Weights ne trouve aucune solution. C'est un écart assumé
  >    par rapport à l'affirmation ci-dessus (« pas de skinning fait main »), limité aux seuls cas
  >    où l'algorithme automatique échoue purement et simplement, jamais utilisé comme raccourci
  >    général. Le rig final reste skinné à 100 % dans tous les cas.

  > **Correction (2026-09-20, revue finale de branche complète)** : une revue de code indépendante,
  > portant sur l'ensemble de la branche, a décodé directement les données binaires de skin
  > (`JOINTS_0`/`WEIGHTS_0`) du `muscle-rig.glb` commité et trouvé un bug réel et sérieux, non
  > détecté par les vérifications précédentes (aucune n'avait décodé le contenu binaire du skin
  > exporté, seulement sa présence).
  >
  > 1. **Les 20 muscles de membre gauche étaient skinnés sur les os DROITS.** Cause racine : le
  >    `.glb` contenait 27 noms de mesh uniques, chacun utilisé par exactement 2 nodes (`.l` et
  >    `.r`). Blender impose des noms de datablock uniques dans `bpy.data.meshes` : deux objets
  >    exportés de même nom ne peuvent provenir que d'UN SEUL datablock mesh partagé — les objets
  >    gauche/droite de Z-Anatomy sont des duplicata liés, miroités par la matrice d'objet (pas une
  >    géométrie indépendante par côté). Les poids de vertex vivant dans le datablock mesh (seule la
  >    liste des noms de groupes est par-objet), `parent_set(type="ARMATURE_AUTO")` exécuté sur les
  >    deux objets à la fois écrivait dans une seule couche de poids partagée : le côté traité en
  >    dernier gagnait pour les deux. Invisible pour les 7 datablocks tronc/cou (les deux côtés
  >    pointent de toute façon vers le même os `spine`/`neck`) — c'est exactement pour cette raison
  >    que le bug est passé inaperçu jusqu'à ce décodage binaire direct.
  >    **Correctif** : dans `export_muscle_rig.py`, juste avant `parent_set(ARMATURE_AUTO)`, chaque
  >    objet dont `obj.data.users > 1` reçoit une copie privée de son datablock
  >    (`obj.data = obj.data.copy()`), avec une assertion (`obj.data.users == 1` pour tous) qui fait
  >    échouer l'export si un partage subsiste. Ré-exécution réelle du pipeline contre le vrai
  >    `Startup.blend` : toujours 54 muscles (aucun changement de compte), et décodage indépendant du
  >    nouveau `.glb` (binaire `JOINTS_0`/`WEIGHTS_0`, hors Blender) confirmant que l'os dominant de
  >    chaque objet `.l`/`.r` de membre est désormais bien du bon côté sur l'ensemble des 54 objets.
  >    `validate_muscle_rig.py` vérifie désormais cet invariant structurellement (pas seulement visé
  >    par relecture) : aucun datablock mesh partagé entre objets exportés, et os dominant du bon
  >    côté pour chaque objet `.l`/`.r`.
  > 2. **Le correctif ci-dessus n'a PAS résolu la bavure de poids mesurée sur les muscles de tronc**
  >    (ex. Latissimus dorsi). Hypothèse de départ (partage de datablock entre les objets `.l`/`.r`
  >    du tronc eux-mêmes, donc corrigée par le même correctif) infirmée par remesure directe sur le
  >    nouveau `.glb` : `Latissimus dorsi muscle.l` reste dominé à 45 % par `L_upper_arm` (37 % `neck`,
  >    17 % `spine`) et `.r` à 47 % par `R_upper_arm` — quasi identique aux chiffres d'avant
  >    correctif. C'est donc un problème de qualité de poids distinct, pas un symptôme du bug de
  >    datablock partagé : la diffusion de chaleur de Blender, appliquée à un muscle en nappe qui
  >    s'étend du bassin jusqu'à l'aisselle/l'humérus, ne trouve pas de dominante nette entre `spine`,
  >    `neck` et `L_upper_arm`/`R_upper_arm` (aucun des trois ne dépasse ~45 %). C'est plus grave que
  >    la « bavure entre muscles proches de l'avant-bras » anticipée par la puce ci-dessus : ici, l'os
  >    dominant lui-même est le mauvais, pas seulement une contamination secondaire d'un os par
  >    ailleurs correctement dominant. `External abdominal oblique muscle` et `Transverse part of
  >    trapezius muscle`, en revanche, gardent un os dominant correct (`spine` à ~62-64 %, `neck` à
  >    ~60-64 % respectivement) malgré une bavure secondaire non négligeable vers les os de membre.
  >    **Non corrigé dans cette passe** : corriger la répartition fine des poids du Latissimus dorsi
  >    demanderait soit une retouche manuelle du weight-painting dans Blender (repeindre
  >    explicitement vers `spine`), soit un ajustement de la position calculée de l'os `L_upper_arm`/
  >    `R_upper_arm` (actuellement dérivée de la bounding box des muscles de bras, pas d'un repère
  >    squelettique réel), les deux hors périmètre de cette correction. Reste un point ouvert, à
  >    traiter dans une session ultérieure si la déformation du Latissimus dorsi s'avère visuellement
  >    gênante en posture réelle.

  > **Correction (2026-09-20, tentative de correction ciblée du point ouvert ci-dessus — amélioration
  > partielle, pas une résolution complète)** : suite à l'investigation qui a diagnostiqué le
  > chevauchement géométrique bbox-Deltoïde/Biceps/Triceps ↔ Latissimus dorsi comme cause probable,
  > `rig_spec.py` gagne `resolve_skeletal_landmarks()` qui résout les vrais objets `Humerus.l`/
  > `Humerus.r` du `Startup.blend` (vérifiés directement via `bpy.data.objects` : 2143 sommets / 4280
  > faces chacun, longueur monde ~31.76 cm, cohérent avec la mesure ~31.8 cm du brainstorming initial).
  > `export_muscle_rig.py` dérive désormais la position des os `L_upper_arm`/`R_upper_arm`
  > (uniquement ces deux os — `spine`/`neck`/`forearm`/`thigh` restent dérivés de la bbox des muscles,
  > correctif ciblé) depuis la bbox de l'humérus réel plutôt que celle des muscles de bras.
  >
  > Ré-exécution réelle du pipeline (54 muscles, aucun changement de compte) et remesure directe du
  > nouveau `.glb` (binaire `JOINTS_0`/`WEIGHTS_0`) :
  > - **Latissimus dorsi muscle.l** : `L_upper_arm` chute de 45,4 % à 34,3 % (bavure vers le bras
  >   nettement réduite) et `spine` progresse de 17,5 % à 20,5 % — mais l'os dominant devient
  >   **`neck`** (36,7 % → 44,5 %), pas `spine`. **`.r`** : `R_upper_arm` 47,2 % → 34,7 %, `spine`
  >   16,0 % → 18,9 %, dominant devient `neck` (36,7 % → 46,4 %). **Le défaut ciblé (dominante sur
  >   l'os de bras) est corrigé, mais le muscle reste mal dominé — par `neck` au lieu de `spine`.**
  >   Le rapprochement géométrique de l'os `L_upper_arm`/`R_upper_arm` vers l'axe huméral (loin du
  >   dos) a bien réduit son influence sur la diffusion de chaleur du Latissimus dorsi, mais a
  >   mécaniquement fait ressortir `neck` (déjà secondaire à ~37 % avant ce correctif) comme nouvelle
  >   dominante, sans qu'aucun ajustement n'ait visé `neck`. Objectif produit non pleinement atteint.
  > - **Transverse part of trapezius muscle** : bavure vers l'os de bras réduite sur les deux côtés
  >   (`.l` : `L_upper_arm` 36,4 % → 20,4 %, `neck` dominant 63,6 % → 79,6 % ; `.r` : `R_upper_arm`
  >   40,0 % → 24,7 %, `neck` dominant 60,0 % → 75,3 %) — nette amélioration, dominante déjà correcte
  >   avant et après.
  > - **External abdominal oblique muscle** : bavure vers l'os de bras réduite (`.l` : `L_upper_arm`
  >   20,2 % → 18,3 %, `spine` dominant 64,4 % → 67,5 % ; `.r` : `R_upper_arm` 22,0 % → 20,3 %,
  >   `spine` dominant 62,0 % → 65,4 %) — amélioration, dominante déjà correcte avant et après.
  > - **Aucune régression détectée sur les muscles de bras déjà correctement pondérés** (Deltoïde x3,
  >   Biceps brachii x2, Triceps brachii x3, Brachioradialis — `.l` et `.r`) : tous restent dominants
  >   sur leur bon os `upper_arm`/`forearm`, et certains cas limites s'améliorent nettement — ex.
  >   `Long head of biceps brachii.r` passait de justesse de `R_forearm` (53,5 %) devant `R_upper_arm`
  >   (46,5 %) avant ce correctif ; après, `R_upper_arm` domine clairement à 83,8 %.
  >
  > **Bilan honnête** : amélioration réelle et mesurée (bavure vers `upper_arm` réduite d'environ
  > moitié sur les 3 muscles de tronc concernés, aucune régression, muscles de bras déjà corrects
  > renforcés), mais **le Latissimus dorsi n'a pas atteint la dominante `spine` attendue** — reste
  > dominé par un os incorrect (`neck` au lieu de `L_upper_arm`/`R_upper_arm`). Point ouvert non
  > refermé : une correction complète demanderait probablement un ajustement séparé pour `neck`
  > (même diagnostic de chevauchement géométrique, cette fois avec la bbox Trapèze/SCM) et/ou une
  > retouche manuelle du weight-painting, toujours hors périmètre de ce correctif ciblé.

  > **Correction (2026-09-20, fix définitif — changement d'approche, pas un nouvel ajustement de
  > position d'os)** : les deux tentatives précédentes ci-dessus repositionnaient des os individuels
  > pour tenter d'influencer le résultat du solveur Automatic Weights (heat-diffusion) de Blender —
  > une approche jugée "whack-a-mole" après coup : le solveur considère toute l'armature et toute la
  > topologie du maillage, pas seulement l'os le plus proche, et le Latissimus dorsi est un muscle en
  > nappe qui s'étend du bassin jusqu'à l'aisselle/l'épaule, géométriquement ambigu entre `spine`,
  > `neck` et `L_upper_arm`/`R_upper_arm` quel que soit le repositionnement d'un seul os. Changement
  > d'approche, à la demande explicite de l'humain après ces deux tentatives : pour tout objet résolu
  > sous `rig_spec.TRUNK_NECK_MUSCLES` (Erector spinae, Rectus abdominis muscle, External abdominal
  > oblique muscle, Latissimus dorsi muscle, Ascending/Transverse/Descending part of trapezius
  > muscle, Sternocleidomastoid muscle), on **n'invoque plus jamais Automatic Weights du tout** :
  > `export_muscle_rig.py` sépare désormais explicitement `trunk_neck_objects` (parentés via
  > `parent_set(type="ARMATURE")`, sans calcul de poids) de `limb_objects` (seuls à passer par
  > `parent_set(type="ARMATURE_AUTO")`, heat-diffusion), puis assigne à chaque objet tronc/cou un poids
  > rigide déterministe — 100 % sur son unique os connu avec certitude (`spine` ou `neck`, table
  > `TRUNK_NECK_MUSCLES`), 0 % partout ailleurs — via une nouvelle fonction `apply_rigid_weight()`,
  > généralisée depuis le filet de sécurité existant qui appliquait déjà ce même mécanisme (poids 1.0
  > sur tous les sommets) au cas, plus étroit, où le solveur Bone Heat Weighting échouait à trouver
  > une solution pour un muscle de MEMBRE. Justification du choix : ces muscles tronc/cou ne sont pas
  > bi-articulaires (contrairement aux muscles de membre — ex. Biceps brachii, qui doit se répartir
  > entre `L_upper_arm` et `L_forearm` pour bien se déformer au coude) — le blending heat-diffusion
  > n'apporte donc aucun bénéfice pour cette catégorie et s'est révélé, sur deux tentatives, activement
  > nuisible.
  >
  > Ré-exécution réelle du pipeline (`Muscles résolus : 55 objets sur 8 os`, 1 exclu pour géométrie
  > dégénérée — `Erector spinae.j`, inchangé — donc toujours 54 muscles exportés ; log ajouté :
  > `Poids rigide déterministe (tronc/cou) : 14 objet(s). Automatic Weights (membres) : 40 objet(s).`
  > — 0 échec Bone Heat Weighting sur cette exécution) et décodage binaire indépendant du nouveau
  > `.glb` (`JOINTS_0`/`WEIGHTS_0`, sans passer par Blender, avec agrégation par sommet des poids sur
  > tous les groupes de vertex d'un objet, toutes primitives glTF confondues) :
  > - **Les 14 objets tronc/cou réellement exportés** (7 noms de base × `.l`/`.r` — `Erector spinae`
  >   n'est jamais exporté, géométrie dégénérée déjà exclue avant cette correction) portent
  >   désormais un poids **exactement 100,000 % sur leur os correct et 0 % partout ailleurs**, sans
  >   aucune exception : `Rectus abdominis muscle.l`/`.r` → `spine` 100 % ; `External abdominal
  >   oblique muscle.l`/`.r` → `spine` 100 % ; **`Latissimus dorsi muscle.l`/`.r` → `spine` 100 %**
  >   (le défaut ciblé par les deux tentatives précédentes — dominante `L_upper_arm`/`R_upper_arm`
  >   puis `neck` — est cette fois résolu de façon exacte, pas seulement améliorée) ; `Ascending`/
  >   `Transverse`/`Descending part of trapezius muscle.l`/`.r` → `neck` 100 % ;
  >   `Sternocleidomastoid muscle.l`/`.r` → `neck` 100 %. Vérification faite objet par objet sur le
  >   binaire exporté, pas seulement sur le log Blender.
  > - **`WEIGHTS_0` valide mécaniquement** : sur les 106 couples (objet, primitive glTF) du fichier
  >   exporté, 0 sommet avec une somme de poids ≠ 1,0 (tolérance 1e-4) ; `JOINTS_0` référence
  >   exclusivement les 9 index de joint valides du skin. Nombre de triangles (356 060) et de
  >   maillages (54) exportés identiques à avant ce correctif — seule l'assignation des poids change,
  >   aucune géométrie n'est touchée.
  > - **Aucune régression sur les 40 muscles de membre** (toujours skinnés via Automatic Weights,
  >   inchangé) : échantillon vérifié incluant Deltoïde (3 parties), Biceps brachii (2 chefs),
  >   Triceps brachii (3 chefs), Brachioradialis, Quadriceps femoris (4 chefs), Biceps femoris
  >   (2 chefs) — `.l` et `.r` — tous restent dominants sur l'os de leur propre côté, aucune bascule
  >   de dominante observée par rapport aux mesures du correctif précédent.
  > - **`validate_muscle_rig.py` étendu** avec un nouvel invariant permanent : pour tout objet exporté
  >   dont le nom de base figure dans `rig_spec.TRUNK_NECK_MUSCLES`, l'ensemble des groupes de vertex à
  >   poids non nul doit être exactement `{os attendu}` (pas seulement "dominant" — aucun autre groupe
  >   à poids non nul toléré) et chaque sommet doit avoir un poids total de exactement 1,0. Passe sur
  >   le nouveau `.glb` (`OK: 9 os, 54 maillages skinnés, binding gauche/droite cohérent, poids rigide
  >   tronc/cou exact sur 8 nom(s) de base.`) — rend cette garantie vérifiée mécaniquement à chaque
  >   ré-export futur, pas seulement mesurée une fois au moment de ce correctif.
  >
  > **Déviation assumée, par souci d'honnêteté** : ce correctif étend l'usage du poids rigide
  > hand-assigné bien au-delà de son périmètre d'origine (filet de sécurité pour un échec ponctuel et
  > non déterministe du solveur, 1-3 objets sur 54 selon l'exécution) vers une catégorie entière de 14
  > objets, assignée de façon systématique et inconditionnelle, jamais soumise au solveur Automatic
  > Weights. C'est un écart réel par rapport à l'esprit initial de la spec ("gère les muscles
  > bi-articulaires mieux qu'un rattachement rigide au bone le plus proche" — voir Décisions de
  > cadrage ci-dessous), qui justifiait Automatic Weights de façon générale. Mais cet écart est
  > mieux justifié que les deux tentatives précédentes : les muscles tronc/cou ne sont PAS
  > bi-articulaires (contrairement à la justification citée, qui vise spécifiquement les muscles de
  > membre), donc l'argument en faveur de heat-diffusion ne s'applique tout simplement pas à eux — et
  > ce changement d'approche fait suite à la direction explicite de l'humain, après avoir vu deux
  > tentatives basées sur Automatic Weights échouer à produire une dominante correcte. **Bilan
  > honnête** : contrairement aux deux tentatives précédentes ("amélioration partielle"), celle-ci
  > atteint l'objectif produit complet — dominante exacte et déterministe sur l'os correct pour les 14
  > objets tronc/cou, garantie mécaniquement vérifiée par le validateur, sans régression mesurée sur
  > les 40 muscles de membre. Point ouvert : le Latissimus dorsi et les autres muscles tronc/cou se
  > déforment désormais de façon totalement rigide (pas de bulge/étirement naturel du muscle), une
  > simplification anatomique assumée en échange de l'attachement osseux correct — non vérifié
  > visuellement en contexte réel (pas d'accès GUI dans cette session), à confirmer lors d'une
  > relecture manuelle ultérieure de la posture avatar (`moi coupe.mp4`).

### Liste des muscles retenus

Mappés sur les 8 os existants (voir `docs/superpowers/specs/2026-09-16-3d-posture-skeleton-rig-design.md`) :

Noms vérifiés directement dans `Startup.blend` via `bpy.data.objects` pendant le brainstorming (suffixes `.l`/`.r` = gauche/droite, présents sur les objets réels) :

| Os | Muscles (nom d'objet Z-Anatomy, sans le suffixe `.l`/`.r`) |
|---|---|
| `spine` | Erector spinae, Rectus abdominis muscle, External abdominal oblique muscle, Latissimus dorsi muscle |
| `neck` | Trapezius muscle — **scindé en 3 objets** (« Ascending part of trapezius muscle », « Transverse part of trapezius muscle », « Descending part of trapezius muscle »), même structure que le deltoïde ; Sternocleidomastoid muscle |
| `L_upper_arm` / `R_upper_arm` | Deltoid muscle (3 parties : acromiale/claviculaire/scapulaire), Biceps brachii muscle, Triceps brachii muscle |
| `L_forearm` / `R_forearm` | Brachioradialis muscle, Flexor carpi ulnaris, Extensor carpi ulnaris, Extensor digitorum |
| `L_thigh` / `R_thigh` | Quadriceps femoris muscle, Biceps femoris muscle (ischio-jambiers) |

Point d'attention découvert pendant la vérification : certains objets ont des variantes `.el`/`.er`/`.ol`/`.or` en plus de `.l`/`.r` (ex. `Latissimus dorsi muscle.el`) — probablement des niveaux de détail ou des variantes géométriques alternatives. Le script d'export devra choisir explicitement les variantes `.l`/`.r` de base et ignorer les autres (à vérifier au cas par cas à l'implémentation, ne pas supposer que toutes les variantes existent pour chaque muscle).

## Approche

```
Étape 1 — Génération de l'armature (script Python, hors runtime)
─────────────────────────────────────────────────────────────────
tools/blender/export_muscle_rig.py (NOUVEAU, exécuté manuellement via
`blender --background --python`, pas embarqué dans l'app)
  ├─ Charge Startup.blend (téléchargé séparément, voir Décisions de cadrage)
  ├─ Construit une bpy.types.Armature avec la même hiérarchie que
  │  BONE_ORDER/BONE_SPECS/BONE_LENGTH de pose3dSkeleton.ts
  │  (axes Z-up Blender ; l'export glTF convertit automatiquement en Y-up)
  ├─ Sélectionne les objets mesh des muscles retenus (par nom de collection)
  ├─ Parente chaque muscle à l'armature avec Automatic Weights
  │  (bpy.ops.object.parent_set(type='ARMATURE_AUTO'))
  └─ Exporte armature + muscles en un seul fichier .glb
       (bpy.ops.export_scene.gltf, export des skins/joints inclus)
                    │
                    ▼
        web/public/muscle-rig.glb (NOUVEAU, committé au dépôt)

Étape 2 — Chargement runtime (Next.js, inchangé sur le fond depuis la Tranche 2)
──────────────────────────────────────────────────────────────────────────────
PostureAvatar3D.tsx (MODIFIÉ)
  ├─ useGLTF("/muscle-rig.glb")  [@react-three/drei, déjà une dépendance]
  ├─ Retrouve chaque bone du squelette importé par son nom (BoneKey)
  │  → Record<BoneKey, THREE.Bone>, même contrat que buildSkeleton()
  ├─ applyFrameToSkeleton(bones, frame.landmarks, cache)  [INCHANGÉ, Tranche 2]
  ├─ Applique la couleur de l'action_level courant à TOUS les matériaux
  │  des muscles importés (plusieurs dizaines, pas un seul comme en Tranche 2)
  └─ OrbitControls, fallback "aucune posture détectée" (inchangés)
```

## Structure du projet (ajouts sur l'existant)

```
TMS vision/
├── NOTICE.md                          # NOUVEAU — attribution CC BY-SA (BodyParts3D/Z-Anatomy)
├── tools/
│   └── blender/
│       ├── export_muscle_rig.py       # NOUVEAU — script d'export, exécuté manuellement
│       └── README.md                  # NOUVEAU — instructions (téléchargement Z-Anatomy, commande d'exécution)
└── web/
    ├── public/
    │   └── muscle-rig.glb             # NOUVEAU — asset généré par le script, committé
    └── app/
        └── PostureAvatar3D.tsx        # MODIFIÉ — charge muscle-rig.glb au lieu du maillage de test
                                         #   (testSkinnedGeometry.ts n'est plus utilisé par ce composant ;
                                         #   à supprimer ou conserver comme test isolé, cf. Hors périmètre)
```

## Détail — `tools/blender/export_muscle_rig.py`

- Table `BONE_HIERARCHY` répliquant `BONE_ORDER`/`BONE_SPECS`/`BONE_LENGTH` de `pose3dSkeleton.ts` (dupliquée intentionnellement en Python, pas de partage de source entre TypeScript et Blender — un commentaire dans chaque fichier renvoie vers l'autre, à tenir synchronisé manuellement si le squelette change).
- Construction de l'armature : un `bpy.types.Bone` par entrée de `BONE_HIERARCHY`, position locale relative au parent = longueur du parent le long de l'axe Z de Blender (équivalent de l'axe Y de Three.js après conversion glTF), exactement comme `buildSkeleton()` le fait pour l'axe Y en Three.js.
- Sélection des muscles : recherche par nom d'**objet** (`bpy.data.objects`), pas seulement par nom de collection — certains muscles (ex. Latissimus dorsi, Brachioradialis) existent comme objets nommés sans collection dédiée du même nom, découvert en inspectant le fichier réel pendant le brainstorming. Filtrer sur les suffixes `.l`/`.r` exacts (pas `.el`/`.er`/`.ol`/`.or`, des variantes non désirées repérées sur certains muscles). Erreur explicite si un objet attendu est introuvable (ne pas continuer silencieusement avec un sous-ensemble incomplet).
- Rattachement : `bpy.ops.object.parent_set(type='ARMATURE_AUTO')` par muscle (ou par lot), en s'assurant que l'armature est bien l'objet actif au moment de l'appel (contrainte de l'API Blender).
- Export : `bpy.ops.export_scene.gltf(filepath=..., export_format='GLB', export_skins=True, ...)`. Vérifier après export que le `.glb` produit contient bien un unique squelette partagé par tous les muscles (pas un squelette dupliqué par objet — comportement par défaut à confirmer contre la version de Blender installée).

## Détail — `PostureAvatar3D.tsx`

- `useGLTF("/muscle-rig.glb")` charge la scène ; on en extrait la liste des `THREE.SkinnedMesh` (potentiellement ~30, un par muscle/partie) et leur `THREE.Skeleton` partagé.
- Construction de `Record<BoneKey, THREE.Bone>` : pour chaque valeur de `BoneKey`, chercher dans `skeleton.bones` l'entrée dont `.name` correspond — erreur explicite si un nom attendu est absent (signe que l'armature exportée ne correspond plus à `pose3dSkeleton.ts`, ne pas continuer avec un mapping partiel silencieux).
- `applyFrameToSkeleton` appelé exactement comme en Tranche 2, sans modification.
- Couleur : itérer sur tous les `SkinnedMesh` trouvés et appliquer la couleur de l'`action_level` courant à leur matériau (cloner un matériau partagé plutôt que muter le matériau original importé du glTF, pour ne pas modifier l'asset source en mémoire de façon inattendue si le composant est démonté/remonté).
- Fallback "aucune posture détectée", `OrbitControls`, logique vidéo : inchangés.

## Tests

- **Validation de l'export** (script séparé ou étape manuelle, pas un test Vitest classique vu qu'il dépend d'un fichier binaire externe non commité) : charger le `.glb` généré et vérifier que les 9 noms de `BoneKey` sont bien présents dans son squelette, qu'au moins un `SkinnedMesh` existe par muscle attendu.
- **Vérification manuelle obligatoire** (comme les tranches précédentes) : rejouer `moi coupe.mp4`, comparer visuellement les muscles importés à la posture de la vidéo et au squelette de test de la Tranche 2 (proportions, absence de déformation aberrante aux articulations), vérifier que les correctifs de la Tranche 2 (masquage des os jamais détectés, absence de mannequin fantôme à t=0) fonctionnent toujours avec les vrais maillages.
- Les tests unitaires existants (`pose3dSkeleton.test.ts`, 11 tests) ne sont pas affectés : ce module n'est pas modifié par cette tranche.

## Hors périmètre (cette tranche)

- Musculature complète (~600 muscles) — extension future, après validation de ce sous-ensemble réduit.
- Coloration/activation par muscle individuel selon les sous-scores RULA — Tranche 4 future.
- Correction du roll/torsion des os (limite connue depuis la Tranche 2, non résolue ici).
- Correction du risque de cascade d'échelle sur hanche jamais détectée (limite connue depuis la Tranche 2, non résolue ici).
- `testSkinnedGeometry.ts` : conservé tel quel dans le dépôt (couvert par ses propres tests) mais plus utilisé par `PostureAvatar3D.tsx` une fois cette tranche livrée — décision de suppression ou de conservation comme filet de sécurité à prendre à l'implémentation, pas ici.
