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
- `zone` : `neck`, `trunk`, `upper_arm` ou `lower_arm`. `target_segments` : les segments mis en
  évidence en bleu dans la vidéo.
- `view` : `front`, `side` ou `three_quarter` (cadrage de la caméra).
- `poses` : chaque pose donne, par os, des angles en degrés à partir de la posture neutre. Un os absent
  d'une pose reste à sa direction neutre. Os disponibles : `spine`, `neck`, `L_upper_arm`,
  `L_forearm`, `R_upper_arm`, `R_forearm`, `L_thigh`, `R_thigh`. Angles : `flexion` et `lateral`,
  entre -180 et 180.
- `keyframes` : suite de poses à des instants `t` (secondes) strictement croissants, le premier à 0 ;
  le mouvement est interpolé de façon adoucie entre deux poses clés. Deux poses clés identiques
  d'affilée = une position tenue.
- `instructions` : consignes datées, affichées (et dites si une voix est configurée) à l'instant `t`.
- `duration_seconds` : entre 10 et 180.

## Limites du squelette

L'avatar a **9 os** : tronc, cou, deux bras, deux avant-bras, deux cuisses. Il n'a ni poignet, ni
main, ni rotation de la tête, ni omoplate. Le cou n'a qu'une direction (pas de rotation sur lui-même).
Un exercice ne peut montrer que ce que ces os savent faire.

## Cycle de vie d'un exercice

1. **Brouillon** (`"status": "draft"`, `"source": "human"`) : rédigé mais pas relu. Il apparaît dans
   l'application avec un badge « Brouillon ».
2. **Validé** (`"status": "validated"`) : l'ostéopathe a relu la vidéo et les consignes. Renseigner
   `validated_by` (son nom) et `validated_on` (date `AAAA-MM-JJ`), sans quoi le fichier est refusé.
3. **Proposition d'une IA** : un exercice proposé par un fournisseur d'IA est écrit dans
   `exercises/drafts/` avec `"source": "ai"`. **Il n'entre jamais dans le catalogue.** Pour l'adopter,
   un humain le relit, le corrige, le déplace dans `exercises/`, passe `source` à `"human"`, puis le
   valide comme ci-dessus.

Les quatre exercices livrés sont des brouillons rédigés sans expertise d'ostéopathe : ils ne
doivent pas être présentés à un salarié comme validés.

## Générer les vidéos

Voir la section « Générer les modules d'étirement » du `README.md` à la racine.
