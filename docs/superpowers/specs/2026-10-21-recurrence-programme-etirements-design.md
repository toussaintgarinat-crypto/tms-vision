# Récurrence, projection journalière et programme d'étirements

**Date** : 2026-10-21
**Statut** : Design à valider, implémentation à planifier

## Contexte

La vidéo analysée dure 30 s à 3 min. Elle n'a pas vocation à mesurer une posture isolée : elle est
un **échantillon représentatif du cycle de travail**, que le salarié répète pendant toute sa
journée (typiquement 9 h). Le rapport actuel ne le reflète pas :

- `export.py.summary()` restitue un score max, un temps par niveau d'action et une zone dégradée,
  tous exprimés **sur la durée de la vidéo**, jamais sur la journée.
- `rula/scoring.py.detect_muscle_use()` détecte déjà statisme (> 60 s) et répétition
  (>= 4 cycles/min), mais en **un booléen unique** sur un seul angle de charge posturale, utilisé
  seulement comme bonus du score RULA. Aucun nombre de cycles, aucune fréquence, aucune zone
  n'est restituée.
- `capsules.py` recommande **une seule** capsule (zone la plus dégradée en temps cumulé élevé).
- `load_kg` est un `float` unique, obligatoire (`Form(..., ge=0)`), stocké `NOT NULL`. Il ne
  permet ni de dire « charge inconnue », ni d'exprimer une fourchette.
- Les capsules sont des URL placeholder (`example.com`). Aucun mécanisme ne produit de vidéo.

Cette spec couvre trois parties livrables en tranches successives, plus une quatrième **réservée**
(correction du geste) dont le développement est explicitement différé.

## Décisions de cadrage

- **La vidéo est un échantillon, la journée est la cible.** Les indicateurs de récurrence sont
  calculés sur chaque vidéo puis **projetés** sur la durée de l'activité qu'elle représente dans une
  journée paramétrable (défaut 9 h).
- **Un poste = plusieurs vidéos, regroupées dans un « bilan de poste ».** Chaque vidéo garde son
  analyse détaillée et porte la **durée passée sur son activité dans la journée** (par exemple
  5 h de manutention, 3 h de saisie). Le rapport global (récurrence, projection, programme
  d'étirements) porte sur le bilan. La part de journée non couverte par les vidéos est affichée
  (« 1 h non documentée »).
- **Représentativité confirmée vidéo par vidéo.** À l'ajout, l'opérateur coche « Cette séquence est
  représentative de cette activité ». Une vidéo non confirmée apparaît dans le rapport avec ses
  chiffres bruts mais est exclue de la projection.
- **Seuils de cycles non fixés à ce stade.** Les valeurs seront calibrées plus tard avec
  l'ostéopathe ; en attendant, le système n'en invente aucune (voir Partie A).
- **La projection est toujours présentée comme une estimation** (« basée sur un échantillon de
  X min »). Elle suppose que l'échantillon est représentatif ; c'est à l'opérateur de le garantir
  en filmant un cycle typique.
- **Récurrence par zone** (`neck`, `trunk`, `upper_arm`, `lower_arm`), pas un indicateur global :
  elle doit pouvoir orienter le choix des étirements.
- **Programme de 2 à 3 capsules** classées par charge journalière de chaque zone, en
  remplacement de la capsule unique.
- **Le poids est une saisie de l'opérateur**, pas une mesure : la vidéo ne peut pas le deviner. Il
  est facultatif, et peut être **précis ou en fourchette**.
- **Cas défavorable pour les recommandations** quand le poids est une fourchette.
- **Génération vidéo autonome et déterministe** à partir de l'avatar 3D existant ; l'IA n'est
  qu'un fournisseur optionnel et interchangeable, jamais câblée en dur.
- **Correction du geste** : prévue dans le modèle de données et la structure du rapport, mais pas
  implémentée dans ce périmètre.

## Partie A : moteur de récurrence et projection journalière

### Bilan de poste

Un **bilan de poste** regroupe plusieurs analyses existantes. Pour chaque analyse rattachée :

| Champ | Rôle |
|---|---|
| `activity_hours` | Durée passée sur cette activité dans la journée (> 0) |
| `representative` | Booléen : l'opérateur confirme que la séquence est représentative |

Le bilan porte `workday_hours` (défaut 9.0, > 0, plafonné à 24). La somme des `activity_hours`
des analyses ne doit pas dépasser `workday_hours` ; la différence est restituée comme part non
documentée. Un nouveau modèle (tables `postes_bilans` et `bilan_analyses`) évite de modifier les
analyses existantes, qui restent utilisables seules.

### Indicateurs par zone

Pour chacune des 4 zones, à partir de l'historique temporel des angles (déjà disponible frame par
frame) :

