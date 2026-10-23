#!/usr/bin/env bash
# Installation ou mise à jour de TMS Vision (version Docker) en une commande :
#
#   curl -fsSL https://raw.githubusercontent.com/toussaintgarinat-crypto/tms-vision/main/install.sh | bash
#
# Options (après « bash -s -- ») :  --with-videos   génère aussi les vidéos d'étirement (long)
#                                   --no-start      prépare tout sans lancer les services
#                                   --yes           ne pose aucune question (Docker installé sans demander)
#                                   --version X     installe/met à jour vers la version X (ex. 1.2.0) au lieu de la dernière
#                                   --check         dit seulement si une mise à jour est disponible, sans rien modifier
# Variables : TMS_VERSION (comme --version), TMS_DIR (dossier, défaut ~/tms-vision), TMS_REPO (adresse Git du dépôt),
#             TMS_DOMAIN, TMS_USER, TMS_PASSWORD (évitent les questions).
#
# Relançable sans risque : si l'installation existe déjà, c'est une MISE À JOUR (sauvegarde de data/,
# git pull, reconstruction) ; le .env et data/ ne sont jamais écrasés.
set -euo pipefail

REPO="${TMS_REPO:-https://github.com/toussaintgarinat-crypto/tms-vision.git}"
DIR="${TMS_DIR:-$HOME/tms-vision}"
WITH_VIDEOS=0; NO_START=0; ASSUME_YES=0; CHECK=0; TARGET="${TMS_VERSION:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --with-videos) WITH_VIDEOS=1 ;;
    --no-start) NO_START=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --check) CHECK=1 ;;
    --version) shift; TARGET="${1:-}"; [ -n "$TARGET" ] || { echo "--version attend un numéro (ex. 1.2.0)" >&2; exit 1; } ;;
    *) echo "Option inconnue : $1" >&2; exit 1 ;;
  esac
  shift
done
[ -z "$TARGET" ] || TARGET="v${TARGET#v}"   # 1.2.0 et v1.2.0 sont acceptés

if [ -t 1 ]; then GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'; else GREEN=; RED=; YELLOW=; BOLD=; RESET=; fi
ok()   { echo "${GREEN}✔${RESET} $*"; }
warn() { echo "${YELLOW}!${RESET} $*"; }
die()  { echo "${RED}✘${RESET} $*" >&2; exit 1; }
step() { echo; echo "${BOLD}== $* ==${RESET}"; }

# Sous « curl | bash », l'entrée standard est le script lui-même : les réponses viennent du terminal.
TTY=""; [ -r /dev/tty ] && TTY=/dev/tty
ask() {  # ask <question> <défaut>  -> réponse sur la sortie standard
  local answer=""
  if [ "$ASSUME_YES" = "0" ] && [ -n "$TTY" ]; then
    read -r -p "$1 [$2] : " answer < "$TTY" || true
  fi
  echo "${answer:-$2}"
}
confirm() {  # confirm <question>  -> 0 si oui
  [ "$ASSUME_YES" = "1" ] && return 0
  [ -n "$TTY" ] || return 1
  local answer; read -r -p "$1 [o/N] : " answer < "$TTY" || true
  [[ "$answer" =~ ^[oOyY] ]]
}

SUDO=""; if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

# --- Prérequis ---------------------------------------------------------------------------------
step "Prérequis"
[ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ] || die "Système non pris en charge (Linux ou macOS). Sous Windows, utilisez WSL2."

if ! command -v git >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update -qq && $SUDO apt-get install -y git; fi
  command -v git >/dev/null 2>&1 || die "Git est requis : installez-le puis relancez."
fi
ok "Git $(git --version | cut -d' ' -f3)"

if ! command -v docker >/dev/null 2>&1; then
  [ "$(uname -s)" = "Linux" ] || die "Docker Desktop est requis : https://docs.docker.com/desktop/ — installez-le puis relancez."
  warn "Docker n'est pas installé."
  confirm "Installer Docker avec le script officiel (https://get.docker.com) ?" \
    || die "Docker est requis : https://docs.docker.com/engine/install/ — installez-le puis relancez."
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO systemctl enable --now docker 2>/dev/null || true
fi
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  if $SUDO docker info >/dev/null 2>&1; then DOCKER="$SUDO docker"; else die "Le démon Docker ne répond pas (lancé ? droits ?)."; fi
fi
$DOCKER compose version >/dev/null 2>&1 || die "Le plugin « docker compose » manque : https://docs.docker.com/compose/install/"
ok "Docker $($DOCKER --version | sed 's/Docker version //; s/,.*//')"

# --- Code --------------------------------------------------------------------------------------
step "Code"
UPDATE=0
if [ -d "$DIR/.git" ]; then
  UPDATE=1
  CURRENT_VERSION="$(cat "$DIR/VERSION" 2>/dev/null || echo inconnue)"
  CURRENT_COMMIT="$(git -C "$DIR" rev-parse HEAD)"
  git -C "$DIR" fetch --tags --quiet origin main || die "Impossible de joindre le dépôt (Internet ? dépôt privé ?)."
  if [ -n "$TARGET" ]; then
    git -C "$DIR" rev-parse -q --verify "refs/tags/$TARGET" >/dev/null \
      || die "Version $TARGET introuvable. Versions publiées : $(git -C "$DIR" tag -l 'v*' | sort -V | tr '\n' ' ')"
    REF="refs/tags/$TARGET"
  else
    REF="origin/main"
  fi
  NEW_VERSION="$(git -C "$DIR" show "$REF:VERSION" 2>/dev/null || echo inconnue)"
  NEW_COMMIT="$(git -C "$DIR" rev-parse "$REF^{commit}")"
  ok "Installée : version $CURRENT_VERSION ($(git -C "$DIR" rev-parse --short HEAD)) ; cible : version $NEW_VERSION ($(git -C "$DIR" rev-parse --short "$REF^{commit}"))"
  if [ "$CHECK" = "1" ]; then
    if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then ok "À jour."; else
      warn "Mise à jour disponible : $CURRENT_VERSION -> $NEW_VERSION. Nouveautés :"
      git -C "$DIR" log --format='  - %s' "$CURRENT_COMMIT..$NEW_COMMIT" 2>/dev/null | head -20 || true
      echo "Pour l'appliquer : relancer cette commande sans --check."
    fi
    exit 0
  fi
  if [ -n "$(git -C "$DIR" status --porcelain --untracked-files=no)" ]; then
    die "Des fichiers du dépôt ont été modifiés dans $DIR : annulez-les (git -C $DIR status) avant la mise à jour."
  fi
  if [ -d "$DIR/data" ]; then (cd "$DIR" && deploy/backup.sh) || warn "Sauvegarde impossible (on continue)."; fi
  if [ -n "$TARGET" ]; then
    git -C "$DIR" checkout --quiet "$TARGET" || die "Passage à la version $TARGET impossible."
  else
    git -C "$DIR" checkout --quiet main && git -C "$DIR" merge --ff-only --quiet origin/main || die "Mise à jour impossible (voir docs/INSTALLATION-CLIENT.md)."
  fi
  ok "Code en version $(cat "$DIR/VERSION" 2>/dev/null || echo inconnue)"
else
  [ "$CHECK" = "0" ] || die "Aucune installation dans $DIR : rien à vérifier."
  [ ! -e "$DIR" ] || [ -z "$(ls -A "$DIR" 2>/dev/null)" ] || die "$DIR existe et n'est pas vide : choisissez un autre dossier (TMS_DIR=...)."
  git clone "$REPO" "$DIR" || die "Clonage impossible. Dépôt privé ? Voir « Accès au dépôt GitHub » dans docs/INSTALLATION-CLIENT.md."
  if [ -n "$TARGET" ]; then
    git -C "$DIR" checkout --quiet "$TARGET" || die "Version $TARGET introuvable. Versions publiées : $(git -C "$DIR" tag -l 'v*' | sort -V | tr '\n' ' ')"
  fi
  ok "Code récupéré dans $DIR (version $(cat "$DIR/VERSION" 2>/dev/null || echo inconnue))"
fi
cd "$DIR"

# --- Configuration (.env) ----------------------------------------------------------------------
step "Configuration"
if [ -f .env ]; then
  ok ".env déjà présent : conservé tel quel"
