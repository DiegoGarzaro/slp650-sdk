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

## Template engine

`slp650_sdk.templates` provides data-driven layouts
(`template name + field values -> bitmap`), exposed over
`GET /templates` + `POST /print/template` and extensible by applications via
`register_template()` — see [11_INTEGRATION_GUIDE.md](11_INTEGRATION_GUIDE.md).

Built-in templates:

| Name | Media | Required | Optional |
|---|---|---|---|
| `address` | AddressSmall | `address` | — |
| `asset-tag` | MultiPurpose | `asset_id` | `owner`, `qr_data` |
| `inventory` | MultiPurpose | `item` | `sku`, `quantity`, `location` |
| `photo` | MediaBadge | `image_base64` | `caption` |
| `shipping` | Shipping | `to` | `from`, `barcode_data` |
| `visitor-badge` | MediaBadge | `name` | `company`, `qr_data` |

QR codes (`slp650_sdk.codes.qr_image`) and Code 128 barcodes
(`code128_image`) are rendered host-side as 1-bit images, per the rules
above. The `photo` template takes a base64-encoded image (optionally as a
`data:` URI) and dithers it with Floyd–Steinberg.
