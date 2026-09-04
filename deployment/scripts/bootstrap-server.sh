#!/usr/bin/env bash
#
# Prepares a fresh Ubuntu VPS: Docker, firewall, swap, SSH hardening.
# Run once, as root, on the server:
#
#   curl -fsSL <raw-url>/bootstrap-server.sh | bash
#   # or: scp it over, then  bash bootstrap-server.sh
#
# Idempotent -- safe to re-run.
set -euo pipefail

log() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

[[ $EUID -eq 0 ]] || { echo "Run as root (or with sudo)." >&2; exit 1; }

if ! grep -qiE "ubuntu|debian" /etc/os-release; then
    echo "This script targets Ubuntu/Debian. Adapt it for other distributions." >&2
    exit 1
fi

log "Updating packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -yqq

log "Installing base tools"
apt-get install -yqq ca-certificates curl gnupg ufw fail2ban unattended-upgrades

# --------------------------------------------------------------------------
# Swap.
#
# Docker builds and Postgres are both happy to spike past a small VPS's RAM.
# Without swap the OOM killer picks a process -- usually Postgres, usually
# mid-write. Swap is slow, but slow beats a killed database.
# --------------------------------------------------------------------------
TOTAL_MB=$(free -m | awk '/^Mem:/{print $2}')
if [[ $TOTAL_MB -lt 4096 && ! -f /swapfile ]]; then
    log "RAM is ${TOTAL_MB}MB -- adding a 2G swapfile"
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # Prefer RAM; only reach for swap under real pressure.
    sysctl -w vm.swappiness=10 >/dev/null
    grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

log "Installing Docker"
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -yqq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

log "Capping Docker log growth"
# Containers log to disk forever by default; a chatty API fills a 40GB VPS.
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
systemctl restart docker

# --------------------------------------------------------------------------
# Firewall. Only SSH and HTTP(S). Postgres and Redis are bound to the compose
# network and never published, but a firewall is the layer that holds if
# someone later adds a `ports:` entry without thinking.
# --------------------------------------------------------------------------
log "Configuring the firewall"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ufw status verbose | head -6

log "Enabling fail2ban for SSH"
systemctl enable --now fail2ban

log "Enabling unattended security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades

# --------------------------------------------------------------------------
# SSH hardening. Only applied when a key is already installed -- switching
# off passwords before that locks you out of your own server.
# --------------------------------------------------------------------------
if [[ -s /root/.ssh/authorized_keys ]] || [[ -n "$(find /home -name authorized_keys -size +0 2>/dev/null | head -1)" ]]; then
    log "Disabling SSH password authentication (a key is present)"
    sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    sshd -t && systemctl reload ssh
else
    echo
    echo "!! No authorized_keys found -- leaving password login enabled."
    echo "!! Install your key first, then re-run to harden SSH."
fi

log "Creating the deploy directory"
mkdir -p /srv/pos
chown "${SUDO_USER:-root}:${SUDO_USER:-root}" /srv/pos 2>/dev/null || true

cat <<DONE

Server ready.

  docker    $(docker --version | cut -d, -f1)
  compose   $(docker compose version --short 2>/dev/null || echo '-')
  ram       ${TOTAL_MB}MB $( [[ -f /swapfile ]] && echo '+ 2G swap' )
  firewall  22, 80, 443

Next:
  git clone <repo> /srv/pos && cd /srv/pos
  cp .env.example .env && ./deployment/scripts/generate-secrets.sh >> .env
  \$EDITOR .env
  ./deployment/scripts/configure-nginx.sh <your-domain>
  CERTBOT_EMAIL=<you> ./deployment/scripts/init-certs.sh <your-domain>
  docker compose up -d
DONE
