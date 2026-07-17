# Embedded transport agents

The transport layer can be any device capable of acting as a **USB host** for
a USB Printer Class device. ESP32-S3 was the first candidate, but the design
is hardware-agnostic — RP2040/RP2350, STM32, other MCUs with USB-OTG/host
support, or a small Linux SBC all fit the same contract.

## Contract

A transport agent is deliberately dumb. It does **not** render or encode:

1. The backend renders the label and generates the native `.slp` stream
   (see [03_NATIVE_PROTOCOL.md](03_NATIVE_PROTOCOL.md)).
2. The agent receives that stream over the network (MQTT, HTTPS, or similar).
3. The agent enumerates the printer as USB Printer Class (device
   `VID:PID 0619:0126`) and claims interface 0.
4. It writes the stream in chunks to bulk OUT endpoint `0x01`.
5. It reports job completion or USB errors back to the backend
   (status responses arrive on bulk IN endpoint `0x82`).

Because the payload is opaque bytes, a transport agent written today keeps
working as the encoder evolves.

## Validation path

Before writing firmware, validate payloads on Linux: a captured `.slp` file
that prints correctly via `cat label.slp > /dev/usb/lp0` is a known-good
fixture for the embedded implementation.

## Candidate platforms

| Platform | USB host support | Notes |
|---|---|---|
| ESP32-S3 | TinyUSB host / ESP-IDF `usb_host` | Wi-Fi built in; original candidate |
| RP2040 / RP2350 | PIO-USB or native (RP2350) | Cheap; needs external network |
| STM32 (F4/H5/H7) | USB-OTG host | Mature HAL printer-class support |
| Linux SBC (Pi Zero 2 W, …) | Kernel `usblp` | Easiest: reuse this SDK directly |

## Standalone rendering (later)

Only after several captured `.slp` files are documented should on-device
rendering be considered. The remaining bitmap packet format can then be
specified from the discovery log and implemented portably (see the C/C++ core
milestone in [ROADMAP.md](../ROADMAP.md)). Until then, agents stay
transport-only.
