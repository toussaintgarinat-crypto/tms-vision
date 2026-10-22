# Exercices d'étirement

Chaque fichier `exercises/<id>.json` définit un exercice. Il alimente le catalogue de capsules de
l'application et sert à **générer la vidéo** (avatar 3D animé), sans IA.

Les règles de validation sont dans `src/tms_vision/exercises.py` : un fichier invalide fait
échouer le chargement en nommant le fichier et le champ fautif.

## Format

```json
{
  "id": "neck-lateral-stretch",
  "zone": "neck",
  "title": "Étirements cervicaux",
  "description": "…",
  "status": "draft",
  "source": "human",
  "validated_by": null,
  "validated_on": null,
  "view": "front",
  "target_segments": ["neck"],
  "poses": { "neutral": {}, "tilt_right": { "neck": { "lateral": 35 } } },
  "keyframes": [ { "t": 0, "pose": "neutral" }, { "t": 5, "pose": "tilt_right" } ],
  "instructions": [ { "t": 0, "text": "…" } ],
  "duration_seconds": 45
}
```

- `id` : minuscules, chiffres et tirets ; égal au nom du fichier.
- `zone` : la région principale de l'exercice. `target_segments` : les régions mises en évidence en
  bleu dans la vidéo. Régions : `neck`, `trunk`, `upper_arm`, `lower_arm` (les quatre zones RULA
  mesurées), puis `head`, `shoulder` (ceinture scapulaire, pectoraux, rotateurs), `hand` (main et
  doigts), `hip` (bassin, fessiers, psoas), `thigh`, `lower_leg` (mollet, jambe) et `foot`. Les
  régions hors RULA n'ont pas de mesure : leurs exercices existent et se génèrent, mais aucun score
  ne les recommande encore.
- `view` : `front`, `side` ou `three_quarter` (cadrage de la caméra). Le zoom est automatique : tête
  et cou, mains et avant-bras, pied seul sont cadrés de près ; tout le reste, corps entier.
- `poses` : chaque pose donne, par os, jusqu'à trois angles en degrés **relatifs à l'os parent**. Un
  os absent d'une pose, ou sans angle, reste aligné sur son parent : la tête suit le cou, la main
  suit l'avant-bras, le pied suit la jambe.
- `keyframes` : suite de poses à des instants `t` (secondes) strictement croissants, le premier à 0 ;
  le mouvement est interpolé de façon adoucie entre deux poses clés. Deux poses clés identiques
  d'affilée = une position tenue.
- `instructions` : consignes datées, affichées (et dites si une voix est configurée) à l'instant `t`.
- `duration_seconds` : entre 10 et 180.

## Le squelette : 24 os

Un os par segment, parent avant enfant (`root` est le bassin, sans angle) :

```
root
├─ spine ─ neck ─ head
│  ├─ L_clavicle ─ L_upper_arm ─ L_forearm ─ L_hand ─┬─ L_fingers
│  │                                                  └─ L_thumb
│  └─ R_clavicle ─ R_upper_arm ─ R_forearm ─ R_hand ─┬─ R_fingers
│                                                     └─ R_thumb
├─ L_thigh ─ L_shin ─ L_foot ─ L_toes
└─ R_thigh ─ R_shin ─ R_foot ─ R_toes
```

`fingers` regroupe les quatre doigts longs, `toes` les orteils. `spine` est un seul os pour tout le
tronc. Les angles peuvent être donnés pour tous les os sauf `root`.

## Sens des angles

