#!/usr/bin/env bash
# Check DNS and HTTPS front-end for production (Caddy → Streamlit).
#
# Usage:
#   ./scripts/verify_https_setup.sh
#   DOMAIN=pulse-dividend.duckdns.org EXPECT_IP=35.224.4.144 ./scripts/verify_https_setup.sh
set -euo pipefail

DOMAIN="${DOMAIN:-pulse-dividend.duckdns.org}"
EXPECT_IP="${EXPECT_IP:-}"

echo "=== HTTPS setup check: ${DOMAIN} ==="
echo ""

echo "DNS:"
RESOLVED="$(dig +short "$DOMAIN" 2>/dev/null | tail -1 || true)"
if [[ -z "$RESOLVED" ]]; then
  echo "  FAIL — no A record for ${DOMAIN}"
else
  echo "  ${DOMAIN} → ${RESOLVED}"
  if [[ -n "$EXPECT_IP" && "$RESOLVED" != "$EXPECT_IP" ]]; then
    echo "  WARN — expected ${EXPECT_IP}"
  fi
fi
echo ""

echo "HTTP (port 80):"
HTTP_HEADERS="$(curl -sI --max-time 15 "http://${DOMAIN}/" 2>&1 || true)"
echo "$HTTP_HEADERS" | sed -n '1,6p'
if echo "$HTTP_HEADERS" | grep -qi 'server: nginx'; then
  echo "  FAIL — nginx is answering. Run on the VM:"
  echo "    sudo ./deploy/gcp/setup-https-caddy.sh"
elif echo "$HTTP_HEADERS" | grep -qi 'server: caddy'; then
  echo "  OK — Caddy on HTTP"
fi
echo ""

echo "HTTPS (port 443):"
HTTPS_HEADERS="$(curl -sI --max-time 15 "https://${DOMAIN}/" 2>&1 || true)"
echo "$HTTPS_HEADERS" | sed -n '1,8p'
if echo "$HTTPS_HEADERS" | grep -qi 'server: nginx'; then
  echo "  FAIL — nginx is answering on HTTPS (default welcome page, not Streamlit)"
  echo "  Fix on VM: sudo ./deploy/gcp/setup-https-caddy.sh"
  exit 1
fi
if echo "$HTTPS_HEADERS" | grep -qi 'server: caddy'; then
  echo "  OK — Caddy terminates TLS"
fi
if echo "$HTTPS_HEADERS" | grep -qi 'content-length: 615'; then
  echo "  WARN — tiny response (615 bytes) is usually nginx default HTML, not Streamlit"
fi
BODY_SNIP="$(curl -sk --max-time 15 "https://${DOMAIN}/" 2>/dev/null | head -c 200 || true)"
if echo "$BODY_SNIP" | grep -qi 'streamlit'; then
  echo "  OK — Streamlit HTML detected"
elif echo "$BODY_SNIP" | grep -qi 'Welcome to nginx'; then
  echo "  FAIL — nginx default page (Caddy not proxying to Streamlit)"
  exit 1
else
  echo "  Body preview: ${BODY_SNIP:0:120}..."
fi
echo ""
echo "Done."
