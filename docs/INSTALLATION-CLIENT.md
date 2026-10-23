# Installer, mettre à jour et sauvegarder TMS Vision chez un client

Deux façons d'installer, au choix :

| | Docker (recommandée) | Sans Docker |
|---|---|---|
| Installation | 1 commande, identique partout | `./tms setup` (Python, Node, ffmpeg, Chromium) |
| HTTPS + mot de passe | inclus (Caddy) | à prévoir soi-même (proxy) |
| Démarrage automatique | inclus (`restart: unless-stopped`) | services systemd fournis (Linux) |
| Mise à jour | `git pull` + `docker compose up -d --build` | `git pull` + `./tms setup` + `./tms build` |

> **À savoir avant la première livraison.** Les fichiers Docker (`docker-compose.yml`, `deploy/`)
> ont été écrits et vérifiés pour leur syntaxe, mais n'ont pas pu être construits dans
> l'environnement où ils ont été rédigés (pas de démon Docker). **Faites un premier essai complet sur
> une de vos machines avant d'aller chez le client** : c'est la seule façon de le valider vraiment.

---

## 0. Raccourci : tout installer en une commande (Docker)

Avec accès à Internet, selon le système du client :

**Linux ou macOS** (terminal) :
```bash
curl -fsSL https://raw.githubusercontent.com/toussaintgarinat-crypto/tms-vision/main/install.sh | bash
```

**Windows 10/11** (PowerShell, administrateur inutile) :
```powershell
irm https://raw.githubusercontent.com/toussaintgarinat-crypto/tms-vision/main/install.ps1 | iex
```
Avec options : `& ([scriptblock]::Create((irm https://raw.githubusercontent.com/toussaintgarinat-crypto/tms-vision/main/install.ps1))) -WithVideos`
(`-NoStart`, `-Yes` existent aussi). Voir § 11 pour les particularités de Windows.

Le script installe Docker s'il manque (après confirmation), récupère le code dans `~/tms-vision`,
pose les questions utiles (adresse du site, identifiant, mot de passe, ou en génère un), crée le
`.env`, puis construit et lance tout. Options : `bash -s -- --with-videos` (génère aussi les vidéos
d'étirement), `--no-start` (prépare sans lancer), `--yes` (aucune question). Sans question, on peut
tout passer par variables : `TMS_DOMAIN=tms.client.fr TMS_USER=dr TMS_PASSWORD=... bash`. (Sous
macOS, Docker Desktop doit être installé avant : le script ne l'installe que sous Linux.)

**Relancer la même commande plus tard fait la mise à jour** : sauvegarde de `data/`, `git pull`,
reconstruction. Le `.env` et `data/` ne sont jamais écrasés.

Limites : le dépôt doit être **public** pour que l'adresse `raw.githubusercontent.com` réponde (sinon,
clonez avec une clé de déploiement, voir § 1, puis lancez `./install.sh` depuis le clone). Comme pour
les fichiers Docker, ce script a été testé avec un faux Docker, pas sur une vraie installation :
essayez-le d'abord sur une de vos machines. Lire un script avant de l'exécuter reste une bonne
habitude : <https://github.com/toussaintgarinat-crypto/tms-vision/blob/main/install.sh>.

---

## 1. Prérequis

### Le serveur du client
- Linux (Ubuntu 22.04/24.04 ou Debian 12 recommandés), 8 Go de RAM, 4 cœurs, 20 Go de disque libres.
  macOS et Windows 10/11 fonctionnent aussi, avec Docker Desktop (voir § 11 pour Windows). Windows Server
  n'est pas pris en charge par Docker Desktop.
- Un accès à Internet pour l'installation (téléchargement des images et des paquets). Ensuite, le
  fonctionnement courant n'en dépend plus (sauf HTTPS public et envoi d'emails).

### Pour un accès depuis d'autres appareils (téléphone, tablette, poste du praticien)
- **Un nom de domaine** (ex. `tms.cabinet-martin.fr`) qui pointe vers l'adresse IP du serveur, et les
  ports **80 et 443** ouverts vers ce serveur. Le certificat HTTPS est alors obtenu tout seul.
- HTTPS est **indispensable** : sans lui, le navigateur du téléphone refuse d'ouvrir la caméra.
- Sans nom de domaine (réseau local seulement) : utiliser l'adresse IP du serveur comme adresse du
  site. Le certificat est alors auto-signé : chaque appareil affichera un avertissement, à moins d'y
  installer le certificat racine (voir « Dépannage »).

