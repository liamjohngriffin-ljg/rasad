#!/usr/bin/env bash
# One-shot install on a fresh Ubuntu 22.04 or 24.04 server (Hetzner or similar).
#   curl -fsSL <raw url>/deploy/install.sh | sudo bash -s -- <domain or blank>
# or, from an unpacked copy of the repo:  sudo bash deploy/install.sh rasad.example.com
set -euo pipefail

DOMAIN="${1:-}"
APP_DIR="${APP_DIR:-/opt/rasad}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "$(id -u)" -ne 0 ]; then echo "run as root (sudo)"; exit 1; fi

echo "== Docker"
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

echo "== Firewall"
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null || true
  if [ -n "$DOMAIN" ]; then
    ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
    echo "   ssh, http (redirects to https) and https open"
  else
    # no domain means no certificate: plain HTTP would carry passwords and session cookies in the
    # clear, so the web ports stay closed and the platform is reached through an SSH tunnel
    echo "   ssh only; reach the platform with:  ssh -L 8080:localhost:80 <user>@<this server>  then http://localhost:8080"
  fi
  ufw --force enable >/dev/null
fi

echo "== Copying to $APP_DIR"
mkdir -p "$APP_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  rsync -a --delete --exclude node_modules --exclude .git --exclude '*.db' --exclude .env "$SRC_DIR/" "$APP_DIR/"
fi
cd "$APP_DIR"

if [ ! -f .env ]; then
  echo "== Writing .env"
  cp .env.example .env
  sed -i "s/^RASAD_DB_PASSWORD=.*/RASAD_DB_PASSWORD=$(openssl rand -hex 24)/" .env
  sed -i "s/^RASAD_SECRET=.*/RASAD_SECRET=$(openssl rand -hex 32)/" .env
  sed -i "s/^DOMAIN=.*/DOMAIN=$DOMAIN/" .env
  if [ -z "$DOMAIN" ]; then echo "RASAD_BIND=127.0.0.1" >> .env; fi
  chmod 600 .env
fi

echo "== Building and starting"
docker compose up -d --build
echo "== Seeding demo data (first run only)"
docker compose --profile seed run --rm seed

echo
echo "Rasad is up."
if [ -n "$DOMAIN" ]; then
  echo "  URL: https://$DOMAIN   (certificate is issued on first visit; allow a minute)"
else
  echo "  No domain, so the platform listens on this server only. From your machine:"
  echo "    ssh -L 8080:localhost:80 <user>@<this server>   then open http://localhost:8080"
  echo "  For a team: point a hostname here, set DOMAIN=<hostname> and remove RASAD_BIND in .env, then 'docker compose up -d'"
fi
echo "  First admin password:"
docker compose exec -T api cat /data/admin-password.txt 2>/dev/null || echo "   (set by RASAD_ADMIN_PASSWORD in .env)"
echo "  Logs: docker compose logs -f api scheduler"
