#!/usr/bin/env bash
# Install Caddy on the GCP VM and reverse-proxy HTTPS → Streamlit (localhost:8501).
# Prereqs: DNS A-record for DOMAIN → this VM's static external IP; firewall tcp 80,443.
#
# Usage (on the VM):
#   export DOMAIN=app.yourdomain.com
#   curl -fsSL https://raw.githubusercontent.com/.../setup-https-caddy.sh | bash
#   # or from repo:
#   chmod +x deploy/gcp/setup-https-caddy.sh
#   sudo DOMAIN=app.yourdomain.com ./deploy/gcp/setup-https-caddy.sh

set -euo pipefail

DOMAIN="${DOMAIN:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Set DOMAIN, e.g. export DOMAIN=app.example.com" >&2
  exit 1
fi

echo "==> Installing Caddy..."
sudo apt-get update
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install -y caddy

echo "==> Writing Caddyfile for ${DOMAIN}..."
sudo tee /etc/caddy/Caddyfile > /dev/null <<EOF
${DOMAIN} {
    reverse_proxy localhost:8501
}
EOF

echo "==> Opening firewall (if using default VPC tags)..."
# GCP console: also create rules allow-tcp-80 and allow-tcp-443 from 0.0.0.0/0

sudo systemctl enable caddy
sudo systemctl reload caddy || sudo systemctl restart caddy

echo ""
echo "HTTPS proxy ready."
echo "  App URL:  https://${DOMAIN}"
echo "  OAuth:    https://${DOMAIN}/oauth2callback"
echo ""
echo "Update on the VM:"
echo "  .streamlit/secrets.toml → redirect_uri = \"https://${DOMAIN}/oauth2callback\""
echo "Google Cloud Console → OAuth client → Authorized redirect URIs (same URL)."
