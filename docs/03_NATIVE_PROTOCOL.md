# Native protocol

The SLP650 does **not** speak PostScript, PCL, or ESC/POS. It receives a
compact command stream on USB bulk OUT endpoint `0x01`.

**Status: decoded.** The protocol was reverse engineered on 2026-07-16 from
hardware captures cross-checked against the GPL driver source
(<https://github.com/fawkesley/smart-label-printer-slp-linux-driver>, files
`SeikoSLPCommands.h`, `RasterToSIISLP.cxx`, `SIISLPProcessBitmap.cxx`).
`slp650_sdk.protocol` implements a parser/decoder for it; see the discovery
log at the bottom for evidence.

## Command set

| Command | Byte | Arguments |
|---|---:|---|
| NOP | `0x00` | none |
| Status | `0x01` | none (response on bulk IN) |
| Version | `0x02` | none (response on bulk IN) |
| BaudRate | `0x03` | unknown (serial-era) |
| PrintRaster | `0x04` | `<len> <len raw bitmap bytes>` |
| PrintRLERaster | `0x05` | `<len> <len RLE bytes>` |
| Margin | `0x06` | 1 byte: left margin in **mm** |
| Repeat | `0x07` | none: reprint previous print command |
| Tab | `0x09` | 1 byte: leading white **dots** in the next line |
| LineFeed | `0x0A` | none: advance one blank line |
| VertTab | `0x0B` | 1 byte: advance N blank lines (max 255) |
| FormFeed | `0x0C` | none: end of label, feed and cut position |
| Speed | `0x0D` | 1 byte: `0x02` = fine mode, `0x00` = normal (SLP650) |
| Density | `0x0E` | 1 byte: signed; `0xF9` = 65%, `0x00` = 100%, `0x06` = 130% |
| Reset | `0x0F` | none |
| Model | `0x12` | unknown (response on bulk IN) |
| Indent | `0x16` | 1 byte: left margin in **dots** |
| FineMode | `0x17` | 1 byte (older models; the SLP650 uses Speed instead) |
| SetSerialNumber | `0x1B` | unknown |
| Check | `0xA5` | unknown |

## Job structure

```
06 <mm>          Margin        (mm ≈ dots / 23.622 at 300 dpi)
0E <density>     Density
0D <speed>       Speed         (this is how fine mode is set on the SLP650)
16 <dots>        Indent        ((576 - line_width) / 2, if it fits in ≤ 255)
<line stream>                  (see below)
0C               FormFeed      (end of label)
```

Both Margin and Indent are emitted by the driver: Margin by the filter's page
setup (mm, computed from `(576 - line_width + 7) / 23.622`), Indent by the
bitmap processor (dots, `(576 - line_width) / 2`; if that exceeds 255 it falls
back to a second Margin command in mm).

## Line stream

