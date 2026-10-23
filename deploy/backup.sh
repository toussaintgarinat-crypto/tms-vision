#!/usr/bin/env bash
# Sauvegarde du dossier data/ (base d'analyses DuckDB + vidéos d'exercice) dans une archive datée.
#
#   deploy/backup.sh [dossier-de-destination]     (défaut : ./backups, ou TMS_BACKUP_DIR)
#
# Les 14 dernières archives sont conservées (TMS_BACKUP_KEEP pour changer). Le site ouvre la base
# le temps de chaque requête seulement : lancer la sauvegarde la nuit (voir docs/INSTALLATION-CLIENT.md)
# ou site arrêté pour une copie parfaitement cohérente. Penser à copier aussi les archives HORS du
# serveur (disque externe, autre machine) : une sauvegarde sur le même disque ne protège pas d'une panne.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ -f .env ] && { set -a; . ./.env; set +a; }

DEST="${1:-${TMS_BACKUP_DIR:-$ROOT/backups}}"
KEEP="${TMS_BACKUP_KEEP:-14}"

[ -d data ] || { echo "Aucun dossier data/ à sauvegarder dans $ROOT." >&2; exit 1; }
mkdir -p "$DEST"

ARCHIVE="$DEST/tms-data-$(date +%Y-%m-%d_%H%M%S).tar.gz"
tar -czf "$ARCHIVE.tmp" -C "$ROOT" data
tar -tzf "$ARCHIVE.tmp" >/dev/null   # l'archive doit se relire en entier
mv "$ARCHIVE.tmp" "$ARCHIVE"
echo "Sauvegarde créée : $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# Rotation : on ne garde que les $KEEP plus récentes.
ls -1t "$DEST"/tms-data-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f -- "$old" && echo "Ancienne sauvegarde supprimée : $old"
done
