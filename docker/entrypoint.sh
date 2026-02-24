#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$(dirname "${SIM_DB_PATH:-/data/openprotocol.db}")"
mkdir -p /data

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf

