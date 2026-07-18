# Integration guide

How to print labels from your own application, and how to extend the SDK
with your own templates.

There are two integration surfaces:

1. **REST API** — language-agnostic, over the network. Best when the printer
   is attached to a Pi/print server and your app runs elsewhere.
2. **Python library** — in-process. Best for Python apps running on the host
   with the printer, or apps that only need to *generate* `.slp` streams.

## 1. REST API integration

Authentication: every request needs the `X-API-Key` header (key lives in
`/etc/default/slp650-api` on the print server). All endpoints are documented
in [07_REST_API.md](07_REST_API.md); interactive OpenAPI docs are served at
`http://<host>:8787/docs`.

### Discover templates

```bash
curl -H "X-API-Key: $API_KEY" http://<host>:8787/templates
```

```json
[
  {
    "name": "visitor-badge",
    "description": "Name badge with optional company line and QR code",
    "default_media": "MediaBadge",
    "required_fields": ["name"],
    "optional_fields": ["company", "qr_data"]
  }
]
```

### Print a template

```bash
curl -X POST http://<host>:8787/print/template \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{
    "template": "visitor-badge",
    "fields": {
      "name": "Diego Garzaro",
      "company": "ACME Corp",
      "qr_data": "https://example.com/visitor/42"
    },
    "copies": 1
  }'
```

Python example:

```python
import requests

response = requests.post(
    "http://printserver:8787/print/template",
    headers={"X-API-Key": API_KEY},
    json={"template": "shipping", "fields": {"to": "...", "barcode_data": "PKG-42"}},
    timeout=30,
)
response.raise_for_status()
```

If none of the templates fit, render the label yourself and use
`POST /print/image` (any image format Pillow reads; it is fitted onto the
media canvas), or send raw text via `POST /print/text`.

### Error handling

| Status | Meaning | Typical fix |
|---|---|---|
| 401 | Bad API key | Check `X-API-Key` |
| 404 | Unknown template | `GET /templates` for valid names |
| 422 | Missing fields / unknown media / bad params | Read `detail` |
| 503 | Printer offline or not configured | Check `GET /health` |

## 2. Python library integration

```python
from PIL import Image
from slp650_sdk import SLPConfig, encode_image, send_native_stream
from slp650_sdk.templates import render_template

image = render_template("visitor-badge", {"name": "Diego"})
data = encode_image(image)                       # pure Python, any OS
send_native_stream(data, SLPConfig(), copies=1)  # Linux host with the printer
```

`encode_image` works anywhere, so a backend can generate `.slp` payloads and
ship them to whatever transport reaches the printer (the Pi's
`POST /print/raw`, or a future embedded agent — see
[09_EMBEDDED_TRANSPORT.md](09_EMBEDDED_TRANSPORT.md)).

## 3. Writing your own template

A template is a name, a field contract, and a renderer function that turns
validated fields plus a canvas size into a 1-bit PIL image:

```python
from PIL import Image, ImageDraw

from slp650_sdk.codes import qr_image
from slp650_sdk.templates import Template, draw_fitted_text, register_template

def render_asset_tag(fields, canvas):
    width, height = canvas
    image = Image.new("L", canvas, 255)
    draw = ImageDraw.Draw(image)
    margin = height // 12

    qr_size = height - 2 * margin
    image.paste(
        qr_image(fields["asset_url"], qr_size).convert("L"),
        (width - margin - qr_size, margin),
    )
    draw_fitted_text(
        draw,
        fields["asset_id"],
        (margin, margin, width - 2 * margin - qr_size, height - margin),
        max_font_size=height // 3,
        bold=True,
        valign="middle",
    )
    return image.convert("1", dither=Image.Dither.NONE)

register_template(Template(
    name="asset-tag",
    description="Asset ID with QR link",
    default_media="MultiPurpose",
    required_fields=("asset_id", "asset_url"),
    optional_fields=(),
    renderer=render_asset_tag,
))
```

Once registered, the template works everywhere — `render_template()` locally,
and `GET /templates` / `POST /print/template` if the module registering it is
imported by the API process (e.g. from a small wrapper module that imports
`slp650_sdk.api` after registering your templates, pointed to by uvicorn).

### Rules and guidance for template authors

- **Canvas comes from the media**: your renderer receives `(width, height)`
  from `media_pixels(media)`; x is the feed direction, y spans the printhead
  (max 576 dots). Don't hardcode sizes — derive margins and font sizes from
  the canvas so the template works on more than one media.
- **Render everything host-side**: text, QR codes, and barcodes are pixels by
  the time they reach the encoder. Use `slp650_sdk.codes.qr_image` /
  `code128_image`; never assume printer fonts.
- **Finish with `convert("1", dither=Image.Dither.NONE)`** for text/codes;
  reserve Floyd–Steinberg dithering for photos.
- **Auto-fit text** with `draw_fitted_text` instead of fixed font sizes —
  field values vary in length, and clipped labels are worse than smaller
  text.
- **Mind physical accuracy**: the feed axis prints ~2% short mechanically
  (docs/03, discovery log). For scannable barcodes, prefer placing bars
  *across* the feed (as the built-in shipping template does) and always
  verify a printed label with a real scanner.
- **Test without hardware**: assert the rendered image size/mode in unit
  tests, and inspect encoded output with
  `slp650 label.png --native --dry-run --capture out.slp` + `slp650-dump out.slp`.
- Media geometry references: [04_LABEL_MEDIA.md](04_LABEL_MEDIA.md); protocol
  details: [03_NATIVE_PROTOCOL.md](03_NATIVE_PROTOCOL.md).
