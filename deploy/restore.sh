#!/usr/bin/env bash
# Restore a nightly dump into the running stack. Stops the API and scheduler, replaces the database,
# starts them again. The current database is dumped first, so a restore can itself be undone.
#   sudo bash deploy/restore.sh                      # newest backup
#   sudo bash deploy/restore.sh rasad-20261019-0602.sql.gz
set -euo pipefail
APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
file="${1:-}"
if [ -z "$file" ]; then
  file=$(docker compose exec -T backup sh -c 'ls -1t /backups/rasad-*.sql.gz 2>/dev/null | head -1' | tr -d '\r')
  file=$(basename "$file")
fi
[ -n "$file" ] || { echo "no backups found"; exit 1; }
docker compose exec -T backup test -f "/backups/$file" || { echo "/backups/$file not found"; exit 1; }
echo "== Restoring $file"
stamp=$(date +%Y%m%d-%H%M%S)
echo "== Safety dump of the current database: pre-restore-$stamp.sql.gz"
docker compose exec -T backup sh -c "pg_dump -h db -U rasad rasad | gzip > /backups/pre-restore-$stamp.sql.gz"
docker compose stop api scheduler
docker compose exec -T backup sh -c "psql -h db -U rasad -d postgres -v ON_ERROR_STOP=1 -c 'DROP DATABASE IF EXISTS rasad WITH (FORCE)' -c 'CREATE DATABASE rasad OWNER rasad'"
docker compose exec -T backup sh -c "gunzip -c /backups/$file | psql -h db -U rasad -d rasad -v ON_ERROR_STOP=1 -q"
docker compose start api scheduler
echo "== Restored. Check with: docker compose exec api python -m rasad.doctor"