else
  DOMAIN="${TMS_DOMAIN:-$(ask "Adresse du site (nom de domaine, ou localhost pour un essai)" "localhost")}"
  USER_NAME="${TMS_USER:-$(ask "Identifiant du praticien" "praticien")}"
  PASSWORD="${TMS_PASSWORD:-}"
  GENERATED=0
  if [ -z "$PASSWORD" ] && [ "$ASSUME_YES" = "0" ] && [ -n "$TTY" ]; then
    read -r -s -p "Mot de passe du praticien (vide = en générer un) : " PASSWORD < "$TTY" || true; echo
  fi
  if [ -z "$PASSWORD" ]; then
    PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)"; GENERATED=1
  fi
  [[ "$PASSWORD" != *\'* ]] || die "Le mot de passe ne doit pas contenir d'apostrophe."
  HASH="$($DOCKER run --rm caddy:2-alpine caddy hash-password --plaintext "$PASSWORD")" \
    || die "Impossible de hacher le mot de passe (image caddy:2-alpine non téléchargeable ?)."
  [[ "$HASH" == \$2* ]] || die "Hash inattendu produit par Caddy : $HASH"

  SCHEME="https"
  SITE_URL="$SCHEME://$DOMAIN"
  sed -e "s|^TMS_SITE_ADDRESS=.*|TMS_SITE_ADDRESS=$DOMAIN|" \
      -e "s|^TMS_SITE_URL=.*|TMS_SITE_URL=$SITE_URL|" \
      -e "s|^TMS_BASIC_AUTH_USER=.*|TMS_BASIC_AUTH_USER=$USER_NAME|" \
      .env.example > .env
  # Le hash contient des « $ » : écrit à part, entre apostrophes, sans interprétation par sed.
  { grep -v '^TMS_BASIC_AUTH_HASH=' .env; echo "TMS_BASIC_AUTH_HASH='$HASH'"; } > .env.tmp && mv .env.tmp .env
  chmod 600 .env
  ok ".env créé (site : $SITE_URL, identifiant : $USER_NAME)"
  if [ "$GENERATED" = "1" ]; then
    echo
    echo "${BOLD}Mot de passe généré : $PASSWORD${RESET}"
    echo "Notez-le maintenant : il n'est pas conservé en clair (seul son hash est dans .env)."
  fi
fi

[ "$NO_START" = "0" ] || { echo; ok "Préparation terminée (--no-start). Lancer avec : cd $DIR && docker compose up -d --build"; exit 0; }

# --- Lancement ---------------------------------------------------------------------------------
step "Construction et lancement (première fois : 10 à 20 minutes)"
$DOCKER compose up -d --build

echo "Attente que les services soient prêts…"
for _ in $(seq 1 60); do
  if [ -z "$($DOCKER compose ps --format '{{.Health}}' | grep -vx 'healthy' | grep -v '^$' || true)" ]; then break; fi
  sleep 5
done
$DOCKER compose ps

if [ "$WITH_VIDEOS" = "1" ]; then
  step "Vidéos d'étirement"
  $DOCKER compose run --rm capsules
fi

SITE="$(grep '^TMS_SITE_URL=' .env | cut -d= -f2-)"
# Journal des versions installées sur cette machine (date | version | commit | action).
echo "$(date '+%Y-%m-%d %H:%M:%S') | $(cat VERSION 2>/dev/null || echo inconnue) | $(git rev-parse --short HEAD) | $([ "$UPDATE" = "1" ] && echo mise-a-jour || echo installation)" >> .tms-updates.log
echo
VERSION_NOW="$(cat VERSION 2>/dev/null || echo inconnue)"
if [ "$UPDATE" = "1" ]; then ok "${BOLD}Mise à jour terminée : version $VERSION_NOW.${RESET}"; else ok "${BOLD}Installation terminée : version $VERSION_NOW.${RESET}"; fi
echo "Site : $SITE"
[ "$WITH_VIDEOS" = "1" ] || echo "Vidéos d'étirement (à faire une fois) : cd $DIR && docker compose run --rm capsules"
echo "Sauvegarde : cd $DIR && deploy/backup.sh      Guide complet : $DIR/docs/INSTALLATION-CLIENT.md"