### Logiciels
- **Git**, pour récupérer le code et les mises à jour.
- **Docker Engine + plugin Compose** (voie Docker) : <https://docs.docker.com/engine/install/>. Après
  l'installation, activer le démarrage au boot : `sudo systemctl enable --now docker`.
- **Accès au dépôt GitHub** `toussaintgarinat-crypto/tms-vision`. S'il est privé, créez sur le serveur
  une *clé de déploiement* en lecture seule :
  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/tms_deploy -N ""
  cat ~/.ssh/tms_deploy.pub     # à ajouter dans GitHub : Settings > Deploy keys (sans droit d'écriture)
  ```
  puis cloner avec `GIT_SSH_COMMAND="ssh -i ~/.ssh/tms_deploy" git clone git@github.com:toussaintgarinat-crypto/tms-vision.git`
  (et pour les mises à jour : `export GIT_SSH_COMMAND="ssh -i ~/.ssh/tms_deploy"` avant `git pull`).

---

## 2. Installation avec Docker

```bash
# 1. Récupérer le code
git clone https://github.com/toussaintgarinat-crypto/tms-vision.git
cd tms-vision

# 2. Créer la configuration
cp .env.example .env
```

**3. Remplir `.env`** (ouvrir avec `nano .env`) :

- `TMS_SITE_ADDRESS` : le nom de domaine du client, ex. `tms.cabinet-martin.fr`.
- `TMS_SITE_URL` : la même adresse précédée de `https://`, ex. `https://tms.cabinet-martin.fr`.
  Elle sert aux liens envoyés aux patients.
- `TMS_BASIC_AUTH_USER` : l'identifiant du praticien.
- `TMS_BASIC_AUTH_HASH` : le mot de passe **haché**. Le produire ainsi, puis coller le résultat
  **entre apostrophes** dans `.env` :
  ```bash
  docker run --rm caddy:2-alpine caddy hash-password --plaintext 'LeMotDePasseChoisi'
  ```
  Exemple de ligne obtenue : `TMS_BASIC_AUTH_HASH='$2a$14$Zkx...'`.
- `TMS_MAILER` : laisser `none` tant qu'aucun service d'email n'est branché (voir § 8).

```bash
# 4. Construire et lancer (la première fois : 10 à 20 minutes)
docker compose up -d --build

# 5. Vérifier que tout est « healthy »
docker compose ps

# 6. Générer les vidéos d'étirement (une fois, puis après chaque ajout d'exercice)
docker compose run --rm capsules              # tous les exercices
docker compose run --rm capsules --id neck-lateral-stretch   # un seul
```

Ouvrir `https://<adresse du site>` : le navigateur demande l'identifiant et le mot de passe.

**Ce qui est protégé par mot de passe et ce qui ne l'est pas.** Tout le site praticien (analyses,
bilans, historique, bibliothèque) demande le mot de passe. Seule la page que reçoit le patient
(`/bibliotheque/envoi/<jeton>`) est ouverte, ainsi que ses données : son adresse contient un jeton
aléatoire, et elle ne montre que les exercices choisis par le praticien.

