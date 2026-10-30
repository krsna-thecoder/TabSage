#!/usr/bin/env bash
# TabSage EC2 deploy helper.
# Run from the backend/ directory:
#   bash deploy/run.sh <domain> <chrome-extension-origin>
# Example:
#   bash deploy/run.sh tabsage.duckdns.org "chrome-extension://abcd1234..."
set -eu

DOMAIN="${1:-tabsage.duckdns.org}"
EXT_ID="${2:-chrome-extension://REPLACE_WITH_EXTENSION_ID}"

echo ">> Building image (first time ~1-3 min)..."
docker build -t tabsage-backend .

echo ">> Removing any old containers/network (ignore errors)..."
docker rm -f tabsage caddy 2>/dev/null || true
docker network rm tabsage-net 2>/dev/null || true

echo ">> Writing Caddyfile for $DOMAIN ..."
printf '%s {\n    reverse_proxy tabsage:8000\n}\n' "$DOMAIN" > "$HOME/Caddyfile"

echo ">> Creating network..."
docker network create tabsage-net

echo ">> Starting app container..."
docker run -d --name tabsage --network tabsage-net --restart unless-stopped \
  -e ENV=prod -e ALLOWED_ORIGINS="$EXT_ID" -e FORWARDED_ALLOW_IPS="*" -e WEB_CONCURRENCY=1 \
  tabsage-backend

echo ">> Starting Caddy (HTTPS on 80/443)..."
docker run -d --name caddy --network tabsage-net --restart unless-stopped \
  -p 80:80 -p 443:443 -v caddy_data:/data -v caddy_config:/config \
  -v "$HOME/Caddyfile":/etc/caddy/Caddyfile caddy:2

echo ">> Done. Running containers:"
docker ps
echo ">> Now test:  curl https://$DOMAIN/health"
