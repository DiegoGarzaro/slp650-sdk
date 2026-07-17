# Python SDK

## Install

```bash
uv add slp650-sdk        # from a git/path source until published
# or, inside this repo:
uv sync
```

Requires Python ≥ 3.11. The encoder additionally needs the CUPS toolchain and
the Seiko filter on the host (see [08_RASPBERRY_PI.md](08_RASPBERRY_PI.md));
rendering works anywhere.

## Library usage

```python
from pathlib import Path

from slp650_sdk import SLPConfig, build_native_stream, print_file, send_native_stream
from slp650_sdk.rendering import render_text_label

config = SLPConfig(media="AddressSmall", density="MediumQuality")

# Render a text label to a 1-bit PNG.
render_text_label("Hello from the SLP650", "AddressSmall", Path("label.png"))

# Encode to the printer-native stream (no printing).
data = build_native_stream(Path("label.png"), config)
Path("label.slp").write_bytes(data)

# Send a native stream to the printer.
send_native_stream(data, config, copies=2)

# Or do encode + send in one call.
print_file(Path("label.png"), config, copies=1, capture_path=Path("label.slp"))
```

Configuration can also come from `SLP650_PPD`, `SLP650_FILTER`,
`SLP650_DEVICE`, and `SLP650_LOCK` environment variables via
`SLPConfig.from_env()`.

## CLI

The package installs a `slp650` command:

```bash
# Print an image
slp650 label.png --media AddressSmall --density MediumQuality --copies 2

# Capture the native stream without printing
slp650 label.png --media AddressSmall --capture label.slp --dry-run

# Fine mode, custom device
slp650 label.png --fine-print --device /dev/usb/lp1
```

Exit code is non-zero on failure, with the reason on stderr.

Two companion commands support protocol reverse engineering (see
[03_NATIVE_PROTOCOL.md](03_NATIVE_PROTOCOL.md)):

```bash
slp650-patterns --media AddressSmall --out fixtures/   # controlled test images
slp650-dump capture.slp                                # annotated stream dump
slp650-dump a.slp b.slp                                # diff two captures
```

## Concurrency

Device access is serialized with an exclusive lock file
(`/run/lock/slp650.lock` by default). Do not send a CUPS job and a direct
device job concurrently — CUPS does not honor this lock.
