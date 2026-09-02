#!/usr/bin/env bash
#
# Database backup. Run from cron:
#   0 3 * * * /srv/pos/deployment/scripts/backup.sh >> /var/log/pos-backup.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/pos}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

# shellcheck disable=SC1091
set -a; source .env; set +a

# --clean --if-exists so the dump can be restored over an existing database.
# Custom format (-Fc) rather than plain SQL: it is compressed and lets
# pg_restore pick individual tables during a partial recovery.
docker compose exec -T postgres pg_dump \
    -U "$POSTGRES_ADMIN_USER" \
    -d "$POSTGRES_DB" \
    --format=custom --clean --if-exists \
    > "$BACKUP_DIR/pos-$STAMP.dump"

echo "wrote $BACKUP_DIR/pos-$STAMP.dump ($(du -h "$BACKUP_DIR/pos-$STAMP.dump" | cut -f1))"

# A backup that has never been restored is a hypothesis. Verify the dump is
# readable before trusting it.
if ! docker compose exec -T postgres pg_restore --list < "$BACKUP_DIR/pos-$STAMP.dump" >/dev/null; then
    echo "WARNING: dump failed verification" >&2
    exit 1
fi

find "$BACKUP_DIR" -name 'pos-*.dump' -mtime "+$RETAIN_DAYS" -delete
echo "verified; pruned dumps older than $RETAIN_DAYS days"