Mesuré sur le modèle `web/public/muscle-rig.glb` et verrouillé par `web/app/exercisePose.test.ts` :
le côté **gauche** du modèle est +x et son **avant** est +z (face à la caméra de l'avatar). Les angles
sont en degrés, entre -180 et 180, et **relatifs au parent** : `R_forearm: { flexion: 90 }` plie le coude
de 90° quel que soit l'angle du bras, et `R_upper_arm: { flexion: 90 }` seul lève le bras avec
l'avant-bras, la main et les doigts qui le prolongent.

Trois angles : `flexion`, `lateral`, `twist`. Selon la direction de repos de l'os :

| Os | `flexion` > 0 | `lateral` > 0 | `twist` > 0 |
|---|---|---|---|
| `spine`, `neck`, `head` (vers le haut) | vers l'avant | inclinaison vers la **droite** du sujet | rotation vers la **droite** du sujet |
| bras, avant-bras, main, doigts, pouce, cuisse, jambe (qui pendent) | vers l'avant | écartement du corps (miroir à gauche et à droite) | rotation externe : le devant de l'os tourne vers l'extérieur |
| `*_clavicle` (horizontale) | roulis (peu utile) | élévation de l'épaule | projection de l'épaule vers l'avant |
| `*_foot`, `*_toes` (vers l'avant) | flexion dorsale : le bout monte | inversion (roulis du pied) | pointe vers l'extérieur |

- `flexion: 90` sur un bras = bras à l'horizontale devant soi. Sur une cuisse : cuisse horizontale
  devant soi. Un genou plié, c'est `R_shin: { flexion: -90 }` (la jambe revient vers l'arrière de la
  cuisse). `R_forearm: { flexion: 90 }` sur un bras à l'horizontale lève l'avant-bras.
- Composition : d'abord `twist`, puis `lateral`, puis `flexion`. Un bras avec `flexion: 90` est à
  l'horizontale devant soi, et `lateral` l'en écarte dans le plan horizontal :
  `{ "flexion": 90, "lateral": -45 }` sur le bras droit le ramène de 45° vers le milieu du corps.
- Le repos du modèle a les bras très légèrement écartés du corps (environ 10 à 15°) : `flexion: 90`
  sur un bras le met donc à l'horizontale à une dizaine de degrés près.
- Le sens de `twist` sur la main et l'avant-bras (pronation ou supination) dépend de l'orientation de
  la paume dans le modèle au repos : le vérifier à l'œil avant de s'en servir.

## Limites du squelette

Le tronc est un seul os : pas de distinction lombaire, dorsal. Les quatre doigts longs bougent
ensemble, comme les orteils ; il n'y a pas d'articulation de la mâchoire, d'omoplate séparée de la
clavicule ni de rotation fine de l'avant-bras (pronation, supination) autre que `twist`. Un exercice
ne peut montrer que ce que ces os savent faire. Les muscles sont simplifiés (1 500 sommets au plus
chacun) et leur déformation aux articulations est approximative : relire les images de chaque
exercice (`web/scripts/snapshot-exercise.mjs`) avant de le diffuser.

## Cycle de vie d'un exercice

1. **Brouillon** (`"status": "draft"`, `"source": "human"`) : rédigé mais pas relu. Il apparaît dans
   l'application avec un badge « Brouillon ».
2. **Validé** (`"status": "validated"`) : l'ostéopathe a relu la vidéo et les consignes. Renseigner
   `validated_by` (son nom) et `validated_on` (date `AAAA-MM-JJ`), sans quoi le fichier est refusé.
3. **Proposition d'une IA** : un exercice proposé par un fournisseur d'IA est écrit dans
   `exercises/drafts/` avec `"source": "ai"`. **Il n'entre jamais dans le catalogue.** Pour l'adopter,
   un humain le relit, le corrige, le déplace dans `exercises/`, passe `source` à `"human"`, puis le
   valide comme ci-dessus.

Les quarante-cinq exercices livrés (au moins un par région du corps) sont des brouillons rédigés
sans expertise d'ostéopathe : ils ne doivent pas être présentés à un salarié ou à un patient comme
validés. Ceux ajoutés pour la bibliothèque du praticien (voir `library/body_map.json`) ne changent pas
le programme d'étirements des salariés : l'exercice recommandé pour chaque zone mesurée est fixé par
`PROGRAM_CAPSULE_BY_ZONE` dans `src/tms_vision/capsules.py`.

## Générer les vidéos

Voir la section « Générer les modules d'étirement » du `README.md` à la racine.
