# Journal des versions

Une entrée par version publiée, la plus récente en haut. Numérotation `MAJEUR.MINEUR.CORRECTIF`
(voir [`docs/VERSIONS.md`](docs/VERSIONS.md)) : le CORRECTIF pour une correction, le MINEUR pour une
nouveauté compatible, le MAJEUR quand une mise à jour demande une intervention (changement de
configuration, de format de données…). Le numéro installé s'affiche en haut du site, après « TMS Vision ».

Chaque version est aussi une étiquette Git (`v1.0.0`) : c'est ce qui permet d'installer ou de revenir à
une version précise.

## [Non publié]

### Bibliothèque de métiers et copie de bilan
- Page « Bibliothèque de métiers » (dossier `metiers/`) : 10 métiers avec leurs fiches d'activité
  types (bureau, caisse, logistique, assemblage, conduite, soins, coiffure, cuisine, peinture,
  entretien). Un bouton crée un bilan prérempli, nommé d'après la personne, à adapter. Les modèles
  sont en brouillon (écrits par l'IA) : à relire et valider par un professionnel de santé.
- Bilans de poste : « Dupliquer ce bilan » pour reprendre un bilan avec une autre personne (fiches
  d'activité et durée de la journée copiées, vidéos non copiées) et « Enregistrer comme modèle de
  métier » pour garder un bilan réussi dans la bibliothèque (« Mes modèles »).
- Programme d'étirements sans vidéo : un bilan sans analyse vidéo (par exemple créé depuis un métier)
  propose désormais jusqu'à 3 exercices d'après les zones des tâches saisies, classées par durée de
  tâches qui les sollicitent, avec le badge « Sans vidéo ». Les zones mesurées sur vidéo passent
  toujours en premier. Aucun score de risque n'est inventé : sans mesure, seules les durées comptent.
- Bilans de poste : onglets « Bilans » et « Archives » dans la liste, pour ranger un bilan sans le
  perdre (Archiver, Restaurer) ou le supprimer définitivement (avec confirmation). Les mêmes actions
  sont sur la page d'un bilan. Les vidéos analysées ne sont jamais supprimées avec le bilan. Les
  bases existantes sont mises à niveau automatiquement.
- Correction : la suppression d'une fiche d'activité depuis le site était refusée par l'API
  (méthode DELETE absente de la configuration CORS).

### Assistant vocal (facultatif, éteint par défaut)
- Écoute le praticien et pré-remplit la fiche d'activité (dictée libre ou questions guidées, lecture
  à voix haute en option) ; n'enregistre jamais, les champs remplis sont surlignés pour relecture.
- Désactivé au départ ; le praticien l'active ou le désactive lui-même par un interrupteur dans la
  roue ⚙ du bandeau (aucune variable d'environnement).
- Réglage depuis le site, par la roue ⚙ du bandeau : fournisseur d'IA (Ollama, LM Studio, llama.cpp,
  OpenRouter, OpenAI, DeepSeek ou tout serveur compatible OpenAI), adresse et modèle (liste
  déroulante chargée automatiquement). Les clés restent dans le fichier `.env`, jamais enregistrées
  par le site. Écoute par le navigateur ou transcription souveraine (Workplace). Voir
  `docs/INSTALLATION-CLIENT.md` § 12.
- Variables facultatives : `TMS_ASSISTANT_LLM_KEY` et `TMS_TRANSCRIPTION_KEY` (clés, dans `.env`) ;
  `TMS_ASSISTANT_LLM_URL`, `TMS_ASSISTANT_MODEL`, `TMS_TRANSCRIPTION_URL` (valeurs
  par défaut).

## [1.0.0] - 2026-10-23

Première version livrable.

### Analyse ergonomique
- Analyse RULA d'une vidéo (enregistrée dans le navigateur ou importée, par morceaux), pose 3D,
  avatar musculaire du corps entier coloré par segment, mesure de la main et du pied.
- Floutage des visages de la vidéo annotée ; purge des envois abandonnés (vidéo brute).
- Stockage des analyses dans une base DuckDB ; historique avec filtres et page de détail ;
  lecture des vidéos avec requêtes Range.
- Poids manipulé (précis ou en fourchette) avec recalcul des scores.

### Bilan de poste
- Récurrence par zone, projection sur la journée, fiche d'activité (tâches, fréquences, pauses,
  poste de travail), rapport.
- Comptes rendus anonymes : carrousels d'images, animation 3D ou vidéo ; export PDF (impression) ou
  fichier HTML autonome.

### Exercices d'étirement et bibliothèque
- Catalogue d'exercices définis en fichiers validés (position debout, assise ou allongée) ; exercices
  en brouillon signalés, à valider par un professionnel de santé.
- Programme d'étirements recommandé selon les zones à risque et la charge ; génération des vidéos
  (`./tms capsules`) ou lecture en direct dans le navigateur.
- Bibliothèque par zone du corps et pathologie (≈ 77 exercices), choix du format d'affichage
  (images, animation 3D, vidéo) et envoi au patient par lien (page patient sans mot de passe).

### Installation et exploitation
- `./tms` pour installer, lancer et tester sans Docker ; mode production (`./tms build`, `start --prod`).
- Installation Docker avec HTTPS automatique et mot de passe (Caddy) ; `install.sh` (Linux, macOS) et
  `install.ps1` (Windows) pour installer et mettre à jour en une commande, avec choix de la version.
- Sauvegarde et restauration de `data/` (`deploy/backup.*`, `deploy/restore.*`) ; unités systemd.
- Numéro de version affiché dans l'application (`GET /version`).
