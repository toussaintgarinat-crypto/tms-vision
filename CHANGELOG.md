# Journal des versions

Une entrée par version publiée, la plus récente en haut. Numérotation `MAJEUR.MINEUR.CORRECTIF`
(voir [`docs/VERSIONS.md`](docs/VERSIONS.md)) : le CORRECTIF pour une correction, le MINEUR pour une
nouveauté compatible, le MAJEUR quand une mise à jour demande une intervention (changement de
configuration, de format de données…). Le numéro installé s'affiche en haut du site, après « TMS Vision ».

Chaque version est aussi une étiquette Git (`v1.0.0`) : c'est ce qui permet d'installer ou de revenir à
une version précise.

## [Non publié]

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
