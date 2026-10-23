# Suivi des versions

## Principe

- **Un numéro** `MAJEUR.MINEUR.CORRECTIF` dans le fichier `VERSION` (ex. `1.2.0`).
  - CORRECTIF (`1.0.1`) : correction sans changement visible ;
  - MINEUR (`1.1.0`) : nouveauté compatible (nouveaux exercices, nouvelle page…) ;
  - MAJEUR (`2.0.0`) : la mise à jour demande une intervention (nouvelle variable dans `.env`,
    changement de format de données…), toujours expliquée dans `CHANGELOG.md`.
- **Un journal** `CHANGELOG.md` : ce qui change à chaque version, en français, pour le client.
- **Une étiquette Git** `v1.2.0` par version publiée : c'est elle qui permet d'installer ou de revenir
  à une version précise.
- **Affichage** : le numéro s'affiche en haut du site (« TMS Vision v1.2.0 ») et est donné par
  `GET /api/version` ; `./tms version` l'affiche aussi pour une installation sans Docker.
- **Journal côté client** : chaque installation ou mise à jour par `install.sh` / `install.ps1` ajoute
  une ligne à `.tms-updates.log` (date, version, commit, action), pour savoir ce qui a tourné quand.

## Publier une nouvelle version (côté développeur)

1. Faire les modifications et les commiter sur `main`.
2. Décrire les nouveautés dans `CHANGELOG.md`, sous `## [Non publié]` (listes sous « Ajouts »,
   « Corrections », « À savoir pour la mise à jour »…), puis commiter.
3. Publier :
   ```bash
   deploy/release.sh 1.1.0
   ```
   Le script vérifie que vous êtes sur `main`, sans modification en cours, que `1.1.0` est supérieur à la
   version actuelle et que le journal contient des nouveautés. Il met à jour `VERSION`, date l'entrée du
   journal, crée le commit « Version 1.1.0 » et l'étiquette `v1.1.0`. **Il ne pousse rien.**
4. Envoyer sur GitHub :
   ```bash
   git push origin main && git push origin v1.1.0
   ```
5. (Facultatif) Sur GitHub, *Releases > Draft a new release*, choisir l'étiquette `v1.1.0` et coller
   l'entrée du journal : les clients peuvent alors suivre les versions (« Watch > Releases »).

Les clients qui lancent la commande de mise à jour sans préciser de version reçoivent la dernière
version de `main` : ne poussez sur `main` que ce qui est prêt à être livré.

## Mettre à jour une installation (côté client ou technicien)

La même commande installe et met à jour. **Une sauvegarde de `data/` est faite automatiquement avant
toute mise à jour.**

| | Linux / macOS | Windows (PowerShell) |
|---|---|---|
| Voir s'il y a une mise à jour | `curl -fsSL …/install.sh \| bash -s -- --check` | `& ([scriptblock]::Create((irm …/install.ps1))) -Check` |
| Mettre à jour vers la dernière version | `curl -fsSL …/install.sh \| bash` | `irm …/install.ps1 \| iex` |
| Passer à une version précise | `curl -fsSL …/install.sh \| bash -s -- --version 1.0.0` | `& ([scriptblock]::Create((irm …/install.ps1))) -Version 1.0.0` |
| Depuis le dossier déjà installé | `./install.sh --check`, `./install.sh`, `./install.sh --version 1.0.0` | `.\\install.ps1 -Check`, `.\\install.ps1`, `.\\install.ps1 -Version 1.0.0` |

(`…` = `https://raw.githubusercontent.com/toussaintgarinat-crypto/tms-vision/main`.)

- **Revenir en arrière** : `--version <numéro précédent>` (ou `-Version`). Les mises à jour de la base de
  données n'ajoutent que des colonnes : un retour à une version antérieure reste compatible. En cas de
  doute, restaurer aussi la sauvegarde (`deploy/restore.*`, voir `docs/INSTALLATION-CLIENT.md`).
- **Quelle version tourne ?** En haut du site, ou `cat VERSION`, ou `cat .tms-updates.log`.
- **Versions publiées** : `git tag -l "v*"` dans le dossier installé, ou la page *Releases* du dépôt.

## Suivi des clients (modèle à tenir à jour)

| Client | Adresse du site | Version installée | Dernière mise à jour | Contact |
|---|---|---|---|---|
| (exemple) Cabinet Martin | https://tms.cabinet-martin.fr | 1.0.0 | 2026-10-23 | … |

Ce tableau est à tenir à jour de votre côté : le dépôt est public, n'y inscrivez pas vos vrais
clients. Un tableur ou votre outil de gestion suffit ; `.tms-updates.log` sur chaque machine donne
l'historique exact.