The label feeds lengthwise: each **raster line spans the printhead** (the
image's *short* axis, max 576 dots) and successive lines advance the paper
(the image's *long* axis). For an AddressSmall label the raster is 285 dots
per line, 984 lines. The across-the-head dot index runs opposite to the
image's y axis (dot ≈ `height - y`; exact edge behavior below).

Per line, front to back:

- **Blank line**: not printed. One blank line → `0A`; runs → `0B <n>`
  (repeated while n > 255). Blank lines after the last printed line are
  omitted entirely (FormFeed handles the rest).
- **Printed line**: optionally `09 <n>` (Tab) when the leading white run
  exceeds 126 dots (n ≤ 255; any remainder becomes RLE white runs), then
  either `04` (raw) or `05` (RLE) — the driver emits whichever is smaller.
- Trailing white in a line is never encoded (raw: trailing zero bytes
  stripped; RLE: trailing white runs stripped).

### PrintRaster (`0x04`) payload

`04 <byteCount> <bitmap>` — plain 1-bit bitmap, MSB first, 8 dots per byte.

### PrintRLERaster (`0x05`) payload

`05 <byteCount> <rle bytes>`, where each RLE byte is:

| Byte range | Meaning |
|---|---|
| `0x00`–`0x3F` | white run of *value* dots (0–63) |
| `0x40`–`0x7F` | black run of *value − 64* dots (0–63) |
| `0x80`–`0xFF` | literal chunk: bits 6..0 are 7 dots, MSB first |

Runs longer than 63 dots are split across bytes. The literal form is used for
runs shorter than 8 dots (it packs the next 7 dots verbatim).

### Repeat (`0x07`)

Reprints the previous print command. Present in the protocol, but the current
driver build never emits it (its last-command comparison buffer is never
populated) — confirmed by the hline capture: 984 identical lines, zero `07`
bytes. A future pure encoder can use it for significant savings on repetitive
labels.

## Density and speed values (SLP650)

From `RasterToSIISLP.cxx` and confirmed by capture:

| Option | Density byte |
|---|---|
| LowQuality (65%) | `0xF9` |
| MediumQuality (100%) | `0x00` |
| HighQuality (130%) | `0x06` |

Fine mode: `Speed 0x02` (fine) vs `Speed 0x00` (normal). **Gotcha:** the
filter detects the option by searching its options string for the literal
`noFinePrint`; `FinePrint=False` is silently ignored (this SDK passes the
correct CUPS boolean form).

## Tools

```bash
slp650-patterns --media AddressSmall --out fixtures/    # controlled test images
slp650 input.png --media AddressSmall --capture out.slp --dry-run   # capture
slp650-dump out.slp                                     # decoded, annotated dump
slp650-dump a.slp b.slp                                 # locate divergence
```

The parser (`slp650_sdk.protocol`) decodes both raster payload formats
(`decode_rle`, `decode_raster`) and collapses repeated line sequences, so even
multi-kilobyte captures dump to a few lines. New findings go into
`ARG_LENGTHS`/`COMMANDS` there, with the evidence logged below.

## Raster row-to-dot mapping (cupsfilter stage)

Capture-validated on AddressSmall (285 dots) and MediaBadge (567 dots):

- Image row `y` lands on printhead dot `height - y` (the across axis is the
  flipped image y axis).
- **Image row 0 maps to dot `height`, which is out of range, and is silently
  discarded.** Content must not rely on row 0 (the `border` pattern draws its
  top edge at row 1 for this reason).
- The bottom image row (`height - 1`) lands on dot 1 and bleeds onto dot 0
  (double strike), on both integer- and fractional-height media.
- Fractional dot heights are truncated (567.6 → 567); a canvas that does not
  match the truncated raster gets rescaled and loses additional edge rows.

This is behavior of the CUPS raster path, not of the printer: a pure encoder
that builds raster lines directly is free of it.

## Open questions

- Status (`0x01`) / Version (`0x02`) / Model (`0x12`) response formats on bulk
  IN endpoint `0x82`.
- Return-media geometry: the only capture used a mismatched (AddressSmall
  sized) input image, so its Margin/Indent values reflect scaled content, not
  the media. Re-capture with Return-sized patterns.
- Whether fine mode (`Speed 0x02`) changes anything physically beyond the one
  argument byte. A normal-mode border measured ~62 mm against 63.5 mm
  predicted at 300 lines/inch — possibly ruler imprecision, possibly a feed
  pitch difference; needs the same border printed in both modes and measured.

## Discovery log

### 2026-07-16 — header and geometry (hardware capture, SLP650, AddressSmall)

- All-white label is exactly 9 bytes: `06 0c 0e 00 0d 02 16 91 0c` → Margin
  12 mm, Density 0x00, Speed 0x02, Indent 145, FormFeed.
- Indent 145 = (576 − 285) / 2 → raster line width is 285 dots; Margin
  12 = (576 − 285 + 7) / 23.622 rounded down.
- Density captures: LowQuality → `0xF9`, HighQuality → `0x06` (matches driver
  source constants including the 65%/100%/130% comments).
- `--fine-print` produced an identical stream → traced to the filter's
  `noFinePrint` string matching; our option format was wrong (fixed in
  `SLPConfig.filter_options`).

### 2026-07-16 — raster encoding (hardware capture + driver source)

- vline (column at x=492): `0B ff 0B ed` = advance 255 + 237 = 492 blank
  lines, then one full-black line `05 05 7f 7f 7f 7f 61` = 63×4 + 33 = 285
  black dots. Confirms VertTab semantics and RLE black-run encoding.
- pixel at (16,16): `0B 10` (skip 16 lines) `09 ff` (tab 255) `05 02 0e c0`
  (white 14, literal 1 black + 6 white) → dot at 255 + 14 = 269 ≈ 285 − 16:
  across axis is the flipped image y.
- hline (row y=142): 984 repetitions of `09 8f 05 01 c0` → tab 143, one black
  dot. Confirms Tab is per-line and the driver does not use Repeat (`07`).
- black: 984 × `05 05 7f 7f 7f 7f 61`; border: full-black first/last lines,
  middle lines `04 01 c0` (raw wins over RLE for 2 edge dots); checkerboard:
  raw lines `04 23 fc 03 fc 03 ...` (35 bytes < RLE) — confirms the
  smaller-of-raw-or-RLE selection and trailing-white stripping.
- Command names/bytes for `0x03`, `0x09`, `0x0B`, `0x1B`, `0xA5` and the RLE
  byte ranges taken from driver source (`SeikoSLPCommands.h`,
  `SIISLPProcessBitmap.cxx::CompressRun`).

### 2026-07-16 — physical print of the border capture

- Printing `pattern_border_984x285.slp` on a larger-than-AddressSmall roll
  produced a box that overran onto the next label: the stream encodes
  absolute geometry (984 lines x 285 dots = 83.3 mm x 24.1 mm at 300 dpi) and
  the printer does not scale to the loaded media. Media selected at encode
  time must match the physically loaded roll.
- The printed box has only one long rail — physically confirming the capture
  analysis: cupsfilter clips the image's y=0 row out of the raster (border
  middle lines are `04 01 c0`, near edge only). The one-dot edge offset is
  real and visible in print.

### 2026-07-16 — MediaBadge (SLP-NWB) captures; model predictions confirmed

- White label header predicted from the spec and confirmed byte-for-byte:
  Margin 0 (`(576-567+7)/23.622` truncates to 0), Indent 4 (`(576-567)/2`).
- Fine-print A/B diff diverges at offset 0x5 only: Speed `00` vs `02` —
  confirms the Speed-as-fine-mode encoding and the `noFinePrint` fix.
- Border first line is `05 09` + 9 x `7f` = 567 black dots: **CUPS truncates
  fractional dot sizes** (136.224 pt = 567.6 → 567), it does not round. Our
  568-tall canvas was rescaled to 749 x 567 by cupsfilter, dropping the
  closing border edge — canvases must match the truncated raster exactly
  (`media_pixels` fixed accordingly).

### 2026-07-17 — edges diagnostic: row-to-dot mapping solved

`pattern_edges_750x567` on MediaBadge probes rows 0/1/565/566 with distinct
feed lengths (100%/75%/50%/25%). Capture segments:

| Feed lines | Black dots | Rows present |
|---|---|---|
| 0-186 | 0, 1, 2, 566 | all four |
| 187-374 | 2, 566 | 0, 1, 565 |
| 375-561 | 566 | 0, 1 |
| 562-749 | none | 0 only |

Conclusion: row y → dot `567 - y`; row 1 → 566, row 565 → 2, row 566 → dot 1
plus bleed onto dot 0; **row 0 → dot 567 (out of range) is discarded** — the
cause of every "missing rail" seen so far, matching the AddressSmall border
byte-for-byte (`04 01 c0`). Border pattern now draws its top edge at row 1.

### 2026-07-18 — four-edge border printed; feed length still reads short

- The row-1 border compensation works: all four edges printed on MediaBadge.
- Across-the-head size is exact (48.0 mm measured = 567 dots at 300 dpi).
- Feed length measured 62 mm twice against 63.5 mm predicted (750 lines at
  300 lines/inch) — a consistent ~2.4% shortfall in **normal mode**
  (`Speed 0x00`). Pending: print the same border with `--fine-print`
  (`Speed 0x02`) and measure; that decides between a mode-dependent feed
  pitch and a general mechanical shortfall.

*(append new entries here: date, input, observation, conclusion)*
