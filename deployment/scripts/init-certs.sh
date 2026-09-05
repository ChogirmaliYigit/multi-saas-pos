#!/usr/bin/env bash
#
# First-time certificate issuance. Renewal is automatic afterwards -- the
# certbot service runs `renew` twice a day.
#
#   CERTBOT_EMAIL=you@example.com ./deployment/scripts/init-certs.sh saas-pos.com
set -euo pipefail

DOMAIN="${1:-${BASE_DOMAIN:-}}"
EMAIL="${CERTBOT_EMAIL:-}"

if [[ -z "$DOMAIN" ]]; then
    echo "usage: CERTBOT_EMAIL=you@example.com $0 <base-domain>" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Compose prefixes volumes with the project name. `|| true` matters: under
# `set -o pipefail` a grep with no match kills the script silently, which is a
# miserable thing to debug.
PROJECT="$(docker compose config --format json 2>/dev/null \
    | sed -n 's/.*"name": *"\([^"]*\)".*/\1/p' | head -1 || true)"
CERT_VOLUME="${PROJECT:-pos}_certbot-certs"

# --------------------------------------------------------------------------
# Break the bootstrap deadlock.
#
# Nginx refuses to start when a `ssl_certificate` file is missing, but certbot
# needs Nginx running to serve the ACME challenge. Without a placeholder there
# is no order of operations that works -- the classic Let's Encrypt chicken and
# egg. A throwaway self-signed pair lets Nginx boot; certbot then overwrites it
# with the real thing.
# --------------------------------------------------------------------------
ensure_placeholder() {
    local name="$1"
    if docker run --rm -v "$CERT_VOLUME:/etc/letsencrypt" alpine:3.20 \
            test -f "/etc/letsencrypt/live/$name/fullchain.pem" 2>/dev/null; then
        return
    fi
    echo "==> Writing a temporary self-signed certificate for $name"
    docker run --rm -v "$CERT_VOLUME:/etc/letsencrypt" alpine:3.20 sh -c "
        apk add --no-cache openssl >/dev/null 2>&1
        mkdir -p /etc/letsencrypt/live/$name
        openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
            -keyout /etc/letsencrypt/live/$name/privkey.pem \
            -out /etc/letsencrypt/live/$name/fullchain.pem \
            -subj '/CN=$name' >/dev/null 2>&1
    "
}

# The config references both hosts, so both need a file present before Nginx
# will parse it.
ensure_placeholder "$DOMAIN"
ensure_placeholder "api.$DOMAIN"

echo "==> Starting Nginx"
docker compose up -d nginx
sleep 3
if [[ "$(docker compose ps nginx --format '{{.State}}')" != "running" ]]; then
    echo "Nginx did not start. Logs:" >&2
    docker compose logs nginx | tail -20 >&2
    exit 1
fi

if [[ -z "$EMAIL" ]]; then
    echo
    echo "Nginx is up with placeholder certificates. Set CERTBOT_EMAIL and"
    echo "re-run to obtain real ones."
    exit 0
fi

cat <<NOTE

Two certificates are needed, issued differently:

  1. api.$DOMAIN          HTTP-01 via the webroot. Automated below.
  2. $DOMAIN + *.$DOMAIN  A wildcard, because tenant subdomains are unbounded.
                          Let's Encrypt only issues wildcards over DNS-01,
                          which needs a provider plugin and an API token.

Only the first is automated. For the wildcard, run certbot with your DNS
provider's plugin, for example:

  docker compose run --rm --entrypoint certbot certbot \\
      certonly --dns-cloudflare \\
      --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \\
      -d "$DOMAIN" -d "*.$DOMAIN" \\
      --email "$EMAIL" --agree-tos --no-eff-email

NOTE

read -rp "Issue the api.$DOMAIN certificate now? [y/N] " reply
if [[ "$reply" =~ ^[Yy]$ ]]; then
    # Remove the placeholder before asking certbot for the real thing.
    #
    # certbot refuses to write into a live/ directory it did not create --
    # "live directory exists" -- and there is no flag that overrides it. Nginx
    # is already running and holds the certificate it loaded in memory, so
    # deleting the files underneath it is safe; it picks up the real one on
    # the reload below.
    docker compose run --rm --entrypoint sh certbot -c \
        "rm -rf /etc/letsencrypt/live/api.$DOMAIN \
                /etc/letsencrypt/archive/api.$DOMAIN \
                /etc/letsencrypt/renewal/api.$DOMAIN.conf"

    docker compose run --rm --entrypoint certbot certbot \
        certonly --webroot -w /var/www/certbot \
        -d "api.$DOMAIN" \
        --email "$EMAIL" --agree-tos --no-eff-email \
        --non-interactive

    echo "==> Reloading Nginx"
    docker compose exec nginx nginx -s reload
    echo "Done. api.$DOMAIN now has a real certificate."
fi
