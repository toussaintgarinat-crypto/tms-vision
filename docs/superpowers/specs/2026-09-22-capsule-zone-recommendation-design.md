# Recommandation de capsules d'étirement par zone

**Date** : 2026-09-22
**Statut** : Approuvé (design), implémentation à planifier

## Contexte

Le README (§6, "La Brique Micro-Pauses & Capsules Vidéo") décrit une médiathèque de capsules
vidéo d'étirement, catégorisées par zone anatomique, déclenchée automatiquement une fois une
analyse RULA terminée : « le système associe les scores d'angles critiques aux capsules
d'étirement correspondantes ». Cette brique n'a jamais été construite — aucune vidéo, aucun
catalogue, aucune logique de sélection n'existe dans le code à ce jour.

Le sprint précédent (stockage des analyses en DuckDB,
`docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md`) a livré exactement la
donnée dont cette brique a besoin : la table `analysis_frames` porte, pour chaque frame, un
`{neck,trunk,upper_arm,lower_arm}_segment_action_level` déjà calculé (niveau d'action RULA par
segment anatomique, hérité de la Tranche 4 de l'avatar 3D). Ce sprint construit la première
version de la recommandation — **sélection automatique post-analyse**, pas de mode temps réel —
en s'appuyant sur cette donnée déjà persistée.

**Recherche faite avant ce document** :

- Seuls 4 segments sont réellement mesurés par le pipeline : `neck`, `trunk`, `upper_arm`,
  `lower_arm` (`action_level()` appliqué aux sous-scores RULA correspondants, voir
  `pipeline.py`/`scoring.py`). `wrist` et `legs` existent comme sous-scores RULA mais n'ont pas de
  `segment_action_level` : `legs` est une constante jamais mesurée (`LEGS_SCORE`, limite connue du
  PoC), et `wrist` n'a pas d'équivalent musculaire dans le rig 3D. Les 5 zones anatomiques citées
  au README (Rachis cervical, Lombaires, Épaules, Poignets/Mains, Hanches) ne correspondent donc
  pas 1:1 aux données réellement disponibles.
- `ResultsExporter.summary()` (`export.py`) calcule déjà un `time_by_action_level` **global**
  (cumul de durée par niveau d'action, toutes zones confondues) selon un algorithme précis :
  durée d'une frame détectée = écart jusqu'au timestamp de la frame suivante (ou 1.0s si frame
  détectée unique). Ce sprint réutilise le même principe de calcul de durée, mais **par zone**
  plutôt qu'au global.
- Aucun catalogue de contenu (vidéos, admin UI, CMS) n'existe dans le projet — la seule mention
  est la vision produit du README, jamais implémentée.

## Décisions de cadrage

- **4 zones, alignées sur ce qui est réellement mesuré** : `neck`, `trunk`, `upper_arm`,
  `lower_arm`. Pas de zone "poignets/mains" ni "hanches" dans ce premier jet — les inclure
  obligerait à prévoir des zones qui ne pourraient jamais être recommandées, puisque `wrist` et
  `legs` ne sont jamais dérivés d'une vraie mesure vidéo.
- **Catalogue de capsules avec du contenu placeholder**, pas de vraies vidéos. Aucune vidéo
  d'étirement n'existe aujourd'hui ; ce sprint construit la structure de données et la logique de
  recommandation, alimentées par quelques entrées factices mais réalistes par zone. Le remplissage
  réel par l'ostéopathe est hors périmètre.
- **Catalogue statique en Python**, pas de table DuckDB. C'est du contenu curé par un humain, pas
  une donnée générée par analyse ; sans admin UI (hors périmètre), il ne sera de toute façon
  modifié que par édition directe de code. Une table DuckDB ajouterait de la logique CRUD pour un
  bénéfice nul à ce stade.
- **Zone la plus dégradée = temps cumulé passé dans les niveaux élevés**
  (`investigation_et_changement_bientot` + `changement_immediat`), pas le pire niveau atteint sur
  une seule frame. Reflète une exposition soutenue plutôt qu'un pic isolé qui pourrait être du
  bruit de détection MediaPipe sur une frame. `investigation_recommandee` ne compte pas comme
  "dégradé" — c'est une simple vigilance, pas un niveau justifiant une action corrective.
- **Égalité stricte entre zones** → ordre de priorité fixe : `trunk > neck > upper_arm >
  lower_arm` (les lombaires sont généralement le risque TMS le plus sérieux en ergonomie).
- **Aucune zone dégradée** (toutes à zéro temps cumulé en niveau élevé) → pas de recommandation
  forcée. La réponse indique explicitement l'absence de recommandation plutôt que de suggérer une
  zone arbitrairement.
- **Une seule capsule recommandée**, pas une liste. La première capsule du catalogue pour la zone
  identifiée. Le plus simple pour ce premier jet ; rien n'empêche d'en montrer plusieurs dans un
  sprint futur.
- **Exposé à la fois en API et dans l'interface existante** (pas seulement l'API). Un nouvel
  endpoint, plus un petit bloc dans la page de résultat déjà affichée après une analyse
  (`web/app/page.tsx`). Reste du post-analyse (pas de notification, pas de temps réel) — cohérent
  avec le cadrage. Contrairement à l'UI d'historique (sprint précédent), explicitement reportée,
  ceci s'ajoute à un écran qui existe déjà.

## Architecture

**Nouveau module `src/tms_vision/capsules.py`** — porte le catalogue statique et la logique de
recommandation, sans aucune dépendance à DuckDB (fonctions pures, testables sans base) :

- `Capsule` (dataclass) : `zone: str`, `title: str`, `description: str`, `video_url: str`.
- `CAPSULES: list[Capsule]` — catalogue en dur, au moins une entrée par zone mesurée (`neck`,
  `trunk`, `upper_arm`, `lower_arm`), contenu factice réaliste (style des exemples du README).
- `compute_worst_zone(frames: list[dict]) -> str | None` — reçoit une liste de lignes de frame
  (chacune avec `frame_index`, `timestamp_seconds`, et les 4 clés
  `{neck,trunk,upper_arm,lower_arm}_segment_action_level`), calcule le temps cumulé par zone dans
  les niveaux élevés, retourne la zone gagnante ou `None`.
- `recommend_capsule(zone: str | None) -> Capsule | None` — première capsule du catalogue pour
  cette zone ; `None` si `zone` est `None` ou si aucune capsule n'existe pour cette zone.

**`storage.py`** gagne une seule nouvelle fonction de lecture, dans le même style que les
fonctions existantes (connexion par appel, `None` si `analysis_id` inconnu) :

- `get_frame_segments(analysis_id: str) -> list[dict] | None` — lit `analysis_frames`
  (`frame_index`, `timestamp_seconds`, les 4 colonnes segment), ordonnée par `frame_index`. Aucune
  logique de zone n'y vit — `storage.py` reste une couche de persistance pure, la logique de
  recommandation reste entièrement dans `capsules.py`.

**`api.py`** gagne `GET /analyses/{analysis_id}/recommendation` : appelle
`storage.get_frame_segments(analysis_id)` (404 si `None`, même pattern que les autres routes
`/analyses/{id}/...`), passe le résultat à `capsules.compute_worst_zone` puis
`capsules.recommend_capsule`, répond :

```json
{
  "zone": "trunk" | "neck" | "upper_arm" | "lower_arm" | null,
  "capsule": {"zone": "...", "title": "...", "description": "...", "video_url": "..."} | null
}
```

## Calcul de la zone dégradée

Même principe de durée que `ResultsExporter.summary()` (`export.py`), appliqué par zone plutôt
qu'au global :

1. Les lignes de frame sont déjà triées par `frame_index` (garanti par `storage.get_frame_segments`).
2. Pour chaque frame, sa durée = écart jusqu'au `timestamp_seconds` de la frame suivante dans la
   liste complète (y compris les frames sans détection, dont le `segment_action_level` est `None`
   pour les 4 zones — elles ne contribuent à aucun cumul de zone, mais leur timestamp compte pour
   calculer la durée de la frame précédente, exactement comme dans le résumé global).
3. Pour chaque frame dont le niveau d'une zone est `investigation_et_changement_bientot` ou
   `changement_immediat`, sa durée est ajoutée au cumul de cette zone.
4. La zone au cumul le plus élevé gagne. Égalité stricte → `trunk > neck > upper_arm >
   lower_arm`. Si les 4 cumuls sont à zéro → `None` (pas de recommandation).

## Frontend

`web/app/page.tsx` : après l'affichage du résumé existant (résultat d'une analyse tout juste
terminée), un appel à `GET /analyses/{id}/recommendation` (même pattern que le fetch déjà fait
pour `pose3d_url`) affiche un petit bloc "Recommandation" — libellé français de la zone (cou /
tronc / bras / avant-bras) + titre et description de la capsule. Rien n'est affiché si `zone` est
`null`.

