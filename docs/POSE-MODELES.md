# Modèles de pose : choisir, activer, utiliser

TMS Vision ne dépend plus d'un seul modèle de détection. Avant une analyse, on choisit le modèle et ses
options ; tout le reste (angles, score RULA, CSV, rapports, historique) fonctionne comme avant.

## Quel modèle choisir

| Modèle | Points | Pour quoi faire | À savoir |
|---|---|---|---|
| **MediaPipe Pose 33** (défaut) | 33 | Score RULA et analyse ergonomique globale | Rapide, léger, avatar 3D. Identique à ce que faisait l'application avant le sélecteur. |
| **MediaPipe Pose + Hands** | 33 + 21 par main | Gestes fins : préhensions, flexion des doigts, gestes répétitifs | Utile quand la caméra est proche des mains. |
| **RTMPose / DWPose Whole-body** | jusqu'à 133 | Corps, pieds, mains et visage | Installation facultative, nettement plus lent, 2D : pas d'avatar 3D ni d'angle de cheville. |
| **Custom keypoints** | 1 à 10 points à vous | Suivre un outil, une caisse, une pièce, une zone de danger | Vous placez les points sur une image ; ils sont suivis dans la suite de la vidéo. |

Les options **mains**, **pieds** (whole-body seulement), **visage** (whole-body seulement) et **points
personnalisés** se combinent avec le modèle choisi. Le site affiche le nombre de points suivis par
personne avant l'envoi.

Le modèle whole-body est RTMW-x (famille RTMPose/DWPose, mode « performance » de la bibliothèque
`rtmlib`), open source (Apache 2.0), exécuté par ONNX Runtime sans PyTorch.

## Dans le site

1. Page d'analyse : choisir une vidéo (ou filmer), puis descendre jusqu'à **Modèle de pose**.
2. Choisir le modèle, cocher les options voulues. Le whole-body est grisé, avec la commande
   d'installation, s'il n'est pas installé sur le serveur.
