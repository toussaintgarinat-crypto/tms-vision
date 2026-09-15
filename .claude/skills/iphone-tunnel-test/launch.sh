#!/usr/bin/env bash
# Lance les 4 processus nécessaires pour tester la capture web TMS Vision
# depuis un appareil externe (iPhone, etc.) via tunnel HTTPS cloudflared :
# tunnel API, tunnel frontend, API FastAPI (ALLOWED_ORIGINS = URL du tunnel
# frontend), frontend Next.js (NEXT_PUBLIC_API_URL = URL du tunnel API).
#
# Usage : ./launch.sh   (depuis n'importe où dans le repo TMS vision)
# Arrêt : Ctrl+C — tue les 4 processus.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Erreur : cloudflared introuvable. Installer avec 'brew install cloudflared'." >&2
  exit 1
fi

LOG_DIR="$(mktemp -d)"
API_TUNNEL_LOG="$LOG_DIR/api-tunnel.log"
WEB_TUNNEL_LOG="$LOG_DIR/web-tunnel.log"

PIDS=()

cleanup() {
  echo ""
  echo "Arrêt des processus..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  # `npm run dev` (next dev) lance un processus enfant (next-server) qui ne
  # reçoit pas le signal envoyé au seul PID du sous-shell ci-dessus -- on le
  # cible explicitement en plus, sinon il continue à tourner après Ctrl+C.
  pkill -f "next-server \(v" >/dev/null 2>&1 || true
  pkill -f "node .*next dev" >/dev/null 2>&1 || true
  rm -rf "$LOG_DIR"
}
trap cleanup EXIT INT TERM

extract_url() {
  local log_file="$1"
  local timeout=30
  local elapsed=0
  local url=""
  while [ "$elapsed" -lt "$timeout" ]; do
    url=$(grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$log_file" 2>/dev/null | head -1 || true)
    if [ -n "$url" ]; then
      echo "$url"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  echo "Erreur : URL de tunnel non trouvée dans $log_file après ${timeout}s" >&2
  return 1
}

echo "Démarrage du tunnel API (port 8000)..."
cloudflared tunnel --url http://localhost:8000 > "$API_TUNNEL_LOG" 2>&1 &
PIDS+=("$!")

echo "Démarrage du tunnel Web (port 3000)..."
cloudflared tunnel --url http://localhost:3000 > "$WEB_TUNNEL_LOG" 2>&1 &
PIDS+=("$!")

echo "Attente des URLs de tunnel (jusqu'à 30s)..."
URL_API="$(extract_url "$API_TUNNEL_LOG")"
URL_WEB="$(extract_url "$WEB_TUNNEL_LOG")"

echo "  URL API : $URL_API"
echo "  URL Web : $URL_WEB"

echo "Démarrage de l'API FastAPI (port 8000)..."
ALLOWED_ORIGINS="$URL_WEB" PYTHONPATH=src venv/bin/uvicorn tms_vision.api:app --port 8000 &
PIDS+=("$!")

echo "Démarrage du frontend Next.js (port 3000)..."
(cd web && NEXT_PUBLIC_API_URL="$URL_API" npm run dev) &
PIDS+=("$!")

echo ""
echo "=========================================="
echo " Ouvre cette URL sur ton iPhone (Safari) :"
echo " $URL_WEB"
echo "=========================================="
echo ""
echo "Ctrl+C pour tout arrêter."

wait
