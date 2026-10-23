#!/usr/bin/env bash
# Restaure data/ depuis une archive créée par deploy/backup.sh.
#
#   deploy/restore.sh <archive.tar.gz>
#
# Arrêtez le site avant (docker compose stop api, ou ./tms stop). Le data/ actuel n'est pas détruit :
# il est mis de côté sous le nom data.avant-restauration-<date>.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ARCHIVE="${1:-}"
[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || { echo "Usage : deploy/restore.sh <archive.tar.gz>" >&2; exit 1; }
# Liste d'abord capturée : « grep -q » ferme le tube dès qu'il trouve et ferait échouer tar (pipefail).
LISTING="$(tar -tzf "$ARCHIVE")" || { echo "Archive illisible : $ARCHIVE" >&2; exit 1; }
[[ "$LISTING" == data/* ]] || { echo "Cette archive ne contient pas de dossier data/." >&2; exit 1; }

if [ -d data ]; then
  ASIDE="data.avant-restauration-$(date +%Y%m%d_%H%M%S)"
  mv data "$ASIDE"
  echo "data/ actuel mis de côté : $ASIDE"
fi
tar -xzf "$ARCHIVE" -C "$ROOT"
echo "Restauration terminée depuis $ARCHIVE. Relancez le site."