| Indicateur | Définition |
|---|---|
| `cycles` | Nombre de cycles de mouvement détectés (2 changements de direction d'amplitude >= `REPETITION_MIN_PROMINENCE_DEG`) |
| `cycles_per_minute` | `cycles` / durée de la vidéo en minutes |
| `mean_cycle_seconds` | Durée moyenne d'un cycle (`None` si aucun cycle) |
| `longest_static_seconds` | Plus longue plage contiguë sous `STATIC_VARIATION_THRESHOLD_DEG` |
| `elevated_seconds` | Temps cumulé en niveau d'action élevé pour la zone (même algorithme de durée que `capsules.compute_worst_zone`) |

Les fonctions `_count_direction_changes` et `_longest_static_span_seconds` existent déjà et sont
réutilisées ; elles sont aujourd'hui privées et n'opèrent que sur un angle de charge posturale
global. Il faut les promouvoir en API interne et les appliquer à l'angle de chaque zone.

### Projection journalière

Calcul par zone et par analyse **confirmée représentative**, puis somme sur le bilan :

```
projected_cycles          = sum_i( cycles_per_minute_i * 60 * activity_hours_i )
projected_elevated_hours  = sum_i( elevated_seconds_i / video_duration_seconds_i * activity_hours_i )
```

La projection d'un temps cumulé suppose que la proportion mesurée sur chaque vidéo vaut pour toute
l'activité qu'elle représente. Si une vidéo dure moins de 30 s, l'échantillon est jugé trop court :
les valeurs sont calculées mais le rapport affiche un avertissement explicite. Les analyses non
confirmées sont listées avec leurs chiffres bruts et exclues des sommes.

### Seuils de cycles : non calibrés

Les seuils de détection d'un cycle (amplitude minimale, fréquence jugée répétitive) seront
calibrés plus tard avec l'ostéopathe, **par zone**. Ils sont lus depuis un fichier de configuration
dont les valeurs sont vides au départ. Tant qu'ils sont vides :

- le rapport affiche les chiffres bruts (cycles, cycles par minute, durée moyenne, plage
  statique) et la projection, avec la mention « seuils non calibrés » ;
- aucune zone n'est classée « répétitive » ou « acceptable » ;
- la détection de répétition existante dans `detect_muscle_use` (seuils du PoC) reste inchangée
  pour le score RULA et n'est pas réutilisée pour cette interprétation.

### Restitution

- Nouveau bloc `recurrence` dans le résumé (`summary()`) : indicateurs par zone, plus
  `workday_hours`, `sample_seconds`, `projection_warning` (`None` ou texte).
- Page de résultat et page de détail d'historique : section « Récurrence et charge journalière »
  (tableau par zone, mention « estimation basée sur un échantillon de X min »). Une courbe
  temporelle de l'angle avec cycles repérés est un bonus, hors minimum livrable.
- Persistance : les indicateurs sont recalculables depuis `analysis_frames` ; **pas de nouvelle
  table**, seulement `workday_hours` stocké avec l'analyse.

## Partie B : saisie du poids et programme d'étirements

### Poids : précis ou fourchette

Remplacer le `load_kg` unique par une structure :

```
load: { kind: "none" | "exact" | "range", kg: float | None, kg_min: float | None, kg_max: float | None }
```

- `none` : aucune charge saisie (équivaut à 0 kg pour le calcul). Remplace l'obligation actuelle.
- `exact` : un poids précis.
- `range` : `kg_min <= kg_max`, tous deux >= 0.

**Effet sur le score.** `force_load_score` n'a que trois paliers (< 2 kg → 0, 2 à 10 kg → 1 ou 2,
> 10 kg → 3). Pour une fourchette, le score RULA est calculé **aux deux bornes** :

- si les deux bornes tombent dans le même palier, le score est unique (la fourchette est sans
  effet) ;
- sinon le rapport affiche un intervalle de score (« 5 à 6 selon la charge réelle »).

**Recalcul après coup.** Le poids est saisi par l'opérateur *après* l'analyse vidéo. Le
recalcul ne doit donc **pas relancer la pose estimation** : les angles par frame sont déjà
persistés dans `analysis_frames`, et seul le sous-score de force doit être recalculé. Un
endpoint de mise à jour du poids (`PATCH /analyses/{id}/load`) recalcule scores et
recommandations à partir des angles stockés.

**Compatibilité.** Les analyses existantes ont un `load_kg` : elles sont migrées en `exact`. La
colonne `load_kg` est conservée (lecture) et complétée par `load_kg_min`, `load_kg_max`,
`load_kind`.

### Programme de 2 à 3 capsules

Remplace `recommend_capsule` / `compute_worst_zone` par une fonction de classement :

1. Calculer pour chaque zone une **charge journalière** : `projected_elevated_hours`, avec en cas
   de fourchette de poids la borne haute (cas défavorable).
2. Écarter les zones sans temps élevé.
3. Classer par charge décroissante ; égalité → ordre fixe `trunk > neck > upper_arm > lower_arm`
   (inchangé).