## Gestion d'erreurs

- `analysis_id` inconnu sur `GET /analyses/{id}/recommendation` → 404, même pattern que les autres
  routes `/analyses/{id}/...`.
- Zone identifiée mais catalogue vide pour cette zone (ne devrait pas arriver vu la contrainte
  "au moins une entrée par zone mesurée", mais `recommend_capsule` reste défensif) → `capsule:
  null` dans la réponse plutôt qu'une erreur, `zone` reste renseigné.

## Tests

- `tests/test_capsules.py` (nouveau) : `compute_worst_zone` — cumul de durée par zone sur un jeu de
  frames construit à la main, départage par égalité stricte (ordre `trunk > neck > upper_arm >
  lower_arm`), cas où aucune zone n'est dégradée (`None`), frames non détectées ignorées pour le
  cumul mais comptées pour les durées. `recommend_capsule` — retourne la première capsule de la
  zone, `None` si zone `None` ou catalogue vide pour cette zone.
- `tests/test_storage.py` : `get_frame_segments` — round-trip (colonnes et ordre corrects), `None`
  sur id inconnu.
- `tests/test_api.py` : `GET /analyses/{id}/recommendation` end-to-end (zone + capsule cohérentes
  avec des frames construites pour avoir une zone dégradée connue), 404 sur id inconnu.

## Hors périmètre de ce sprint

- Vraies vidéos de capsules (contenu placeholder uniquement dans ce sprint).
- Édition du catalogue (pas d'admin UI ni de CMS).
- UI d'historique montrant les recommandations passées (reste hors périmètre, comme pour le
  sprint stockage DuckDB).
- Mode temps réel (vérification via webcam que l'étirement est bien exécuté, mentionnée au
  README §6 comme "optionnel").
- Zones "poignets/mains" et "hanches" (décision de cadrage ci-dessus).
- Recommandation de plusieurs capsules par zone.
