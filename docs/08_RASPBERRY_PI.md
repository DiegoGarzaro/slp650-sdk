# Raspberry Pi reference implementation

The Raspberry Pi (or any Debian-based Linux host) is the reference platform:
it runs all three layers — renderer, encoder, transport — plus the REST API.

## 1. Install the driver toolchain

Copy this repository to the Pi and run:

```bash
sudo ./scripts/install_driver.sh
```

The script installs CUPS and build tools, clones and builds the open-source
Seiko driver (<https://github.com/fawkesley/smart-label-printer-slp-linux-driver>),
installs the `seikoslp.rastertolabel` filter and the PPD, and adds your user to
the `lp`/`lpadmin` groups. To target a different account:
`sudo SLP650_USER=someuser ./scripts/install_driver.sh`.

Log out and back in (group membership), then verify:

```bash
lsusb -d 0619:0126
ls -l /dev/usb/lp0
sudo lpinfo -v | grep -i -E 'seiko|smart|0619'
```

`lpinfo -v` may return `Forbidden` for an unprivileged user — use `sudo`, or
log back in after the installer adds the account to `lpadmin`.

## 2. Capture the printer-native stream

The most useful step for future embedded transports:

```bash
./scripts/capture_raw.sh label.png label.slp AddressSmall
# or, with the SDK installed:
slp650 label.png --media AddressSmall --capture label.slp --dry-run
```

Inspect and replay:

```bash
xxd -g 1 label.slp | less
cat label.slp > /dev/usb/lp0   # prints the label
```

The same `label.slp` payload is exactly what an embedded transport would write
to USB bulk endpoint `0x01`.

## 3. Print directly (no CUPS queue)

```bash
slp650 label.png --media AddressSmall --density MediumQuality --fine-print --copies 2
```

Do not send a CUPS job and a direct device job concurrently.

## 4. Install the REST API service

```bash
sudo ./scripts/install_api.sh
```

This installs the package into a venv under `/opt/slp650-agent`, creates an
API key in `/etc/default/slp650-api`, and starts a systemd service
(`slp650-api`) on TCP port 8787. Usage: see [07_REST_API.md](07_REST_API.md).

Service management:

```bash
systemctl status slp650-api
journalctl -u slp650-api -f
```

## Ideas

- Attach a Pi camera and print captured photos as labels via `/print/image`.
