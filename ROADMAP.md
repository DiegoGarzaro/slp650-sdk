# Roadmap

## Milestone 0 — Linux reference implementation ✅

- [x] Direct printing without a CUPS queue (`slp650` CLI)
- [x] Native `.slp` stream capture for inspection and fixtures
- [x] REST print agent (text / image / raw) with API-key auth
- [x] Raspberry Pi installers + systemd service
- [x] Python package (`slp650_sdk`) with renderer/encoder/transport split
- [x] Unit tests and lint gates

## Milestone 1 — Native protocol documentation

- [x] Test-pattern generator (`slp650-patterns`)
- [x] Stream disassembler and diff tool (`slp650-dump`)
- [x] Build a corpus of captured `.slp` streams from controlled test images
- [x] Document command argument encodings in docs/03_NATIVE_PROTOCOL.md
- [x] Decode the raster (`0x04`) and RLE raster (`0x05`) payload formats
      (both implemented in `slp650_sdk.protocol`)
- [x] Map the exact image-to-dot edge geometry (row y → dot height−y; row 0
      is discarded by the CUPS raster path)
- [ ] Understand status responses on bulk IN endpoint `0x82`
- [ ] Golden fixtures: `input.png -> expected.slp` pairs checked into tests

## Milestone 2 — Pure-Python encoder

- [x] Reimplement the encoder from the documented protocol (no CUPS
      dependency): `slp650_sdk.native_encoder`, `slp650 --native`
- [x] Byte-for-byte parity with golden fixtures (all AddressSmall patterns,
      density variants, and MediaBadge captures)
- [x] Encoder works on any OS (macOS/Windows included)
- [x] Use the native encoder in the REST API text/image endpoints (CUPS
      remains as the PDF fallback)

## Milestone 3 — Template engine

- [ ] Declarative templates: Address, Shipping, Inventory, Asset, Visitor Badge, Photo
- [ ] Barcode/QR generation (rendered as images)
- [ ] `POST /print/template` REST endpoint

## Milestone 4 — Embedded transport agents

- [ ] Reference firmware for a USB-host MCU (candidate: ESP32-S3; the contract
      is hardware-agnostic — see docs/09_EMBEDDED_TRANSPORT.md)
- [ ] Job delivery over MQTT and/or HTTPS
- [ ] Job status reporting back to the backend

## Milestone 5 — Cross-platform core

- [ ] Portable C/C++ encoder library (`libslp650`) built from the documented protocol
- [ ] Bindings/ports for embedded targets that want standalone rendering
