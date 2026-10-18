#!/bin/sh
# Nightly Postgres dump with retention. Runs inside the backup container (postgres image).
set -eu
: "${RETENTION_DAYS:=30}"
: "${BACKUP_DIR:=/backups}"
mkdir -p "$BACKUP_DIR"
while true; do
  now=$(date +%Y%m%d-%H%M)
  if pg_dump -h db -U rasad rasad | gzip > "$BACKUP_DIR/rasad-$now.sql.gz"; then
    echo "backup written: rasad-$now.sql.gz"
  else
    echo "backup failed at $now" >&2
  fi
  find "$BACKUP_DIR" -name 'rasad-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
  sleep 86400
done
