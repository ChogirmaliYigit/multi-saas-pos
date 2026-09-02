#!/usr/bin/env bash
#
# Deploy the current checkout.
#
#   ./deployment/scripts/deploy.sh
#
# Builds images tagged with the git SHA, applies migrations, restarts the
# services, and rolls back if the new API fails its health check.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

[[ -f .env ]] || { echo "No .env -- copy .env.example and fill it in." >&2; exit 1; }

TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
PREVIOUS="$(grep -E '^IMAGE_TAG=' .env | cut -d= -f2 || echo latest)"

log() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

log "Building images as $TAG"
IMAGE_TAG="$TAG" docker compose build

log "Applying migrations"
# The migrate service runs to completion and exits. A non-zero exit here stops
# the deploy before any new API container starts, so a bad migration never
# meets live traffic.
if ! IMAGE_TAG="$TAG" docker compose run --rm migrate; then
    echo "Migration failed. Nothing was restarted; the running version is untouched." >&2
    exit 1
fi

log "Rolling out"
sed -i.bak "s/^IMAGE_TAG=.*/IMAGE_TAG=$TAG/" .env && rm -f .env.bak
IMAGE_TAG="$TAG" docker compose up -d --no-deps api worker beat nginx

log "Waiting for the API to report ready"
for attempt in $(seq 1 30); do
    if docker compose exec -T api curl -fsS http://localhost:8000/health/ready >/dev/null 2>&1; then
        log "Deployed $TAG"
        docker image prune -f --filter "until=168h" >/dev/null 2>&1 || true
        exit 0
    fi
    sleep 2
done

log "Health check failed -- rolling back to $PREVIOUS"
sed -i.bak "s/^IMAGE_TAG=.*/IMAGE_TAG=$PREVIOUS/" .env && rm -f .env.bak
IMAGE_TAG="$PREVIOUS" docker compose up -d --no-deps api worker beat
echo "Rolled back. Note: migrations are NOT reverted -- check whether the" >&2
echo "schema change is compatible with $PREVIOUS before retrying." >&2
exit 1
