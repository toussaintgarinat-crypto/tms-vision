# Floutage des visages de la vidéo annotée

**Date** : 2026-10-22
**Statut** : Livré

## Contexte

Le README (§7) annonçait une « anonymisation à la source » des visages, jamais implémentée : la
vidéo annotée d'une analyse (image d'origine + squelette dessiné) était stockée dans DuckDB avec les
visages nets. Cela bloquait tout pilote avec de vraies personnes.

## Décisions

- **Pixellisation, pas flou gaussien.** Un flou se « déflouté » plus facilement et reste
  reconnaissable à fort contraste ; une mosaïque d'environ 8 blocs sur la région est irréversible à
  l'œil. Hors de la région, les pixels sont strictement identiques à l'image d'origine (testé).
- **Où.** Dans `pipeline.analyze_video`, juste avant `draw_overlay` : l'image pixellisée est la seule
  à être écrite dans la vidéo annotée. Les angles et la pose sont calculés sur l'image d'origine
  (le visage aide la pose), qui ne vit qu'en mémoire.
- **Deux sources de position, réunies.**
  1. La **pose** : ellipse déduite des points du visage (nez, yeux, oreilles, bouche) et des épaules,
     marges généreuses (la pose ne donne ni front, ni cheveux, ni menton). Sûre pour la personne
     analysée, même de profil ou de dos.
  2. Un **détecteur de visages** indépendant (MediaPipe BlazeFace, modèle longue portée, seuil de
     confiance bas exprès) : couvre les **autres personnes** du champ, que la pose, limitée à une
     seule personne, ne voit pas. Une boîte détectée est élargie (oreilles, cheveux, menton).
- **Principe de sûreté : en cas de doute, flouter plus.**
  - Pose perdue : la dernière position de la tête est conservée, élargie de 40 %, pendant 1 s.
  - Au-delà, ou avant la première détection : **toute l'image est pixellisée**.
  - Un détecteur qui ne démarre pas **interrompt l'analyse** au lieu de la poursuivre sans floutage.
- **Pas d'interrupteur public.** `analyze_video(..., anonymize=True)` par défaut ; ni l'API ni la
  CLI ne le désactivent. Le paramètre n'existe que pour les tests.
- **Sessions d'envoi abandonnées.** Leurs morceaux contiennent la vidéo brute : purgés au démarrage de
  l'API et à chaque nouvel envoi après 24 h sans activité (`api._purge_stale_upload_sessions`).

## Mesures

- **Sur un vrai visage** (photo de la NASA, domaine public, fournie par scikit-image) : le détecteur
  trouve le visage avant, et plus aucun après, avec la pose seule, avec le détecteur seul, et avec les
  deux. Avec deux personnes dans l'image, la pose seule en laisse une visible : le détecteur est donc
  nécessaire.
- **De bout en bout, vraie chaîne sur une vraie vidéo** (30 images, mouvement, zoom, 4 images sans
  personne) : visage lisible dans 26 images sur 30 sans floutage, **0 sur 30 avec**.
- **Coût** : environ 10 à 20 ms de plus par image à 640×640 (analyse de 33-40 à 49-55 ms par image).

## Limites connues

- Ce n'est **pas une garantie d'anonymat**. Le détecteur peut manquer un visage petit, très éloigné,
  de profil ou partiellement caché, et la pose ne suit qu'une personne. Le corps, les vêtements, le
  badge et le poste de travail restent visibles : au sens du RGPD, la personne peut rester
  identifiable. **Vérifier à l'œil les premières vidéos annotées d'un pilote.**
- Les analyses enregistrées **avant** cette fonctionnalité contiennent des visages non floutés (il
  n'y a pas encore de route de suppression).
- Les images brutes existent en mémoire pendant l'analyse, et le fichier envoyé sur le disque
  jusqu'à la fin de l'analyse.
- Pas d'audio : la vidéo annotée n'en contient pas.
- L'estimation de pose et le détecteur reposent sur `mediapipe.solutions`, plafonné sous 0.10.30
  (voir `requirements.txt`).
- Non couvert : consentement et information des salariés, authentification, droit à l'effacement.

## Tests

`tests/test_face_blur.py` (27, sur images synthétiques) ; `tests/test_pipeline_anonymization.py` (8,
vérifie ce qui est réellement écrit, avec des doubles) ; `tests/test_face_blur_real_faces.py` (5, sur
vrais visages ; ignoré sans scikit-image ou sans `mediapipe.solutions`) ; `tests/test_upload_purge.py`
(8).