4. Retourner les **3 premières zones au plus**, au **minimum 2 capsules** si au moins 2 zones sont
   chargées ; 1 seule si une seule zone l'est ; aucune si aucune ne l'est (réponse explicite
   « aucune recommandation », comme aujourd'hui).
5. Pour chaque capsule : zone, rang, motif (« tronc : environ 4,2 h en posture à risque sur 9 h
   estimées »), indication « calculé sur le cas défavorable » si le poids est une fourchette
   à cheval sur un seuil.

Limite connue conservée : `lower_arm` ne peut atteindre les niveaux élevés (plafond du sous-score
brut à 3, voir `capsules.py`). Elle ne sera donc jamais classée tant que les seuils par segment ne
sont pas redéfinis ; hors périmètre ici.

Optionnel, non livré dans la première tranche : fréquence de micro-pause suggérée (par exemple
toutes les 90 min pour la zone la plus chargée).

## Partie C : génération autonome des modules d'étirement

Objectif : produire la vidéo d'un module d'étirement **de bout en bout, sans dépendre d'une
IA**, avec des briques IA optionnelles et interchangeables.

### Définition d'un exercice en données

Fichier déclaratif par exercice (YAML ou JSON, versionné dans le dépôt) :

```yaml
id: neck-lateral-stretch
zone: neck
title: Étirement latéral du cou
duration_seconds: 45
instructions: ["Incline la tête vers l'épaule droite…", "…"]   # rédigé par l'ostéopathe
keyframes:
  - { t: 0,  pose: neutral }
  - { t: 10, pose: neck_tilt_right }
  - { t: 25, pose: neutral }
  - { t: 35, pose: neck_tilt_left }
target_segments: [neck]       # segments musculaires mis en évidence
```

Le catalogue reste statique et curé (même décision que la spec de recommandation) ; il est étendu
pour référencer ces définitions plutôt qu'une URL.

### Rendu déterministe

- Les poses clés sont des positions d'os du squelette articulé existant (`pose3dSkeleton.ts`),
  interpolées par le rig déjà chargé (`muscle-rig.glb`).
- Le rendu produit une vidéo (cadrage fixe, muscles ciblés colorés via `muscleSegments.ts`,
  consignes et minuteur en surimpression).
- Aucune étape de ce chemin n'appelle une IA ; deux rendus du même fichier donnent la même
  vidéo.
- Choix technique du rendu (navigateur sans interface via Playwright avec capture frame par frame
  puis assemblage ffmpeg, ou rendu côté Blender) : à trancher lors de la planification.

### Fournisseurs optionnels

Interfaces minces, une par besoin, avec un fournisseur par défaut qui ne fait rien :

| Interface | Rôle | Fournisseur par défaut |
|---|---|---|
| `NarrationProvider` | Voix de synthèse des consignes | Aucune voix (texte seul) |
| `InstructionProvider` | Rédaction ou reformulation des consignes | Texte écrit à la main |
| `ExerciseProvider` | Proposition d'un exercice nouveau | Aucun (catalogue seul) |

Un fournisseur est choisi par configuration (variable d'environnement), jamais importé en dur
dans le pipeline. Aucun appel réseau sortant sans qu'un fournisseur distant ait été explicitement
configuré (cohérence RGPD et on-premise). Tout exercice proposé par un `ExerciseProvider` doit
être **validé par l'ostéopathe** avant d'entrer au catalogue : une IA générative peut produire un
geste anatomiquement faux, inacceptable pour de la santé.

La génération directe de vidéo par un modèle d'IA (texte vers vidéo) n'est pas dans ce périmètre ;
elle pourrait y être branchée plus tard comme un fournisseur supplémentaire.

## Partie D : correction du geste (réservée, non implémentée)

Une correction du geste au poste (réglage de hauteur, pivot des pieds plutôt que du tronc, etc.)
fera partie du produit mais n'est pas développée maintenant. Pour qu'elle s'ajoute sans refonte :

- le rapport expose une section **« Correction du geste »**, vide aujourd'hui ;
- le résultat d'analyse porte une liste `gesture_corrections` (vide), de même forme que les
  capsules : zone, motif chiffré issu de la Partie A, texte de consigne, média optionnel ;
- le catalogue est structuré avec un type d'entrée (`stretch` aujourd'hui, `gesture` demain) ;
- le moteur de sélection de la Partie B reste découplé du type d'entrée.

## Tranches proposées

1. **Tranche 1 : Bilan de poste et récurrence** (Partie A) : bilan regroupant plusieurs analyses,
   indicateurs par zone, projection pondérée, affichage des chiffres bruts (seuils non calibrés).
2. **Tranche 2 : Poids et programme** (Partie B) : saisie précise ou fourchette, recalcul sans
   relancer la pose, programme de 2 à 3 capsules, structure réservée de la Partie D.
3. **Tranche 3 : Génération des modules** (Partie C) : définitions d'exercices, rendu déterministe,
   interfaces de fournisseurs.

Chaque tranche aura son plan d'implémentation dans `docs/superpowers/plans/`.

## Questions ouvertes

- Calibration des seuils de cycles par zone : aucun matériel disponible pour l'instant, à planifier
  avec l'ostéopathe (vidéos d'essai de gestes connus ou valeurs de référence de sa pratique).
- Rendu des vidéos : côté navigateur ou côté Blender (à trancher à la Tranche 3).
- Le catalogue final de 30 à 45 exercices reste à définir par l'ostéopathe.
