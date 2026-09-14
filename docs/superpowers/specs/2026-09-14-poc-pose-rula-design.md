# PoC Phase 1 — Pipeline Pose Estimation & Score RULA

**Date** : 2026-09-14
**Statut** : Approuvé

## Contexte

Ce document couvre la Phase 1 de la roadmap TMS Vision (voir `README.md`) : un pipeline Python qui lit une vidéo (fichier ou webcam), extrait la posture via MediaPipe Pose, calcule les angles articulaires pertinents, et produit un score RULA complet (tables officielles) frame par frame, avec sortie vidéo annotée et export de données.

## Contrainte d'environnement

MediaPipe ne supporte pas Python 3.14 (version active sur la machine de dev). Le projet utilise un **venv dédié en Python 3.11** (déjà disponible via `brew install python@3.11`), isolé du reste du système.

## Approche

Package Python modulaire : chaque étape du pipeline (capture, pose, angles, scoring RULA, overlay, export) est un module isolé, testable indépendamment. Ce découpage permet de brancher le pipeline sur un backend FastAPI en Phase 2 sans réécriture.

## Structure du projet

```
TMS vision/
├── README.md
├── requirements.txt
├── .python-version                → 3.11
├── src/tms_vision/
│   ├── capture.py                  # webcam ou fichier vidéo
│   ├── pose_estimation.py          # wrapper MediaPipe Pose (33 keypoints)
│   ├── angles.py                   # calcul vectoriel des angles articulaires
│   ├── rula/
│   │   ├── tables.py                # tables officielles RULA (A, B, C)
│   │   └── scoring.py               # angles + params manuels → score RULA
│   ├── overlay.py                   # squelette + angles + score sur la vidéo
│   ├── export.py                    # écriture CSV/JSON par frame + résumé
│   └── cli.py                       # point d'entrée (arguments, orchestration)
├── tests/
│   ├── test_angles.py               # géométrie sur landmarks synthétiques
│   └── test_rula_tables.py          # vérif des tables contre exemples connus
├── samples/                         # vidéos de test (gitignored)
└── outputs/                         # vidéos annotées + exports (gitignored)
```

## Flux de données

1. `capture.py` fournit des frames (webcam `cv2.VideoCapture(0)` ou fichier vidéo).
2. `pose_estimation.py` extrait les landmarks MediaPipe Pose par frame (33 keypoints x/y/z/visibilité).
3. `angles.py` calcule par vecteurs :
   - Cou : flexion/extension par rapport à la verticale du tronc.
   - Tronc : flexion + inclinaison latérale.
   - Épaule : flexion/abduction par rapport à l'axe du tronc.
   - Coude : angle bras/avant-bras.
   - Poignet : flexion, via les landmarks index/pouce déjà fournis par MediaPipe Pose (pas besoin du modèle Hands).
4. `rula/scoring.py` applique la méthode RULA officielle en 3 étapes :
   - **Table A** : bras + avant-bras + poignet + torsion poignet → score de posture A, puis + usage musculaire (0 ou 1) + force/charge (0-3) → score A final ("Wrist and Arm Score").
   - **Table B** : cou + tronc + jambes → score de posture B, puis + usage musculaire + force/charge → score B final ("Neck, Trunk and Leg Score").
   - **Table C** : croisement score A final × score B final → score RULA global (1-7).
5. `overlay.py` dessine le squelette et un badge de score coloré (vert 1-2 / jaune 3-4 / orange 5-6 / rouge 7, cohérent avec la matrice du README) sur chaque frame, exporté en vidéo annotée.
6. `export.py` écrit un CSV/JSON par frame (angles, sous-scores, score final) + un résumé de fin d'analyse (score max, score moyen, % de temps par zone de risque).

## Paramètres non mesurables par la caméra

Une caméra RGB monoculaire ne peut pas mesurer fiablement la force appliquée, la torsion fine du poignet, ni le support des jambes. Ces paramètres sont donc gérés ainsi :

- **Charge/force** : argument CLI `--load-kg` (poids estimé), mappé sur l'échelle de force RULA (0-3).
- **Torsion du poignet** : argument CLI `--wrist-twist normal|extreme`.
- **Jambes** : hypothèse fixe "jambes soutenues" (score 1), documentée comme limite connue du PoC — pas de détection fiable en monoculaire à ce stade.
- **Usage musculaire** (posture statique >1 min ou répétée >4x/min) : calculé automatiquement via une heuristique de variance des angles dans le temps sur la fenêtre vidéo (30s-3min), pas d'input manuel nécessaire.

## Gestion d'erreurs

- Landmark non détecté ou visibilité sous seuil → frame marquée "non détectée" dans l'export, aucun crash du pipeline.
- Webcam indisponible → message d'erreur explicite à l'utilisateur.
- Paramètres CLI invalides (ex : poids négatif) → validation et rejet à l'entrée.

## Tests

- `test_angles.py` : landmarks synthétiques avec angles géométriques connus (ex : bras à 90° exact), vérifie la justesse du calcul vectoriel.
- `test_rula_tables.py` : vérifie les tables RULA implémentées contre des exemples de référence publiés dans la littérature ergonomique.

## Hors périmètre (Phase 1)

- Anonymisation du visage (prévue Phase 2 selon le README).
- Interface web / API FastAPI (Phase 2/3).
- Bibliothèque de capsules vidéo d'étirements (Phase 2).
- Déclenchement intelligent des micro-pauses (Phase 2).
