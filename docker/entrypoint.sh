#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$(dirname "${SIM_DB_PATH:-/data/openprotocol.db}")"
mkdir -p /data

HOST="${HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-8080}"

echo "[startup] Simulator backend binding on ${HOST}:${API_PORT}"
echo "[startup] UI server binding on 0.0.0.0:${UI_PORT}"
echo "[startup] UI should be reachable at:"

{
  echo "127.0.0.1"
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | tr ' ' '\n'
  fi
  if command -v ip >/dev/null 2>&1; then
    ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1
  fi
} | awk 'NF' | sort -u | while read -r ip_addr; do
  echo "  - http://${ip_addr}:${UI_PORT}"
done

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
