# REST API

A FastAPI print agent (`slp650_sdk.api`) intended to run on the host that has
the printer attached. Default port: **8787**.

Text and image printing use the built-in pure-Python encoder — no CUPS
required. The CUPS toolchain is needed only for PDF uploads, which fall back
to it automatically (responses carry an `engine` field: `native` or `cups`).

## Authentication

Every endpoint requires the `X-API-Key` header, checked against the
`SLP650_API_KEY` environment variable. If no key is configured the server
answers **503** to everything — it never runs open, because it binds to all
interfaces. `scripts/install_api.sh` generates a key into
`/etc/default/slp650-api`.

```bash
API_KEY='paste-the-key-here'
BASE=http://127.0.0.1:8787
```

## Endpoints

### `GET /health`

Reports printer availability; `ok` is true when the device is present.
`pdf_support` indicates whether the optional CUPS toolchain is installed.

```bash
curl -H "X-API-Key: $API_KEY" $BASE/health
```

### `POST /print/text`

Renders text host-side and prints it.

```bash
curl -X POST $BASE/print/text \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Hello from the SLP650",
    "media": "AddressSmall",
    "font_size": 44,
    "copies": 1
  }'
```

Body fields: `text` (required), `media`, `density`, `fine_print`, `copies`
(1–100), `font_size` (8–180), `margin` (0–200), `rotate` (0/90/180/270).

### `POST /print/image`

Prints an uploaded image or PDF (max 20 MiB). Images are fitted onto the
media canvas (aspect-preserving, centered, dithered to 1-bit) and encoded
natively; PDFs go through the CUPS pipeline.

```bash
curl -X POST $BASE/print/image \
  -H "X-API-Key: $API_KEY" \
  -F file=@label.png \
  -F media=AddressSmall \
  -F density=MediumQuality \
  -F copies=1
```

### `POST /print/raw`

Sends a previously captured native `.slp` stream verbatim.

```bash
curl -X POST $BASE/print/raw \
  -H "X-API-Key: $API_KEY" \
  -F file=@label.slp \
  -F copies=1
```

### `POST /print/template` *(planned)*

Data-driven template printing; see [05_RENDERING.md](05_RENDERING.md).

## Error codes

| Status | Meaning |
|---|---|
| 401 | Wrong or missing API key |
| 413 | Upload larger than 20 MiB |
| 422 | Invalid parameters (unknown media, empty upload, bad rotation, …) |
| 503 | No API key configured, or encoder/printer failure |