**Où sont les données ?** Dans le dossier `data/` à côté de `docker-compose.yml` (base d'analyses
`tms_vision.duckdb` et vidéos d'exercice). Il n'est pas dans Git. C'est lui qu'il faut sauvegarder.

---

## 3. Mise à jour

À faire de préférence en fin de journée, quelques minutes d'interruption.

```bash
cd tms-vision

# 1. Sauvegarder d'abord
deploy/backup.sh

# 2. Récupérer la nouvelle version
git pull origin main        # ou : git fetch --tags && git checkout v1.2.0

# 3. Reconstruire et relancer (data/ et .env ne sont pas touchés)
docker compose up -d --build

# 4. Vérifier
docker compose ps           # tous « healthy »
docker compose logs --tail=50 api web

# 5. Régénérer les vidéos seulement si des exercices ont changé (inutile sinon : les vidéos à jour
#    ne sont pas refaites)
docker compose run --rm capsules

# 6. Nettoyer les anciennes images
docker image prune -f
```

**En cas de problème : revenir en arrière.**
```bash
git log --oneline -5                  # repérer la version précédente
git checkout <commit-ou-tag-précédent>
docker compose up -d --build
```
Si les données semblent abîmées : voir « Restaurer » au § 4. Les mises à jour de la base ne font
qu'ajouter des colonnes, un retour en arrière du code reste donc compatible avec la base.

> Conseil : posez une étiquette sur chaque version livrée (`git tag v1.0.0 && git push --tags`), pour
> savoir exactement ce qui tourne chez quel client et pouvoir y revenir.

---

## 4. Sauvegarde et restauration

### Sauvegarder
```bash
deploy/backup.sh                    # crée backups/tms-data-AAAA-MM-JJ_HHMMSS.tar.gz
deploy/backup.sh /mnt/disque-ext    # ou vers un autre dossier (TMS_BACKUP_DIR dans .env)
```
Les 14 dernières archives sont gardées (`TMS_BACKUP_KEEP` pour changer ce nombre).

**Sauvegarde automatique chaque nuit (cron)** :
```bash
crontab -e
# ajouter, en adaptant le chemin :
30 2 * * * /home/tms/tms-vision/deploy/backup.sh >> /home/tms/tms-vision/backups/backup.log 2>&1
```
**Copiez aussi les archives hors du serveur** (disque externe, NAS, autre machine) : une sauvegarde
sur le même disque ne protège pas d'une panne du disque. Ces archives contiennent les analyses des
salariés : à stocker avec le même soin que la base elle-même.

### Restaurer
```bash
docker compose stop api web                       # (sans Docker : ./tms stop)
deploy/restore.sh backups/tms-data-2026-10-23_023000.tar.gz
docker compose start api web
```
Le `data/` en place n'est pas détruit : il est renommé `data.avant-restauration-<date>`.

---

## 5. Démarrage automatique

- **Docker** : les services redémarrent seuls (`restart: unless-stopped`) à condition que Docker
  démarre au boot (`sudo systemctl enable docker`). Test : redémarrer le serveur, puis `docker compose ps`.
- **Sans Docker** : voir § 6.

Commandes courantes :
```bash
docker compose ps                  # état
docker compose logs -f api         # journal de l'API (idem : web, caddy)
docker compose restart api         # redémarrer un service
docker compose down                # tout arrêter (les données restent dans data/)
docker compose up -d               # tout relancer
```

---

## 6. Sans Docker (Linux, avec systemd)

```bash
# 1. Utilisateur et dossier
sudo useradd --system --create-home --shell /bin/bash tms
sudo git clone https://github.com/toussaintgarinat-crypto/tms-vision.git /opt/tms-vision
sudo chown -R tms:tms /opt/tms-vision

# 2. Installation (en tant que tms)
sudo -u tms -H bash -c 'cd /opt/tms-vision && ./tms setup'

# 3. Configuration
sudo -u tms cp /opt/tms-vision/.env.example /opt/tms-vision/.env
sudo -u tms nano /opt/tms-vision/.env      # renseigner TMS_PUBLIC_API_URL, TMS_PUBLIC_WEB_URL, TMS_MAILER…

# 4. Construire le site (l'adresse de l'API y est figée)
sudo -u tms -H bash -c 'cd /opt/tms-vision && ./tms build'

# 5. Vidéos d'étirement
sudo -u tms -H bash -c 'cd /opt/tms-vision && ./tms capsules'

# 6. Services (démarrage automatique) et sauvegarde nocturne
sudo cp /opt/tms-vision/deploy/systemd/tms-*.service /opt/tms-vision/deploy/systemd/tms-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tms-api tms-web tms-backup.timer
systemctl status tms-api tms-web
```

Dans ce mode, l'API (port 8000) et le site (port 3000) n'écoutent que sur la machine elle-même et
**il n'y a ni HTTPS ni mot de passe**. Placez devant un proxy qui les apporte (Caddy, nginx, Traefik :
`/api/*` vers le port 8000 avec le préfixe retiré, le reste vers le port 3000 ; reprendre
`deploy/Caddyfile` comme modèle), et réglez dans `.env` : `TMS_PUBLIC_API_URL=https://<site>/api`,
`ALLOWED_ORIGINS=https://<site>`, `TMS_PUBLIC_WEB_URL=https://<site>`.

