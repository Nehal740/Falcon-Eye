#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 22.04/24.04 server. Run as root:  bash scripts/server-setup.sh
set -euo pipefail

apt-get update && apt-get -y upgrade
apt-get -y install ca-certificates curl git ufw unattended-upgrades

# Docker (official convenience script)
curl -fsSL https://get.docker.com | sh

# Firewall: only SSH, HTTP and HTTPS
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "Done. Next: clone the repo, create .env, run docker compose (see docs/DEPLOYMENT.md)."
