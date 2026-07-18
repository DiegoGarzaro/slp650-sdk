# SLP650 SDK

A portable SDK for the **Seiko Smart Label Printer 650 / 650SE**
(`VID:PID 0619:0126`) built around a strict three-layer architecture:

```
Renderer  ──▶  Encoder  ──▶  Transport
content        native .slp     USB bulk OUT
to bitmap      byte stream     endpoint 0x01
```

Rendering is deliberately separated from transport, so the printer-native byte
stream can be produced on any backend and delivered by anything that can act
as a USB host — a Raspberry Pi today, an embedded USB-host board (ESP32-S3,
RP2040, STM32, a small Linux SBC, …) tomorrow.

The current reference implementation runs on Linux/Raspberry Pi and includes a
Python SDK, a `slp650` CLI, and a REST print agent.

## Highlights

- **Pure-Python native encoder** — `slp650 --native` / `encode_image()`
  implements the reverse-engineered protocol directly, works on any OS, and
  is verified byte-for-byte against hardware captures.
- **Print without a CUPS queue** — encode any image/PDF to the printer-native
  stream and write it straight to `/dev/usb/lp0`.
- **Capture `.slp` streams** — save the exact bytes a future embedded
  transport would send, for inspection and protocol reverse engineering.
- **REST API** — text, image/PDF, and raw-stream printing over HTTP with
  API-key auth, installable as a systemd service.
- **Documented protocol groundwork** — known command bytes and a
  reverse-engineering workflow in [docs/03_NATIVE_PROTOCOL.md](docs/03_NATIVE_PROTOCOL.md).

## Quickstart (Raspberry Pi / Debian Linux)

```bash
# 1. Install the driver toolchain (CUPS + open-source Seiko filter)
sudo ./scripts/install_driver.sh

# 2. Install the SDK
uv sync              # or: pip install .

# 3. Print, or capture the native stream without printing
uv run slp650 label.png --media AddressSmall --copies 1
uv run slp650 label.png --media AddressSmall --capture label.slp --dry-run

# 4. Optional: install the REST print agent (port 8787)
sudo ./scripts/install_api.sh
```

Full setup guide: [docs/08_RASPBERRY_PI.md](docs/08_RASPBERRY_PI.md).

## Python usage

```python
from pathlib import Path
from slp650_sdk import SLPConfig, print_file

config = SLPConfig(media="AddressSmall", density="MediumQuality")
print_file(Path("label.png"), config, copies=1, capture_path=Path("label.slp"))
```

More in [docs/06_PYTHON_SDK.md](docs/06_PYTHON_SDK.md).

## REST API

```bash
curl -X POST http://127.0.0.1:8787/print/text \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello from the SLP650", "media": "AddressSmall", "copies": 1}'
```

Endpoints: `GET /health`, `POST /print/text`, `POST /print/image`,
`POST /print/raw`. Details: [docs/07_REST_API.md](docs/07_REST_API.md).

## Repository layout

```
src/slp650_sdk/   Python package (rendering, encoder, transport, CLI, REST API)
scripts/          Raspberry Pi installers and raw-stream capture helper
systemd/          Service unit for the REST print agent
docs/             Architecture, hardware, protocol, and platform guides
tests/            Unit tests (no printer required)
```

## Documentation

| Doc | Contents |
|---|---|
| [01_ARCHITECTURE](docs/01_ARCHITECTURE.md) | Three-layer design and contributor rules |
| [02_HARDWARE](docs/02_HARDWARE.md) | Printer and USB interface facts |
| [03_NATIVE_PROTOCOL](docs/03_NATIVE_PROTOCOL.md) | Command bytes, open questions, discovery log |
| [04_LABEL_MEDIA](docs/04_LABEL_MEDIA.md) | Media names and pixel geometry |
| [05_RENDERING](docs/05_RENDERING.md) | Rendering rules and template plans |
| [06_PYTHON_SDK](docs/06_PYTHON_SDK.md) | Library and CLI usage |
| [07_REST_API](docs/07_REST_API.md) | HTTP endpoints and auth |
| [08_RASPBERRY_PI](docs/08_RASPBERRY_PI.md) | Reference platform setup |
| [09_EMBEDDED_TRANSPORT](docs/09_EMBEDDED_TRANSPORT.md) | Hardware-agnostic transport agent contract |
| [10_DEVELOPMENT](docs/10_DEVELOPMENT.md) | Dev setup, testing strategy, glossary, FAQ |

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

## Roadmap

See [ROADMAP.md](ROADMAP.md).

## License and credits

MIT (see [LICENSE](LICENSE)). The encoder currently invokes the GPL-licensed
open-source Seiko driver
([fawkesley/smart-label-printer-slp-linux-driver](https://github.com/fawkesley/smart-label-printer-slp-linux-driver))
as an external process; it is installed separately and is not part of this
package.