**Mise à jour sans Docker :**
```bash
sudo -u tms -H bash -c 'cd /opt/tms-vision && ./tms backup && git pull origin main && ./tms setup && ./tms build'
sudo systemctl restart tms-api tms-web
sudo -u tms -H bash -c 'cd /opt/tms-vision && ./tms capsules'   # seulement si des exercices ont changé
```

---

## 7. Vérifications après une installation ou une mise à jour

- [ ] `https://<site>` demande le mot de passe, puis affiche l'application.
- [ ] Analyser une courte vidéo de test : le résultat s'affiche et apparaît dans l'historique.
- [ ] Bibliothèque : choisir une zone, voir les images, l'animation 3D, et la vidéo si elle existe.
- [ ] Envoyer des exercices à une adresse de test, ouvrir le lien **depuis un téléphone, sans être
      connecté** : la page patient s'affiche sans mot de passe.
- [ ] Sur le téléphone, la capture par caméra fonctionne (HTTPS valide).
- [ ] `deploy/backup.sh` crée bien une archive ; la copie hors serveur est en place.
- [ ] Après un redémarrage du serveur, tout revient seul.

---

## 8. Envoi d'emails aux patients

Par défaut (`TMS_MAILER=none`) **aucun email ne part** : l'écran affiche le lien à transmettre au
patient. Pour envoyer de vrais emails, il faut un petit module Python qui implémente l'interface
`Mailer` de `src/tms_vision/mailer.py` (par exemple via le SMTP du client), puis indiquer
`TMS_MAILER=module.chemin:Classe` dans `.env`. En Docker, le module doit être dans l'image (le placer
sous `src/` puis reconstruire). `TMS_SITE_URL` fixe l'adresse mise dans le lien.

---

## 9. Dépannage

| Symptôme | Piste |
|---|---|
| `docker compose up` refuse : « Renseignez … dans .env » | une variable obligatoire est vide : `TMS_SITE_URL`, `TMS_BASIC_AUTH_USER` ou `TMS_BASIC_AUTH_HASH`. |
| Mot de passe refusé | le hash doit être entre apostrophes dans `.env`. Le regénérer et vérifier qu'il commence par `$2a$`. |
| Pas de certificat HTTPS (domaine) | le nom doit pointer vers le serveur, ports 80 et 443 ouverts ; voir `docker compose logs caddy`. |
| Avertissement de certificat (adresse IP ou `localhost`) | normal : certificat local. Récupérer le certificat racine avec `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .` puis l'installer comme autorité de confiance sur l'appareil. |
| Le site s'ouvre mais « Impossible de charger la bibliothèque » | l'API n'est pas prête : `docker compose logs api`. |
| Le lien envoyé au patient pointe vers `localhost` | `TMS_SITE_URL` (ou `TMS_PUBLIC_WEB_URL` sans Docker) n'est pas réglé ; corriger puis `docker compose up -d`. |
| Génération des vidéos qui plante | mémoire insuffisante (prévoir 4 Go libres) ; relancer `docker compose run --rm capsules --id <exercice> --force`. |
| Plus de place sur le disque | `docker image prune -f`, et vider les anciennes archives de `backups/`. |
| Port 80/443 déjà pris | régler `TMS_HTTP_PORT` / `TMS_HTTPS_PORT` dans `.env`. |

---

## 10. À régler avec le client avant la mise en service

- **Contenu en brouillon.** Les rattachements zone → pathologie → exercices et les exercices marqués
  « brouillon » doivent être relus et validés par un professionnel de santé avant tout usage auprès
  de patients. L'application l'affiche à l'écran.
