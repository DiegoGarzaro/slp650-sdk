#!/usr/bin/env bash
# Install the SLP650 REST print agent as a systemd service.
# Run from a checkout of this repository: sudo ./scripts/install_api.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./scripts/install_api.sh" >&2
  exit 1
fi

# The service runs as the invoking user (must be in the lp group).
# Override with: sudo SLP650_USER=someuser ./scripts/install_api.sh
TARGET_USER=${SLP650_USER:-${SUDO_USER:-}}
if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
  echo "Could not determine a non-root service user." >&2
  echo "Run via sudo from your normal account, or set SLP650_USER." >&2
  exit 1
fi

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST=/opt/slp650-agent

mkdir -p "$DEST"
python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install --upgrade pip
"$DEST/.venv/bin/pip" install "$REPO_ROOT"
chown -R "$TARGET_USER:lp" "$DEST"

install -m 0644 "$REPO_ROOT/systemd/slp650-api.service" /etc/systemd/system/slp650-api.service
sed -i "s/^User=.*/User=$TARGET_USER/" /etc/systemd/system/slp650-api.service

if [[ ! -f /etc/default/slp650-api ]]; then
  API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  cat > /etc/default/slp650-api <<EOF
SLP650_API_KEY=$API_KEY
SLP650_PPD=/opt/slp650/siislp650.ppd
SLP650_FILTER=/usr/lib/cups/filter/seikoslp.rastertolabel
SLP650_DEVICE=/dev/usb/lp0
EOF
  chmod 0600 /etc/default/slp650-api
  echo "Generated API key: $API_KEY"
  echo "It is also stored in /etc/default/slp650-api"
fi

systemctl daemon-reload
systemctl enable --now slp650-api
systemctl --no-pager --full status slp650-api || true
