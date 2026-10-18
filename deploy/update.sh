#!/usr/bin/env bash
# Deploy a new version: copy the repo over, rebuild, restart. Data and .env are untouched.
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/rasad}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  rsync -a --delete --exclude node_modules --exclude .git --exclude '*.db' --exclude .env "$SRC_DIR/" "$APP_DIR/"
fi
cd "$APP_DIR"
docker compose up -d --build
docker compose ps
