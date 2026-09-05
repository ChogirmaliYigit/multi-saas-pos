#!/usr/bin/env bash
#
# Restores the most recent dump into a scratch database and checks it is
# actually usable, then drops it.
#
#   ./deployment/scripts/verify-restore.sh              # newest dump
#   ./deployment/scripts/verify-restore.sh <file.dump>  # a specific one
#
# `pg_restore --list` in backup.sh only proves the archive is well-formed.
# This proves it restores -- which is the only property that matters, and the
# one nobody checks until the night they need it.
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/pos}"
SCRATCH="pos_restore_check_$$"

# shellcheck disable=SC1091
set -a; source .env; set +a

DUMP="${1:-$(find "$BACKUP_DIR" -name 'pos-*.dump' -type f -print0 2>/dev/null \
    | xargs -0 ls -t 2>/dev/null | head -1)}"
[[ -n "$DUMP" && -f "$DUMP" ]] || { echo "No dump found in $BACKUP_DIR" >&2; exit 1; }

psql_scratch() {
    docker compose exec -T postgres psql -U "$POSTGRES_ADMIN_USER" -d "$SCRATCH" -tAc "$1"
}
psql_admin() {
    docker compose exec -T postgres psql -U "$POSTGRES_ADMIN_USER" -d postgres -qc "$1"
}

cleanup() { psql_admin "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Verifying $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"

psql_admin "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null 2>&1
psql_admin "CREATE DATABASE $SCRATCH" >/dev/null

# --no-owner: the scratch database has no pos_app role grants to restore into,
# and ownership is recreated by the migrations anyway.
if ! docker compose exec -T postgres pg_restore -U "$POSTGRES_ADMIN_USER" \
        -d "$SCRATCH" --no-owner < "$DUMP" 2>/tmp/restore.err; then
    # pg_restore exits non-zero on ignorable notices too; only real failures
    # leave nothing behind, which the checks below catch.
    grep -viE "already exists|does not exist" /tmp/restore.err | head -5 >&2 || true
fi

check() {
    local label="$1" actual expected="$2"
    actual="$(psql_scratch "$3" | tr -d '[:space:]')"
    if [[ "$actual" -ge "$expected" ]]; then
        printf '  \033[32mok\033[0m   %-22s %s\n' "$label" "$actual"
    else
        printf '  \033[31mFAIL\033[0m %-22s %s (expected >= %s)\n' "$label" "$actual" "$expected"
        exit 1
    fi
}

check "tables"        20 "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
check "plans"          3 "SELECT count(*) FROM plans"
check "RLS policies"  19 "SELECT count(*) FROM pg_policies WHERE policyname='tenant_isolation'"
check "migrations"     1 "SELECT count(*) FROM alembic_version"

# Row-level security surviving a restore is not obvious: policies are schema
# objects, and a dump that quietly dropped them would restore a database with
# no tenant isolation at all.
FORCED="$(psql_scratch "SELECT count(*) FROM pg_class WHERE relrowsecurity AND relforcerowsecurity" | tr -d '[:space:]')"
if [[ "$FORCED" -ge 19 ]]; then
    printf '  \033[32mok\033[0m   %-22s %s\n' "FORCE RLS intact" "$FORCED"
else
    printf '  \033[31mFAIL\033[0m %-22s %s\n' "FORCE RLS intact" "$FORCED"
    exit 1
fi

echo
echo "Restore verified. Scratch database dropped."
