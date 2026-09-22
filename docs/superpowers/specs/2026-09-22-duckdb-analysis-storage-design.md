# Stockage des analyses RULA dans DuckDB

**Date** : 2026-09-22
**Statut** : Approuvé (design), implémentation à planifier

## Contexte

Depuis la Tranche 1 de la Phase 2, `POST /analyses` (et le flux d'upload par chunks) lance
`analyze_video()` et écrit les résultats directement sur le système de fichiers du serveur, dans
`outputs/` : vidéo annotée (`{run_id}_annotated.mp4`), CSV par frame (`{run_id}_frames.csv`),
résumé agrégé (`{run_id}_summary.json`) et landmarks 3D lissés (`{run_id}_pose3d.json`). Ces
fichiers sont servis tels quels via `GET /outputs/{filename}` (`src/tms_vision/api.py`).

Cette approche n'offre aucune persistance interrogeable dans le temps : pas de liste des analyses
passées, pas de filtrage par salarié/poste/date, pas de requête possible sur l'évolution des scores
ou des zones RULA dégradées — chaque analyse est un tas de 4 fichiers isolés, retrouvables
seulement par leur `run_id` si on le connaît déjà. C'est bloquant pour :

1. Tout futur tableau de bord RH/HSE (§6/§8 du README) qui a besoin d'un historique interrogeable.
2. Le sprint suivant (recommandation de capsules par zone), qui a besoin de savoir quelle zone RULA
   a été la plus dégradée sur une analyse donnée — aujourd'hui, la seule source de cette
   information est `segment_action_levels` dans `pose3d.json`, un fichier à reparser entièrement à
   chaque fois faute de structure interrogeable.

Cette tranche migre le stockage des résultats d'analyse (métadonnées, scores par frame, vidéo
annotée, landmarks 3D) hors du système de fichiers, vers DuckDB.

**Recherche faite avant ce document** :

