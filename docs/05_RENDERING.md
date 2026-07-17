# Rendering

## Rules

1. **Always render to a monochrome bitmap host-side.** The printer receives
   raster data only.
2. **Never rely on printer fonts.** Text is drawn with host fonts (DejaVu Sans
   or Liberation Sans on Raspberry Pi OS; PIL's built-in font as fallback).
3. **QR codes and barcodes are images.** Generate them with a host library and
   composite them onto the label bitmap.
4. Dithering: grayscale content is converted to 1-bit with Floyd–Steinberg
   dithering after autocontrast (`slp650_sdk.rendering`).

## Current renderer

`slp650_sdk.rendering.render_text_label()` renders centered, word-wrapped text
onto a canvas sized by media name, with optional rotation (0/90/180/270°),
then saves a 1-bit PNG. It backs the REST API's `POST /print/text` endpoint.

## Template engine (planned)

A declarative template layer on top of the renderer, with built-in layouts:

- Address
- Shipping (with barcode)
- Inventory
- Asset tag (with QR)
- Visitor badge
- Photo

Templates should be data-driven (`template name + field values -> bitmap`) so
the REST API can expose `POST /print/template` and embedded clients can request
prints without doing any layout themselves. See [ROADMAP.md](../ROADMAP.md).
