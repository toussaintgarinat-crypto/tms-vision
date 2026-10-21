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
- **Sur une vraie vidéo de poste de travail** (9 s, 1280×720, 227 images : une personne qui peint un mur,
  de profil ou de trois quarts, les bras levés, une échelle devant elle) : pose détectée dans 227
  images sur 227 ; relecture visuelle de 30 images réparties sur toute la durée : **les traits du
  visage (yeux, nez, bouche, joues) sont illisibles dans toutes**, y compris tête baissée, tournée ou
  levée ; audit indépendant par maillage facial sur gros plan de l'original : 9 visages exploitables,
  couverts à 100 % (échantillon réduit : le maillage échoue sur les profils). Le détecteur de visages
  seul ne trouvait le visage que dans 88 images sur 227 de l'original (les profils lui échappent) :
  la pose est indispensable, la conception en union était justifiée. Surcoût : 10,8 s sans floutage,
  12,8 s avec (+19 %).
- **Scène de groupe, vidéo libre de droit** (film NIOSH sur la protection antichute, Public.Resource.Org,
  archive.org `youtube-C3FvpjC7C6k`, CC BY 3.0 ; quatre extraits de 20 s) : plusieurs personnes, certaines
  très petites (≈ 25 px de tête). La pose seule ne suit qu'une personne et BlazeFace manque les petits
  visages. Ajout de **YuNet** (OpenCV Zoo, MIT) en union avec BlazeFace : sur l'image 521, les 3 visages
  sont couverts ; le petit ouvrier de droite l'est aux images 226 et 300 ; les deux visages principaux de
  l'image 595 aussi.
  **Restent des défauts constatés :** la tête d'un petit ouvrier penché sous un casque (≈ 25 px) échappe
  encore ; YuNet produit des faux positifs (grosses mosaïques sur torse ou sol, ex. image 447), ce qui
  dégrade l'image sans gêner l'anonymat. Les pourcentages de couverture d'un audit indépendant sont
  pollués par les faux positifs des détecteurs d'audit : seule la relecture visuelle fait foi.

- **Ne pas se fier à « plus aucun visage détecté ».** Sur cette vidéo, un détecteur de visages signale
  encore un visage dans 45 images de la sortie floutée : il se déclenche sur la **mosaïque** elle-même
  (vérifié visuellement : aucun trait lisible). Ce critère n'est donc pas une preuve sur de vraies
  vidéos ; il ne vaut que sur des images nettes comme la photo des tests. La preuve est la relecture
  visuelle, éventuellement complétée par un audit indépendant.

## Limites connues

- **Ce qui reste visible autour du visage :** la mosaïque couvre le visage, pas toute la tête. Sur une
  personne de profil, l'arrière du crâne et les cheveux restent visibles, ainsi que la silhouette
  du front et du nez au bord de la zone.
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
