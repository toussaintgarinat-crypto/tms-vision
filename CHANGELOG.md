# Journal des versions

Une entrée par version publiée, la plus récente en haut. Numérotation `MAJEUR.MINEUR.CORRECTIF`
(voir [`docs/VERSIONS.md`](docs/VERSIONS.md)) : le CORRECTIF pour une correction, le MINEUR pour une
nouveauté compatible, le MAJEUR quand une mise à jour demande une intervention (changement de
configuration, de format de données…). Le numéro installé s'affiche en haut du site, après « TMS Vision ».

Chaque version est aussi une étiquette Git (`v1.0.0`) : c'est ce qui permet d'installer ou de revenir à
une version précise.

## [Non publié]

## [1.1.0] - 2026-10-25

### Application de bureau (Windows et macOS)
- Installation par double-clic, sans Docker : `TMS-Vision-Setup.exe` (Windows) et `.dmg` (macOS Apple
  Silicon et Intel), fabriqués par GitHub (Actions > Application de bureau). Tout tourne sur le poste
  du praticien ; les données sont dans son dossier utilisateur et survivent aux mises à jour. Voir
  `docs/APPLICATION-BUREAU.md`. Les fichiers ne sont pas signés : un avertissement s'affiche au
  premier lancement. L'application signale une nouvelle version publiée sur GitHub (fenêtre et bandeau
  du site) sans jamais se mettre à jour seule ; hors ligne, elle ne dit rien.

### Logo
- Le logo de TMS Vision remplace l'icône par défaut : installateur, raccourcis, application Mac,
  petite fenêtre et onglet du navigateur.

### Compte rendu : animation 3D plus fluide
- En mode « Animation 3D », seuls les mannequins visibles à l'écran sont animés (les autres attendent
  qu'on arrive dessus) ; ils n'existent plus du tout dans les autres modes. Avant, tous les exercices
  du compte rendu chargeaient et animaient leur mannequin en même temps, ce qui ralentissait la page.

### Programme d'étirements : plus d'exercices, choix du praticien, explications
- Le nombre d'exercices est réglable (3, 5 ou 10 ; 5 par défaut, au lieu de 3 au maximum). Chaque zone
  sollicitée reçoit d'abord un exercice, puis un deuxième, etc., à partir du catalogue de la zone
  (exercices allongés exclus, variantes assises pour un poste assis). Le nombre choisi est enregistré
  pour chaque bilan, et aussi réglable sur la page d'une analyse.
- Sur un bilan, le praticien peut retirer un exercice, en ajouter un autre du catalogue ou revenir au
  programme automatique. Sa sélection est enregistrée avec le bilan et reprise dans le compte rendu.
- Une icône ⓘ à côté de chaque exercice explique pourquoi il est proposé (survol, clic ou clavier) :
  les tâches du poste qui sollicitent la zone (durée, poste, gestes par minute, maintien, charge), ce
  que l'exercice apporte (nouveau champ `benefit` dans `exercises/`, écrit pour les 95 exercices, en
  brouillon : à relire par l'ostéopathe) et ce qu'il fait travailler. Sans tâche saisie, la bulle le dit.
- API : `GET /bilans/{id}/program?size=` et `GET /analyses/{id}/recommendation?size=` ; réglages
  enregistrés avec `PUT /bilans/{id}/program`. Les bases existantes sont mises à niveau automatiquement.

### Bibliothèque de métiers et copie de bilan
- Bibliothèque classée par domaine d'activité (Terrain et BTP, Industrie et logistique, Alimentaire
  et commerce, Santé et soins, Tertiaire et autres), avec des raccourcis en haut de page, et 17 métiers
  de plus (27 au total) : maçon, carreleur, électricien, plombier-chauffagiste, couvreur, soudeur,
  boulanger-pâtissier, boucher-charcutier, employé libre-service, infirmier, kinésithérapeute,
  chirurgien-dentiste, ostéopathe, téléconseiller, développeur ou graphiste, mécanicien, agriculteur ou
  viticulteur. Tous en brouillon, à relire par un professionnel de santé. Chaque fichier de
  `metiers/` porte désormais un champ `domain`.
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
- Dossiers de bilans, sur autant de niveaux que nécessaire (entreprise > service > poste) : création
  de dossiers et de sous-dossiers, renommage, rangement des bilans et des dossiers par glisser-déposer
  ou par la liste de leur ligne, choix du dossier sur la page d'un bilan (chemin complet affiché).
  Disponible dans « Bilans » comme dans « Archives » (dossiers communs). Un dossier ne peut pas être
  placé dans lui-même ni dans l'un de ses sous-dossiers. Supprimer un dossier ne supprime rien : ses
  bilans et ses sous-dossiers montent d'un niveau. Une copie de bilan reste dans le dossier d'origine.
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
