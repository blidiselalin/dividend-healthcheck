#!/usr/bin/env bash
# Run once on a fresh Ubuntu 22.04/24.04 GCP VM (as your SSH user).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/blidiselalin/dividend-healthcheck.git}"
APP_DIR="${APP_DIR:-$HOME/dividend-healthcheck}"

echo "==> Installing Docker..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${VERSION_CODENAME:-$VERSION}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"

echo "==> Cloning app..."
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
git pull --ff-only || true

echo ""
echo "Bootstrap done. Log out and SSH back in (docker group), then:"
echo "  cd $APP_DIR"
echo "  docker compose up -d --build"
echo "  docker compose exec -T dividendscope python ingest_data.py --ensure-sp500"
echo "  docker compose exec -T dividendscope python ingest_data.py --enrich-existing"
echo "  docker compose exec -T dividendscope python ingest_data.py --sync-portfolio"
