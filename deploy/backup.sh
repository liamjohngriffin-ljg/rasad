#!/bin/sh
# Nightly Postgres dump with retention. Runs inside the backup container (postgres image).
set -eu
umask 077  # dumps hold the whole database: readable by the owner only
: "${RETENTION_DAYS:=30}"
: "${BACKUP_DIR:=/backups}"
mkdir -p "$BACKUP_DIR"
chmod 600 "$BACKUP_DIR"/*.sql.gz 2>/dev/null || true  # dumps written before 0.4.0 were world-readable
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
