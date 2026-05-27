#!/usr/bin/env bash
# Install Caddy on the GCP VM and reverse-proxy HTTPS → Streamlit (localhost:8501).
#
# Stops nginx if it is bound to :80/:443 (common on fresh Ubuntu images).
#
# Usage (on the VM):
#   cd ~/dividend-healthcheck
#   sudo ./deploy/gcp/setup-https-caddy.sh
#   sudo DOMAIN=app.example.com ./deploy/gcp/setup-https-caddy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOMAIN="${DOMAIN:-pulse-dividend.duckdns.org}"
UPSTREAM="${UPSTREAM:-127.0.0.1:8501}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root: sudo DOMAIN=${DOMAIN} $0" >&2
  exit 1
fi

echo "==> Domain: ${DOMAIN}"
echo "==> Upstream: ${UPSTREAM}"

_free_web_ports() {
  echo "==> Ensuring ports 80/443 are free for Caddy..."
  if systemctl is-active --quiet nginx 2>/dev/null; then
    echo "    Stopping nginx (was serving default page on :80/:443)"
    systemctl stop nginx
    systemctl disable nginx || true
  fi
  if systemctl is-active --quiet apache2 2>/dev/null; then
    echo "    Stopping apache2"
    systemctl stop apache2
    systemctl disable apache2 || true
  fi
}

_install_caddy() {
  if command -v caddy >/dev/null 2>&1; then
    echo "==> Caddy already installed: $(caddy version 2>/dev/null | head -1 || true)"
    return
  fi
  echo "==> Installing Caddy..."
  apt-get update
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
}

_write_caddyfile() {
  local template="${ROOT}/deploy/gcp/Caddyfile"
  echo "==> Writing /etc/caddy/Caddyfile for ${DOMAIN}..."
  if [[ -f "$template" ]]; then
    sed "s/pulse-dividend\\.duckdns\\.org/${DOMAIN//./\\.}/g" "$template" > /etc/caddy/Caddyfile
  else
    cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
	encode gzip
	reverse_proxy ${UPSTREAM} {
		header_up Host {host}
		header_up X-Forwarded-For {remote_host}
		header_up X-Forwarded-Proto {scheme}
		header_up X-Forwarded-Host {host}
	}
}
EOF
  fi
  caddy validate --config /etc/caddy/Caddyfile
}

_start_caddy() {
  systemctl enable caddy
  systemctl restart caddy
  systemctl --no-pager --full status caddy || true
}

_check_upstream() {
  echo "==> Checking Streamlit upstream ${UPSTREAM}..."
  if curl -sf --max-time 3 "http://${UPSTREAM}/" >/dev/null 2>&1; then
    echo "    OK — Streamlit responds on ${UPSTREAM}"
  else
    echo "    WARN — nothing on ${UPSTREAM}. Start Docker first:"
    echo "      cd ~/dividend-healthcheck && docker compose up -d --build"
  fi
}

_free_web_ports
_install_caddy
_write_caddyfile
_start_caddy
_check_upstream

echo ""
echo "HTTPS proxy ready."
echo "  App URL:  https://${DOMAIN}/"
echo "  OAuth:    https://${DOMAIN}/oauth2callback"
echo ""
echo "Verify from your laptop:"
echo "  curl -sI https://${DOMAIN}/ | grep -Ei 'HTTP/|server:'"
echo "  (expect Server: Caddy, not nginx)"
echo ""
echo "Update on the VM:"
echo "  .streamlit/secrets.toml → redirect_uri = \"https://${DOMAIN}/oauth2callback\""
echo "Google Cloud Console → OAuth client → Authorized redirect URIs (same URL)."
