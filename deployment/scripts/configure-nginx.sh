#!/usr/bin/env bash
#
# Substitutes the real domain into the Nginx configs.
#
#   ./deployment/scripts/configure-nginx.sh saas-pos.com
#
# The configs ship with a __BASE_DOMAIN__ placeholder rather than an
# envsubst-at-runtime template, so what is on disk is exactly what Nginx
# loads -- one less layer between "the file says X" and "the server does X".
set -euo pipefail

DOMAIN="${1:-${BASE_DOMAIN:-}}"
if [[ -z "$DOMAIN" ]]; then
    echo "usage: $0 <base-domain>" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONF_DIR="$ROOT/deployment/nginx/conf.d"

substituted=0
for file in "$CONF_DIR"/*.conf; do
    if grep -q "__BASE_DOMAIN__" "$file"; then
        substituted=$((substituted + 1))
        # Keep a .orig once, so re-running against a different domain still
        # starts from the placeholder rather than a half-substituted file.
        [[ -f "$file.orig" ]] || cp "$file" "$file.orig"
        sed "s/__BASE_DOMAIN__/$DOMAIN/g" "$file.orig" > "$file"
        echo "configured $(basename "$file") -> $DOMAIN"
    fi
done

# Silence here means the configs were already substituted for some other
# domain -- which is how a stale "api.localhost" once shipped unnoticed.
if [[ $substituted -eq 0 ]]; then
    echo
    echo "!! No __BASE_DOMAIN__ placeholders found." >&2
    echo "!! The configs are already substituted. Current server_name values:" >&2
    grep -h "server_name" "$CONF_DIR"/*.conf | sed 's/^/     /' >&2
    echo "!! Restore them with: git checkout -- $CONF_DIR" >&2
    exit 1
fi

echo
echo "Next:"
echo "  1. Point DNS at this host:"
echo "       A     $DOMAIN          -> <server ip>"
echo "       A     api.$DOMAIN      -> <server ip>"
echo "       A     *.$DOMAIN        -> <server ip>   (tenant subdomains)"
echo "  2. Issue certificates:  ./deployment/scripts/init-certs.sh $DOMAIN"
echo "  3. docker compose up -d"
