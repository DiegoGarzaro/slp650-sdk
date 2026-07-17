# Architecture

## Vision

Build a **portable SDK** for the Seiko SLP650/SLP650SE, not just a Linux driver.
The design goal is a strict three-layer split:

```
┌────────────┐     ┌────────────┐     ┌────────────┐
│  Renderer  │ --> │  Encoder   │ --> │ Transport  │
└────────────┘     └────────────┘     └────────────┘
 content to         bitmap to          bytes to
 1-bit bitmap       native .slp        the printer
                    byte stream
```

- **Renderer** — turns label content (text, images, templates, barcodes) into a
  monochrome bitmap sized for the target media. Runs on any host with Pillow.
- **Encoder** — turns the bitmap into the printer-native SLP command stream
  (see [03_NATIVE_PROTOCOL.md](03_NATIVE_PROTOCOL.md)). Today this is done by
  the open-source Seiko CUPS filter; the goal is a pure, portable encoder.
- **Transport** — delivers the byte stream to the printer's USB bulk OUT
  endpoint. Implementations can be a Linux `usblp` device write (current), an
  embedded USB host (ESP32-S3, RP2040, STM32, …), or any future carrier. See
  [09_EMBEDDED_TRANSPORT.md](09_EMBEDDED_TRANSPORT.md).

The layers communicate through plain data (PNG bitmaps, `.slp` byte streams),
so each can be replaced independently. A captured `.slp` file printed today
through `/dev/usb/lp0` is byte-for-byte the same payload an embedded transport
would send.

## Module map

| Layer | Module | Responsibility |
|---|---|---|
| Renderer | `slp650_sdk.rendering` | Text → 1-bit PNG (fonts, wrapping, rotation) |
| Encoder | `slp650_sdk.encoder` | Document → native `.slp` stream (via CUPS filter, for now) |
| Transport | `slp650_sdk.transport` | `.slp` stream → `/dev/usb/lp0`, with locking |
| Shared | `slp650_sdk.config` | Paths, media geometry, print options |
| Interfaces | `slp650_sdk.cli`, `slp650_sdk.api` | Command line and REST front ends |

## Rules for contributors (human or AI)

1. Renderer, Encoder, and Transport must remain independent — no layer may
   import "upward" or reach around its neighbor.
2. The printable width is fixed: **576 dots at 300 dpi**. Never assume printer
   fonts or printer-side scaling exist.
3. Render everything host-side: text, QR codes, and barcodes are images by the
   time they reach the encoder.
4. One responsibility per module.
5. Every feature ships with tests (see [10_DEVELOPMENT.md](10_DEVELOPMENT.md)).
6. Record every protocol discovery in [03_NATIVE_PROTOCOL.md](03_NATIVE_PROTOCOL.md).

## Suggested reading order

[02_HARDWARE](02_HARDWARE.md) → [03_NATIVE_PROTOCOL](03_NATIVE_PROTOCOL.md) →
[04_LABEL_MEDIA](04_LABEL_MEDIA.md) → [05_RENDERING](05_RENDERING.md) →
[06_PYTHON_SDK](06_PYTHON_SDK.md) → [07_REST_API](07_REST_API.md) →
[08_RASPBERRY_PI](08_RASPBERRY_PI.md) → [09_EMBEDDED_TRANSPORT](09_EMBEDDED_TRANSPORT.md)
