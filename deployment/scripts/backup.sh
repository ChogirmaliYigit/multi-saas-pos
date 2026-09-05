#!/usr/bin/env bash
#
# Database backup. Designed to run unattended from cron:
#
#   0 3 * * * /srv/pos/deployment/scripts/backup.sh >> /var/log/pos-backup.log 2>&1
#
# Install it with:  ./deployment/scripts/install-backup-cron.sh
set -euo pipefail

# cron gives you almost no environment. Docker lives in /usr/bin, but say so
# explicitly rather than depending on whatever cron happens to inherit.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/pos}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/pos-$STAMP.dump"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"; }

# A slow dump must not overlap the next scheduled run: two pg_dumps competing
# for the same disk turns a nightly job into a permanent one.
exec 9>"/tmp/pos-backup.lock"
if ! flock -n 9; then
    log "another backup is still running; skipping this run"
    exit 0
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
    log "ERROR: $BACKUP_DIR does not exist. Run install-backup-cron.sh first."
    exit 1
fi
if [[ ! -w "$BACKUP_DIR" ]]; then
    log "ERROR: $BACKUP_DIR is not writable by $(id -un)."
    exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

if [[ "$(docker compose ps -q postgres | wc -l)" -eq 0 ]]; then
    log "ERROR: the postgres container is not running; nothing to back up."
    exit 1
fi

log "dumping $POSTGRES_DB"
# Custom format: compressed, and pg_restore can pull out individual tables
# during a partial recovery. --clean --if-exists so it restores over an
# existing database.
if ! docker compose exec -T postgres pg_dump \
        -U "$POSTGRES_ADMIN_USER" \
        -d "$POSTGRES_DB" \
        --format=custom --clean --if-exists \
        > "$TARGET"; then
    log "ERROR: pg_dump failed"
    rm -f "$TARGET"
    exit 1
fi

SIZE=$(stat -c%s "$TARGET" 2>/dev/null || stat -f%z "$TARGET")
if [[ "$SIZE" -lt 1024 ]]; then
    # A truncated dump that still exits 0 is the worst kind of backup: it
    # looks like one until the day you need it.
    log "ERROR: dump is only ${SIZE}B, refusing to keep it"
    rm -f "$TARGET"
    exit 1
fi

# An unverified backup is a hypothesis. Reading the archive's table of
# contents proves the file is a well-formed dump, not half a stream.
if ! docker compose exec -T postgres pg_restore --list < "$TARGET" >/dev/null 2>&1; then
    log "ERROR: dump failed verification, removing it"
    rm -f "$TARGET"
    exit 1
fi

log "wrote $(basename "$TARGET") ($(numfmt --to=iec "$SIZE" 2>/dev/null || echo "${SIZE}B")), verified"

DELETED=$(find "$BACKUP_DIR" -name 'pos-*.dump' -mtime "+$RETAIN_DAYS" -print -delete | wc -l)
[[ "$DELETED" -gt 0 ]] && log "pruned $DELETED dump(s) older than $RETAIN_DAYS days"

log "kept: $(find "$BACKUP_DIR" -name 'pos-*.dump' | wc -l) dump(s), $(du -sh "$BACKUP_DIR" | cut -f1) total"
