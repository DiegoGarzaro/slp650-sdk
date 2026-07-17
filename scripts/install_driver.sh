#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./scripts/install_driver.sh" >&2
  exit 1
fi

# The account added to lp/lpadmin. Override with:
# sudo SLP650_USER=someuser ./scripts/install_driver.sh
TARGET_USER=${SLP650_USER:-${SUDO_USER:-}}
if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
  echo "Could not determine a non-root target user." >&2
  echo "Run via sudo from your normal account, or set SLP650_USER." >&2
  exit 1
fi
SOURCE_DIR=/opt/slp650-driver-src
RUNTIME_DIR=/opt/slp650
REPO=https://github.com/fawkesley/smart-label-printer-slp-linux-driver.git

apt-get update
apt-get install -y \
  git build-essential cups cups-client cups-bsd cups-filters \
  libcups2-dev libcupsimage2-dev libjpeg-dev zlib1g-dev \
  python3 python3-venv python3-pip fonts-dejavu-core xxd

systemctl enable --now cups
usermod -aG lp,lpadmin "$TARGET_USER" || true

if [[ -d "$SOURCE_DIR/.git" ]]; then
  git -C "$SOURCE_DIR" pull --ff-only
else
  rm -rf "$SOURCE_DIR"
  git clone --depth 1 "$REPO" "$SOURCE_DIR"
fi

cd "$SOURCE_DIR/src"
make clean || true
make build

FILTER_DIR=$(cups-config --serverbin)/filter
install -m 0755 seikoslp.rastertolabel "$FILTER_DIR/seikoslp.rastertolabel"

mkdir -p "$RUNTIME_DIR"
install -m 0644 siislp650.ppd "$RUNTIME_DIR/siislp650.ppd"

# Also make the model visible to CUPS.
MODEL_DIR=$(cups-config --datadir)/model/seiko
mkdir -p "$MODEL_DIR"
gzip -c siislp650.ppd > "$MODEL_DIR/siislp650.ppd.gz"

udevadm control --reload-rules || true
udevadm trigger || true
systemctl restart cups

cat <<EOF

Driver installed.

1. Reconnect/power-cycle the printer.
2. Log out and back in so membership in lp/lpadmin takes effect.
3. Confirm detection:
     lsusb -d 0619:0126
     ls -l /dev/usb/lp0
     sudo lpinfo -v | grep -i -E 'seiko|smart|0619'
4. Direct capture/print test from this project:
     ./scripts/capture_raw.sh label.png label.slp AddressSmall

PPD:    $RUNTIME_DIR/siislp650.ppd
Filter: $FILTER_DIR/seikoslp.rastertolabel
EOF
