#!/usr/bin/env bash
#
# Installs the nightly database backup. Idempotent.
#
#   sudo ./deployment/scripts/install-backup-cron.sh
#
# Creates the backup directory, sets up log rotation, and adds the crontab
# entry for the user who invoked sudo (not root -- the backup runs `docker
# compose`, and root's docker context is not necessarily the same one).
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }

RUN_AS="${SUDO_USER:-}"
[[ -n "$RUN_AS" && "$RUN_AS" != "root" ]] || {
    echo "Run this via sudo from the deploy user, not as root directly." >&2
    exit 1
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pos}"
LOG="/var/log/pos-backup.log"
SCHEDULE="${SCHEDULE:-17 3 * * *}"

echo "==> Creating $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
chown "$RUN_AS:$RUN_AS" "$BACKUP_DIR"
# Dumps contain every shop's trading history in the clear.
chmod 700 "$BACKUP_DIR"

echo "==> Preparing $LOG"
touch "$LOG"
chown "$RUN_AS:$RUN_AS" "$LOG"
chmod 640 "$LOG"

echo "==> Installing log rotation"
cat > /etc/logrotate.d/pos-backup <<ROTATE
$LOG {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    su $RUN_AS $RUN_AS
    create 640 $RUN_AS $RUN_AS
}
ROTATE

echo "==> Installing the crontab entry for $RUN_AS"
ENTRY="$SCHEDULE $ROOT/deployment/scripts/backup.sh >> $LOG 2>&1"
# Replace any previous entry rather than appending a duplicate every run.
CURRENT="$(crontab -u "$RUN_AS" -l 2>/dev/null | grep -v 'deployment/scripts/backup.sh' || true)"
printf '%s\n%s\n' "$CURRENT" "$ENTRY" | sed '/^$/d' | crontab -u "$RUN_AS" -

echo
echo "Installed:"
crontab -u "$RUN_AS" -l | sed 's/^/  /'
echo
echo "  backups   $BACKUP_DIR  (kept ${RETAIN_DAYS:-14} days)"
echo "  log       $LOG"
echo
echo "Run it once now to confirm:"
echo "  $ROOT/deployment/scripts/backup.sh"