- **Données personnelles.** Le site traite des vidéos et des analyses de salariés (floutage des
  visages inclus). Vérifier avec le client les obligations RGPD (information des salariés, durée de
  conservation, lieu d'hébergement) et, si les données sont de santé, les exigences d'hébergement qui
  s'y appliquent. Ce document ne remplace pas un avis juridique.
- **Un seul compte.** Le mot de passe est partagé par tous les praticiens du site : il n'y a ni
  comptes individuels ni journal des accès.
- **Licence du modèle musculaire** (CC BY-SA 4.0, voir `NOTICE.md`) : vérifier les obligations avant
  une diffusion commerciale.

---

## 11. Windows 10/11 (Docker Desktop)

La voie recommandée sous Windows est la même que sous Linux (Docker) : l'application tourne dans des
conteneurs Linux, seuls les scripts d'installation et de sauvegarde ont leur version PowerShell.

**Prérequis**
- Windows 10 (22H2) ou 11, 64 bits, **virtualisation activée** dans le BIOS, 8 Go de RAM ou plus.
- **Docker Desktop** avec WSL2 : <https://docs.docker.com/desktop/setup/install/windows-install/>.
  `install.ps1` peut le télécharger via `winget` ; un redémarrage de Windows est alors souvent
  nécessaire, puis il faut **lancer Docker Desktop** une première fois (accepter ses conditions,
  attendre « Engine running ») avant de relancer la commande.
- **Git pour Windows** (`install.ps1` le propose via `winget` s'il manque) : <https://git-scm.com/download/win>.
- Pour sortir sur Internet : ports **80 et 443** libres sur le PC (IIS, Skype ou un autre serveur web
  les occupent parfois : sinon régler `TMS_HTTP_PORT` / `TMS_HTTPS_PORT` dans `.env`) et ouverts dans le
  pare-feu Windows et sur la box du client.

**Installation, mise à jour, sauvegarde**

| Action | Commande (PowerShell, dans le dossier `tms-vision`) |
|---|---|
| Installer / mettre à jour | `irm https://raw.githubusercontent.com/toussaintgarinat-crypto/tms-vision/main/install.ps1 \| iex` |
| Vidéos d'étirement | `docker compose run --rm capsules` |
| État, journaux | `docker compose ps` ; `docker compose logs --tail=50 api web` |
| Arrêter / relancer | `docker compose down` ; `docker compose up -d` |
| Sauvegarder `data\` | `.\deploy\backup.ps1` (ou `.\deploy\backup.ps1 D:\Sauvegardes`) |
| Restaurer | `docker compose stop api web` ; `.\deploy\restore.ps1 .\backups\tms-data-….tar.gz` ; `docker compose start api web` |

Si PowerShell refuse d'exécuter `.\deploy\backup.ps1` (« l'exécution de scripts est désactivée ») :
`powershell -ExecutionPolicy Bypass -File .\deploy\backup.ps1`, ou une fois pour toutes
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Les archives sont au même format que sous
Linux (`.tar.gz`) : on peut les restaurer d'un système à l'autre.

**Sauvegarde automatique chaque nuit** (Planificateur de tâches) :
```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\<nom>\tms-vision\deploy\backup.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 2:30am
Register-ScheduledTask -TaskName 'TMS Vision - sauvegarde' -Action $action -Trigger $trigger
```
Copier aussi les archives hors du PC (disque externe, NAS).

**Démarrage automatique.** Les services redémarrent seuls (`restart: unless-stopped`) **si Docker
Desktop est lancé**. Dans Docker Desktop : *Settings > General > Start Docker Desktop when you sign
in*. Le PC doit rester allumé et la session ouverte (ou le démarrage de Docker configuré en
conséquence) : sur un poste qui sert de serveur, désactiver la mise en veille.

**Mémoire.** Docker Desktop (WSL2) réserve par défaut la moitié de la RAM. Pour la génération des
vidéos, prévoir 4 à 6 Go : créer au besoin `%USERPROFILE%\.wslconfig` avec
```
[wsl2]
memory=6GB
```
puis `wsl --shutdown` et relancer Docker Desktop.

**Certificat local** (adresse `localhost` ou IP, sans nom de domaine) : récupérer le certificat racine
`docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .` puis, en PowerShell administrateur,
`certutil -addstore -f ROOT root.crt`, pour supprimer l'avertissement du navigateur sous Windows. Un
téléphone doit avoir ce certificat installé aussi pour ouvrir la caméra.

**Fins de ligne.** Le dépôt contient un `.gitattributes` qui force LF pour les fichiers lus par Linux
(Caddyfile, Dockerfiles, scripts). Ne le supprimez pas : des CRLF casseraient les conteneurs.

**Sans Docker.** La commande `./tms` et les unités systemd sont réservées à Linux/macOS. Sous Windows,
utiliser WSL2 (Ubuntu) et suivre le § 6 dans la distribution, ou, plus simplement, Docker Desktop.

> Comme le reste, les scripts PowerShell ont été testés avec PowerShell 7 sous Linux et un faux Docker
> (génération du `.env` sans BOM, mise à jour, sauvegarde et restauration), mais **pas sur un vrai
> Windows avec Docker Desktop** : essayez-les sur un PC de test avant de livrer.