3. **Points personnalisés** : régler l'image de référence avec le curseur, cliquer sur l'objet à
   suivre (jusqu'à 10 points), donner un nom à chaque point. L'image est figée tant que des points sont
   posés (le suivi part de cette image, vers la suite de la vidéo) ; « Effacer tous les points » permet
   d'en choisir une autre. Rien n'est envoyé avant « Analyser ».
4. Le résultat (et la page de l'historique) affiche le panneau **Modèle de pose** : modèle utilisé,
   points par personne, points détectés par image, confiance moyenne, légende des couleurs de la vidéo
   annotée, tableaux des mains et des points personnalisés, et le lien d'export JSON des points.

Couleurs de la vidéo annotée : corps blanc, mains orange, pieds bleu clair, visage rose, points
personnalisés jaunes (avec leur nom).

## Par l'API

`POST /analyses` et `POST /uploads/{id}/complete` acceptent, en plus des champs habituels :

| Champ | Valeur | Rôle |
|---|---|---|
| `pose_model` | `mediapipe_pose_33` (défaut) ou `rtmpose_wholebody_133` | Modèle principal |
| `enable_wholebody` | `true` / `false` | Équivaut à `pose_model=rtmpose_wholebody_133` |
| `enable_hands` | `true` / `false` | Points et indicateurs des mains |
| `enable_feet`, `enable_face` | `true` / `false` | Whole-body seulement (sinon 422) |
| `custom_points` | `true` / `false` | Suivi de points personnalisés |
| `custom_points_json` | JSON | Requis avec `custom_points` |

```bash
curl -X POST http://localhost:8000/analyses \
  -F file=@poste.mp4 -F side=right -F load_kg=0 -F wrist_twist=normal \
  -F enable_hands=true \
  -F custom_points=true \
  -F 'custom_points_json={"reference_time_seconds": 1.2, "points": [{"name": "clé à molette", "x": 0.42, "y": 0.61}]}'
```

`x` et `y` sont normalisés (0 à 1) sur l'image de référence ; `reference_time_seconds` est l'instant de
cette image. Les noms sont convertis (`clé à molette` devient `custom_cle_a_molette`).

Une option invalide ou un modèle non installé renvoie **422** avec un message (par exemple la commande
d'installation), avant tout traitement. Sans aucune de ces options, l'analyse est celle d'avant.

Autres points d'accès :

- `GET /pose-models` : modèles proposés, avec `installed` (utilisé par le sélecteur) ;
- `GET /analyses/{id}` : en plus de l'existant, `pose_model`, `pose_options`, `keypoint_count`,
  `detection_quality`, `hands_metrics`, `custom_metrics` (anciennes analyses : MediaPipe Pose 33,
  options vides) ;
- `GET /analyses/{id}/keypoints` : les points des modèles complémentaires (mains, whole-body, points
  personnalisés), image par image, au format normalisé ci-dessous.

## Format normalisé

Tous les modèles produisent ce format ; les angles, le score RULA et l'export ne connaissent jamais le
modèle.

```json
{
  "frame": 120,
  "person_id": 1,
  "model": "mediapipe_pose_33",
  "keypoints": [
    {"name": "left_wrist", "x": 0.42, "y": 0.61, "z": 0.03, "confidence": 0.94, "visibility": 0.97}
  ]
}
```

- `x`, `y` normalisés sur l'image ; `z` relatif (0 pour les modèles 2D).
- Noms en minuscules : corps `left_shoulder`, `right_elbow`… ; mains `right_hand_wrist`,
  `right_index_tip`, `left_thumb_cmc`… ; pieds `left_heel`, `left_big_toe`… ; visage `face_0` à
  `face_67` ; points personnalisés `custom_<nom>`.
- Un point absent (non visible, confiance trop faible) est simplement omis : les calculs qui en
  dépendent sont ignorés sans erreur (par exemple pas de score RULA sur une image où l'épaule manque).
- `confidence` est entre 0 et 1. Les scores bruts du whole-body (qui ne sont pas des probabilités) sont
  convertis ; le seuil est réglé dans `pose_models/rtmpose_wholebody.py` (`SCORE_FLOOR`, `SCORE_FULL`).

## Indicateurs

**Mains** (`hands_metrics`, par côté) : taux de détection, flexion moyenne et maximale des doigts, nombre
de préhensions, durée cumulée, cadence par minute, indicateur « répétitif ». Une préhension commence quand
la flexion des doigts atteint 70° et se termine sous 60° (l'écart évite de compter plusieurs fois une
flexion qui oscille). La cadence n'est calculée qu'au-delà de 5 s de vidéo ; au-dessus de 30 préhensions
par minute, la main est marquée « répétitive ». Une main plus petite que 3 % de la hauteur de l'image n'a
pas de mesure des doigts. **Les seuils ne sont pas calibrés** (`extremity_thresholds.json`, comme les
autres seuils des extrémités) : à valider avec l'ostéopathe.

**Points personnalisés** (`custom_metrics`, par point) : taux de suivi, longueur du trajet, vitesse
maximale (en hauteurs d'image, pas en mètres), temps passé à moins de 6 % de la hauteur d'image d'un
poignet (« à la main »).

**Qualité de détection** (`detection_quality`) : images avec au moins un point, points trouvés par image,
confiance moyenne.

Les indicateurs des mains et des points sont **hors RULA** : le score RULA, le recalcul au poids et les
niveaux par segment ne changent pas.

## Installer le modèle whole-body (facultatif)

| Installation | Comment |
|---|---|
| Poste de développement | `./tms setup --with-wholebody`, ou `pip install -r requirements-wholebody.txt` dans le venv |
| Docker | `TMS_WITH_WHOLEBODY=1` dans `.env`, puis `docker compose up -d --build` (l'image est plus lourde) |
| Application de bureau | non proposé |

Les poids (environ 130 Mo) se téléchargent à la première analyse whole-body (de l'ordre d'une minute) ;
avec Docker ils sont gardés dans `outputs/.cache`. Sans l'installation, le modèle est grisé dans le site
et l'API répond 422 avec la commande à lancer ; tout le reste fonctionne.

Variable `TMS_WHOLEBODY_MODE` : `performance` (défaut, le plus précis), `balanced` ou `lightweight`
(plus rapides, moins précis).

**Vitesse mesurée** : environ 0,4 à 0,45 s par image en mode `performance` sur un processeur de 4 cœurs
sans carte graphique, soit une douzaine de minutes pour 1 minute de vidéo à 30 images/s. Les modes
`balanced` et `lightweight` doivent être plus rapides ; ils n'ont pas été mesurés. À titre de
comparaison, MediaPipe analyse 227 images en environ 12 s (mesure de la tranche 5,
`docs/superpowers/specs/2026-10-22-mains-pieds-design.md`). Pour des vidéos longues, préférer MediaPipe
et réserver le whole-body aux séquences courtes qui en ont besoin.

## Données enregistrées

- `analyses` : colonnes `pose_model`, `pose_options` (JSON), `keypoint_count`, `hands_metrics`,
  `custom_metrics`, `detection_quality` (JSON). Les bases existantes sont complétées au premier accès.
- `analysis_keypoints` : une ligne par image et par modèle complémentaire (`analysis_id`, `frame_index`,
  `model`, `keypoints_json`), écrite seulement si un modèle complémentaire est actif : une analyse
  standard ne coûte rien de plus. Les 33 points de MediaPipe Pose restent dans `pose3d_json`.

## Limites connues

- **Whole-body : 2D.** Pas d'avatar 3D ni d'angle de cheville (les valeurs restent vides, sans erreur).
  L'angle du poignet pour RULA utilise la base de l'index de la main du modèle, à la place du point
  MediaPipe : non validé contre une mesure de référence.
- **Whole-body : moins robuste que MediaPipe** quand la personne est petite ou au bord du cadre. Sur un
  extrait de 6 s d'un plan large (une seule vidéo, donc indicatif), 145 images sur 180 ont reçu un score
  contre 165 pour MediaPipe. Les seuils de confiance ont été calibrés sur trois images et vidéos : à
  réviser sur d'autres prises de vue.
- **Mains petites.** Sous 3 % de la hauteur d'image, pas de mesure des doigts. MediaPipe Hands ne retient
  que les mains proches d'un poignet détecté par Pose.
- **Points personnalisés.** Le suivi va de l'image de référence vers la fin de la vidéo (rien avant). Il
  peut dériver sur un objet sans texture ou après une longue occultation : le point est alors omis, pas
  inventé. Le trajet et la vitesse sont mesurés dans l'image : avec une caméra tenue à la main, ils
  reflètent surtout le mouvement de la caméra. Un modèle de détection entraîné (YOLO…) pourra être
  ajouté derrière la même interface.
- **Image de référence.** Le navigateur affiche l'image la plus récente qui ne dépasse pas l'instant
  demandé ; le serveur peut démarrer le suivi sur cette image ou la suivante (au plus une image d'écart).
- Une seule personne est suivie (la plus grande de l'image en whole-body).

## Ajouter un modèle (développeurs)

Le code est dans `src/tms_vision/pose_models/`.

1. Écrire une classe qui hérite de `BasePoseModel` (`base.py`) : `load()`, `process_frame(frame,
   frame_index)` renvoyant des `FramePose` au format normalisé, `close()`. Lever
   `ModelUnavailableError` dans `load()` si une dépendance manque (avec la commande d'installation).
2. L'enregistrer dans `registry.py` (`register(id, classe)`), avec `requires=(...)` dans ses
   métadonnées : le sélecteur sait alors s'il est installé.
3. Pour qu'il alimente les angles et le score RULA, fournir un pont vers les `Landmark` aux noms
   MediaPipe (voir `to_pose_landmarks` dans `rtmpose_wholebody.py` et `keypoints_to_landmarks` dans
   `schema.py`) : `angles.py` et RULA n'ont pas à changer.
4. Brancher l'option dans `options.py` (`PoseOptions.validate`) et le choix dans `pipeline.py`.

## Tests

- Python : `tests/test_pose_models.py`, `test_hand_metrics.py`, `test_wholebody.py`,
  `test_custom_points.py` (dont un suivi sur une vraie vidéo synthétique), `test_api.py`, `test_storage.py`.
- Web : `web/app/poseModels.test.ts`, `poseInfoFormat.test.ts`.
- Les tests du whole-body utilisent des doublures du modèle : ils ne téléchargent pas les poids.
