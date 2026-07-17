# Development

## Setup

```bash
uv sync          # creates .venv with runtime + dev dependencies
```

## Quality gates

Run before every commit:

```bash
uv run ruff check .    # lint (auto-fix: uv run ruff check . --fix)
uv run pytest          # unit tests
```

## Conventions

- Python ≥ 3.11, `uv` for dependency management.
- One responsibility per module; keep the Renderer/Encoder/Transport layers
  independent ([01_ARCHITECTURE.md](01_ARCHITECTURE.md)).
- Google-style docstrings with typed `Args:`/`Returns:`/`Raises:` sections.
- Every feature ships with tests.

## Testing strategy

- **Unit tests** (in `tests/`) cover geometry, rendering, config, and API
  validation — they run anywhere, no printer or CUPS needed.
- **Golden fixtures** (planned): pairs of `input.png` → `expected.slp` captured
  on real hardware. The future pure-Python encoder must reproduce the captured
  streams byte-for-byte. Capture fixtures with:

  ```bash
  ./scripts/capture_raw.sh fixtures/checkerboard.png fixtures/checkerboard.slp AddressSmall
  ```

- **Hardware smoke test**: `slp650 label.png --dry-run --capture out.slp` on a
  machine with the CUPS toolchain, then a real print.

## Glossary

| Term | Meaning |
|---|---|
| Direct thermal | Printing by heating thermochromic label stock — no ink/toner |
| Raster | Row-by-row 1-bit bitmap data as sent to the printhead |
| USB Printer Class | USB device class 7; bulk OUT for data, bulk IN for status |
| DPI | Dots per inch; the SLP650 prints at 300 dpi |
| PPD | PostScript Printer Description — CUPS printer capability file |
| `.slp` stream | This project's name for the captured printer-native byte stream |
| CUPS raster | Intermediate 1-bit page format produced by `cupsfilter` |

## FAQ

**Why does the encoder still depend on CUPS?**
The Seiko GPL filter is the only known-correct implementation of the native
protocol. It is used as a black-box converter (via `subprocess`) until the
protocol is fully documented and reimplemented (see
[03_NATIVE_PROTOCOL.md](03_NATIVE_PROTOCOL.md)).

**Can this print from macOS/Windows?**
Rendering works anywhere; encoding currently requires the Linux CUPS
toolchain. The portable encoder milestone removes that restriction.

**Why MIT-licensed if the driver is GPL?**
The GPL driver is invoked as an external process and installed separately by
`scripts/install_driver.sh`; no GPL code is linked into or shipped with this
package.
