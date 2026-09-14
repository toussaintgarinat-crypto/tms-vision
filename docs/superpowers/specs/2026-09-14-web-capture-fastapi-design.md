# Phase 2 (tranche 1) — Capture web + API FastAPI

**Date** : 2026-09-14
**Statut** : Approuvé

## Contexte

Ce document couvre la première tranche de la Phase 2 de la roadmap TMS Vision (voir
`README.md` section 8). La Phase 1 (pipeline Python MediaPipe → angles → score RULA) est
terminée et testée (66 tests), mais n'a jamais été exercée sur une vraie personne — seulement
sur une vidéo synthétique, faute de webcam dans l'environnement de dev de la Phase 1.

Cette tranche a deux objectifs simultanés :
1. Remplacer la capture CLI (`cli.py --source webcam`, dépendante d'OpenCV et d'une webcam
   branchée sur la machine qui exécute Python) par une capture depuis un navigateur — cohérent
   avec le besoin produit : l'app doit pouvoir tourner sur les appareils des utilisateurs
   (ordinateur, mobile), pas seulement sur la machine du développeur.
2. Servir de première brique concrète de la Phase 2 : extraire le pipeline Phase 1 en fonction
   réutilisable, exposée via une API FastAPI, consommée par une interface web — exactement ce
   que demande déjà le README section 8 pour la Phase 2 ("exposer les mêmes étapes comme
   fonctions appelables depuis un backend FastAPI, sans dupliquer la logique").

Une fois cette brique construite, elle sert aussi à faire la vérification qui était en attente
depuis la fin de la Phase 1 : filmer une vraie personne (toi) et vérifier visuellement que le
squelette se superpose correctement et que le score RULA correspond à la posture observée.

## Décisions de cadrage

- **Enregistrer puis analyser, pas de temps réel.** Le navigateur enregistre un clip complet
  puis l'envoie en un seul fichier ; le backend traite le clip une fois reçu et renvoie le
  résultat. Le pipeline Phase 1 traite déjà les vidéos par lot (toutes les frames en mémoire,
  deux passes) — une capture temps réel frame par frame demanderait de réécrire cette couche,
  hors scope ici.
- **Caméra 2D en priorité, pas de LiDAR dans cette tranche.** Le LiDAR n'est accessible depuis
  un navigateur que via l'API WebXR `depth-sensing`, expérimentale et limitée à Safari sur
  iPhone/iPad Pro — et ses données (buffers de profondeur bruts) ne sont pas un format vidéo
  standard, donc pas compatibles avec l'approche "enregistrer un clip puis l'uploader" retenue
  ci-dessus. Cette tranche capture uniquement la caméra RGB standard (`getUserMedia`), qui
  fonctionne sur tous les navigateurs/appareils. Le support LiDAR est une amélioration future
  possible, pas un prérequis de cette tranche.
- **Pas de base de données, pas de queue de jobs.** Les clips de vérification durent quelques
  dizaines de secondes : un traitement synchrone (la requête HTTP attend la fin de l'analyse)
  est acceptable. Les résultats restent sur le système de fichiers (`outputs/`), comme en
  Phase 1. La base de données prévue au README section 8 arrivera dans une tranche ultérieure.
- **Next.js pour le frontend**, conformément au choix déjà acté au README section 8, plutôt
  qu'une page statique jetable — cette brique devient une fondation réutilisable, pas un
  prototype à refaire.

## Approche

Extraire la logique de `cli.py` en une fonction Python réutilisable, l'exposer via un
endpoint FastAPI, et construire une page Next.js qui enregistre une vidéo dans le navigateur et
l'envoie à cet endpoint.

## Structure du projet (ajouts sur l'existant)

```
TMS vision/
├── src/tms_vision/
│   ├── pipeline.py                  # NOUVEAU — analyze_video(), extrait de cli.run()
│   ├── api.py                       # NOUVEAU — app FastAPI
│   └── cli.py                       # MODIFIÉ — devient un wrapper fin autour de pipeline.py
├── tests/
│   ├── test_pipeline.py             # NOUVEAU — reprend la couverture de test_cli.py
│   └── test_api.py                  # NOUVEAU — TestClient FastAPI
├── web/                              # NOUVEAU — app Next.js
│   ├── app/
│   │   └── page.tsx                  # page unique : capture, formulaire, résultat
│   └── ...
└── outputs/                          # existant, inchangé (gitignored)
```

## Flux de données

1. Le navigateur demande l'accès caméra (`getUserMedia`) et affiche un aperçu live.
2. L'utilisateur renseigne le formulaire (côté filmé, charge en kg, torsion du poignet — mêmes
   paramètres que les arguments CLI `--side`/`--load-kg`/`--wrist-twist`) et lance
   l'enregistrement (`MediaRecorder`).
3. À l'arrêt, le navigateur envoie le clip enregistré (webm ou mp4 selon le navigateur) en
   `POST /analyses` (multipart, fichier + champs du formulaire) vers l'API FastAPI.
4. `api.py` sauvegarde le fichier reçu sur disque, puis appelle
   `pipeline.analyze_video(video_path, side, load_kg, wrist_twist, output_dir)`.
5. `pipeline.analyze_video()` exécute exactement le pipeline Phase 1 déjà validé (capture →
   pose → angles → score RULA → overlay → export), inchangé dans sa logique.
6. `api.py` renvoie un JSON contenant le résumé (score max, score moyen, temps par niveau
   d'action) et les URLs relatives vers la vidéo annotée et le CSV, servis via un montage
   `StaticFiles` sur `outputs/`.
7. La page Next.js affiche le résultat : vidéo annotée intégrée, résumé du score, lien de
   téléchargement du CSV.

## Point de vigilance technique

`cv2.VideoCapture` (utilisé par `capture.py`, inchangé dans cette tranche) doit pouvoir décoder
le conteneur produit par `MediaRecorder` du navigateur — typiquement webm/VP8 sous
Chrome/Firefox, potentiellement mp4/H.264 sous Safari. À vérifier dès la première tâche
d'implémentation, avant de construire le reste de la chaîne : c'est le principal risque
technique de cette tranche. Si le décodage échoue, la solution de repli est de forcer un type
MIME supporté côté `MediaRecorder` (`video/mp4` si le navigateur le propose) plutôt que de
modifier `capture.py`.

## Gestion d'erreurs

- Aucune pose détectée sur l'ensemble du clip → comportement déjà géré par le pipeline Phase 1
  (résumé avec `detected_frame_count: 0`, `max_score: 0`) : réponse HTTP 200 normale, ce n'est
  pas une erreur.
- Fichier vidéo illisible par `cv2` (conteneur non supporté, upload corrompu) → équivalent des
  exceptions `FileNotFoundError`/`RuntimeError` déjà catchées côté CLI (`cli.main()`), renvoyé
  en HTTP 422 avec un message clair, affiché dans l'UI.
- Accès caméra refusé ou indisponible (permission refusée, contexte non sécurisé — `getUserMedia`
  exige HTTPS ou `localhost`) → message d'erreur affiché avant même de proposer l'enregistrement,
  géré côté navigateur.

## Tests

- `test_pipeline.py` : reprend les cas de `test_cli.py` mais appelle `analyze_video()`
  directement plutôt que de passer par les arguments CLI.
- `test_api.py` : `TestClient` FastAPI, upload de `samples/synthetic_smoke_test.mp4` (fixture
  déjà existante) pour vérifier le cas "aucune détection" de bout en bout via l'API.
- Pas de test end-to-end navigateur dans cette tranche (accès caméra difficile à automatiser en
  CI) — la vérification manuelle par l'utilisateur du projet, en filmant une vraie personne, est
  justement l'objectif produit de cette tranche.

## Hors périmètre (cette tranche)

- Capture/traitement LiDAR ou profondeur (amélioration future possible, pas de cette tranche).
- Base de données, historique des analyses.
- Authentification, déploiement, hébergement.
- Floutage RGPD des visages (acceptable ici car usage de vérification personnelle, pas un
  déploiement avec de vrais salariés — reste bloquant avant tout pilote réel, voir README
  section 7).
- Calibrage des seuils géométriques sur données réelles (étape de suivi séparée, une fois cette
  brique construite et le premier clip réel obtenu).