- `Pose3DFrameRecord.segment_action_levels` (`pose3d_export.py`) porte déjà, par frame, le niveau
  d'action (`action_level()`, `scoring.py`) des 4 segments réellement mesurés : `neck`, `trunk`,
  `upper_arm`, `lower_arm`. `legs` est une constante jamais mesurée (voir la Tranche 4 de l'avatar
  3D) et `wrist` n'a pas d'équivalent musculaire dans le rig — ces deux-là restent hors de
  `segment_action_levels` mais leurs scores bruts existent toujours par frame dans `RulaScore`
  (exportés aujourd'hui uniquement dans le CSV).
- `ResultsExporter._summary()` (`export.py`) calcule déjà le résumé agrégé (`max_score`,
  `average_score`, `time_by_action_level`) à partir de la liste de `FrameRecord` accumulée en
  mémoire — cette logique de calcul n'a pas besoin de changer, seule sa destination (retour Python
  au lieu d'écriture disque) change.
- Aucune dépendance DuckDB dans `requirements.txt` actuellement ; aucune notion de salarié/poste
  dans l'API (`side`/`load_kg`/`wrist_twist` uniquement).
- `outputs/` est déjà dans `.gitignore` ; contient aujourd'hui uniquement des runs de test/dev
  (timestamps 2026-09-14/15), non conservés par ce sprint (voir Décisions de cadrage).

## Décisions de cadrage

- **DuckDB stocke tout, y compris les blobs binaires** (vidéo annotée, JSON pose3D) — pas
  seulement les métadonnées. Plus aucun fichier de résultat d'analyse n'est écrit sur disque de
  façon durable ; `outputs/` cesse d'être utilisé par ce flux (il reste utilisé transitoirement par
  les sessions d'upload par chunks, voir plus bas).
- **Les données par frame sont éclatées en lignes SQL interrogeables** (table `analysis_frames`),
  pas seulement conservées dans un JSON de résumé. C'est l'intérêt principal de choisir DuckDB
  (moteur OLAP) plutôt qu'un simple key-value store : permet de vraies requêtes SQL sur l'évolution
  des scores et des zones dans le temps, dont le sprint recommandation de capsules a besoin.
- **Les landmarks 3D bruts restent un blob JSON unique par analyse** (`analyses.pose3d_json`), pas
  éclatés en lignes. Contrairement aux scores, ils ne sont jamais interrogés individuellement —
  seulement rejoués en bloc, frame par frame, par `PostureAvatar3D.tsx`. Les décomposer en lignes
  ajouterait de la complexité sans aucun bénéfice de requêtage.
- **Un identifiant libre `worker_label`/`poste_label`**, texte optionnel, est ajouté aux formulaires
  de création d'analyse pour permettre le filtrage par salarié/poste. Ce n'est pas un système
  d'utilisateurs/authentification — juste un tag texte, cohérent avec l'absence d'auth actuelle du
  projet.
- **Ce sprint écrit ET expose la lecture** (`GET /analyses`, `GET /analyses/{id}`) — pas seulement
  l'écriture. Nécessaire pour le sprint recommandation de capsules et pour tout futur tableau de
  bord.
- **Les endpoints `/outputs/{filename}` sont remplacés**, pas conservés en façade. Le frontend est
  déjà générique sur la forme des URLs (`annotated_video_url`/`csv_url`/`pose3d_url` sont utilisées
  telles que renvoyées par l'API, jamais construites côté client) — aucune raison de garder l'ancien
  format.
- **Le CSV par frame reste disponible, mais généré à la volée** depuis `analysis_frames`
  (`GET /analyses/{id}/frames.csv`), au lieu d'être stocké comme fichier ou blob séparé — ce serait
  une donnée dérivée redondante avec la table SQL.
- **Les sessions d'upload par chunks ne migrent pas.** `POST /uploads`, `PUT
  /uploads/{id}/chunks/{index}` gèrent un état **transitoire** de transport (le temps que le client
  envoie tous les morceaux d'un fichier), pas un « résultat RULA » à persister dans le temps. Ce
  sprint les laisse inchangées, sur le système de fichiers (`outputs/.uploads/`) comme aujourd'hui ;
  seul le résultat final produit par `POST /uploads/{id}/complete` (comme par `POST /analyses`) est
  persisté en DuckDB.
- **Seules les nouvelles analyses passent par DuckDB.** Les fichiers déjà présents dans `outputs/`
  (runs de test/dev antérieurs à ce sprint) ne sont pas migrés — pas de script de reprise
  d'historique dans ce sprint.

## Architecture

Nouveau module `src/tms_vision/storage.py`, seul point d'accès à DuckDB (fichier local
`data/tms_vision.duckdb`, créé au démarrage si absent, ajouté à `.gitignore`). Chaque fonction ouvre
sa propre connexion (`duckdb.connect(DB_PATH)`) le temps de l'opération — pattern simple type
`sqlite3`, suffisant à l'échelle actuelle du projet (un seul process `uvicorn`, pas de charge
concurrente à optimiser).

`pipeline.analyze_video()` devient **pur** : il ne touche plus `outputs/`. La seule écriture
disque restante est un **fichier temporaire** (`tempfile`), requis par la contrainte technique de
`cv2.VideoWriter` (qui n'accepte pas d'écrire directement en mémoire) — le fichier est relu en
bytes puis supprimé avant que la fonction ne retourne, donc invisible de l'extérieur. `export.py`
perd son écriture CSV/JSON sur disque ; sa logique de calcul du résumé (`_summary()`) et des lignes
par frame est conservée, mais retournée comme structures Python plutôt qu'écrite sur disque.

`api.py` appelle `analyze_video()` (calcul) puis `storage.save_analysis(...)` (persistance),
et expose les nouvelles routes de lecture en s'appuyant sur `storage.py`.

## Modèle de données

```sql
CREATE TABLE IF NOT EXISTS analyses (
    id VARCHAR PRIMARY KEY,              -- même format de run_id qu'aujourd'hui (horodatage + hex)
    created_at TIMESTAMP NOT NULL,
    side VARCHAR NOT NULL,
    load_kg DOUBLE NOT NULL,
    wrist_twist VARCHAR NOT NULL,
    worker_label VARCHAR,                -- nullable, texte libre
    poste_label VARCHAR,                 -- nullable, texte libre
    frame_count INTEGER NOT NULL,
    detected_frame_count INTEGER NOT NULL,
    max_score INTEGER NOT NULL,
    average_score DOUBLE NOT NULL,
    time_by_action_level VARCHAR NOT NULL,  -- JSON texte, ex: {"acceptable": 12.3, ...}
    video_bytes BLOB NOT NULL,
    pose3d_json VARCHAR NOT NULL          -- JSON texte (landmarks 3D lissés, par frame)
);

CREATE TABLE IF NOT EXISTS analysis_frames (
    analysis_id VARCHAR NOT NULL REFERENCES analyses(id),
    frame_index INTEGER NOT NULL,
    timestamp_seconds DOUBLE NOT NULL,
    detected BOOLEAN NOT NULL,
    neck_flexion_deg DOUBLE,
    trunk_flexion_deg DOUBLE,
    upper_arm_flexion_deg DOUBLE,
    lower_arm_angle_deg DOUBLE,
    wrist_flexion_deg DOUBLE,
    upper_arm_score INTEGER,
    lower_arm_score INTEGER,
    wrist_score INTEGER,
    wrist_twist_score INTEGER,
    posture_score_a INTEGER,
    neck_score INTEGER,
    trunk_score INTEGER,
    legs_score INTEGER,
    posture_score_b INTEGER,
    muscle_use_score INTEGER,
    force_load_score INTEGER,
    final_score INTEGER,
    action_level VARCHAR,
    neck_segment_action_level VARCHAR,
    trunk_segment_action_level VARCHAR,
    upper_arm_segment_action_level VARCHAR,
    lower_arm_segment_action_level VARCHAR,
    PRIMARY KEY (analysis_id, frame_index)
);
```

Toutes les colonnes de scores/angles par frame sont nullables : une frame sans détection de pose
(`detected = false`) n'a ni angles ni scores, exactement comme aujourd'hui dans le CSV (colonnes
vides).

## API

- **`POST /analyses`** (multipart, inchangé + 2 champs) : `file`, `side`, `load_kg`,
  `wrist_twist`, `worker_label` (optionnel), `poste_label` (optionnel). Réponse :
  `{ analysis_id, summary, annotated_video_url, csv_url, pose3d_url, side }`, où les URLs pointent
  vers `/analyses/{analysis_id}/video`, `/analyses/{analysis_id}/frames.csv`,
  `/analyses/{analysis_id}/pose3d`.
- **`POST /uploads/{id}/complete`** : mêmes 2 champs ajoutés, même forme de réponse.
- **`GET /analyses/{id}/video`** — sert `video_bytes` (`media_type="video/mp4"`). 404 si id
  inconnu.
- **`GET /analyses/{id}/pose3d`** — sert `pose3d_json` (JSON). 404 si id inconnu.
- **`GET /analyses/{id}/frames.csv`** — génère le CSV à la volée depuis `analysis_frames`, même
  colonnes (`CSV_FIELDS`) qu'aujourd'hui. 404 si id inconnu.
- **`GET /analyses`** — liste les analyses (id, created_at, side, worker_label, poste_label,
  résumé), triées par `created_at` décroissant. Filtres optionnels en query params :
  `worker_label`, `poste_label`, `since`, `until` (dates ISO).
- **`GET /analyses/{id}`** — détail d'une analyse (mêmes champs que dans la liste). 404 si id
  inconnu.
- **`GET /outputs/{filename}`** est supprimé.

**Limite acceptée** : servir la vidéo depuis un blob DuckDB (au lieu de `FileResponse`) perd le
support automatique des requêtes HTTP `Range` que Starlette offrait pour un fichier statique — pas
de seeking optimisé côté navigateur (un scrub dans la timeline retélécharge le blob entier plutôt
qu'une plage d'octets). Acceptable vu le plafond actuel des clips (≤ 30s, quelques centaines de Ko
à quelques Mo observés dans `outputs/` aujourd'hui). Hors périmètre de ce sprint.

## Gestion d'erreurs

- Id d'analyse inconnu sur n'importe quelle route `/analyses/{id}...` → 404, même pattern que
  l'actuel `GET /outputs/{filename}`.
- Le garde-fou mémoire existant (`_reject_if_estimated_too_large`, rejet 422 si la vidéo est trop
  volumineuse pour le budget mémoire du serveur) est inchangé — il s'applique avant tout calcul,
  indépendamment de la destination finale des résultats.

## Tests

- `tests/test_storage.py` (nouveau) : création de schéma idempotente, round-trip
  `save_analysis`/lecture (analyses + frames), génération CSV à la volée fidèle à l'ancien format
  de colonnes, filtrage de la liste par `worker_label`/`poste_label`/`since`/`until`.
- `tests/test_pipeline.py` : adapté pour vérifier le contenu retourné en mémoire par
  `analyze_video()` (bytes vidéo, JSON pose3D, lignes de frames) plutôt que des fichiers sur disque.
- `tests/test_export.py` : adapté pour vérifier les structures Python retournées par le calcul de
  résumé/lignes, la logique de calcul elle-même ne change pas.
- `tests/test_api.py` : adapté aux nouvelles routes (`/analyses/{id}/video`, `.../pose3d`,
  `.../frames.csv`, `GET /analyses`, `GET /analyses/{id}`), 404 sur id inconnu, présence des
  nouveaux champs `worker_label`/`poste_label` dans la réponse et dans la liste.

## Hors périmètre de ce sprint

- UI d'historique/dashboard consommant `GET /analyses` (seule l'API est livrée ; pas d'écran
  frontend listant les analyses passées).
- Migration des runs déjà présents dans `outputs/` (décision de cadrage ci-dessus).
- Authentification / vrais comptes utilisateurs (`worker_label`/`poste_label` restent des tags
  texte libres).
- Support des requêtes `Range` pour le streaming vidéo (limite acceptée ci-dessus).
- Concurrence multi-process sur le fichier DuckDB (hors échelle actuelle du projet — un seul
  process `uvicorn`).
- La brique recommandation de capsules par zone (sprint suivant, qui s'appuiera sur
  `analysis_frames` mais fait l'objet de sa propre spec).
