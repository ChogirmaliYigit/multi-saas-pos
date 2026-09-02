#!/usr/bin/env bash
#
# Emits the secret lines for .env. Pipe into the file, or copy the output.
#
#   ./deployment/scripts/generate-secrets.sh
#
set -euo pipefail

random() {
    # base64 then strip characters that need escaping in .env or a URL --
    # a password containing '%' or '#' breaks the DSN or the env parser in
    # ways that are tedious to diagnose.
    openssl rand -base64 "$1" | tr -d '\n=+/#%&?' | cut -c "1-$2"
}

cat <<VARS
SECRET_KEY=$(random 64 64)
POSTGRES_ADMIN_PASSWORD=$(random 32 32)
POSTGRES_APP_PASSWORD=$(random 32 32)
SUPER_ADMIN_PASSWORD=$(random 24 24)
VARS
