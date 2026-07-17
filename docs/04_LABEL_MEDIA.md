# Label media

All geometry derives from the printhead: **576 dots wide at 300 dpi**.

## Supported media names

Sizes come from the Seiko PPD in PostScript points (1/72 inch) and are defined
in `slp650_sdk.config.MEDIA_POINTS`. Pixel canvases are computed at 300 dpi via
`slp650_sdk.config.media_pixels()`.

| Media | Roll (physical) | Points (w × h) | Pixels at 300 dpi (w × h) |
|---|---|---|---|
| `AddressSmall` | SLP-1RL/2RL, 89×28 mm | 236.16 × 68.40 | 984 × 285 |
| `AddressLarge` | SLP-2RLE, 89×36 mm | 236.16 × 98.64 | 984 × 411 |
| `MediaBadge` | SLP-NB/NR/NWB, 70×54 mm | 180.00 × 136.224 | 750 × 568 |
| `MultiPurpose` | SLP-MRL, 51×28 mm | 126.00 × 68.40 | 525 × 285 |
| `Return` | SLP-RTN, 45×19 mm | 122.40 × 45.00 | 510 × 188 |
| `Shipping` | SLP-SRL, 101×54 mm | 271.44 × 136.224 | 1131 × 568 |

The point values are the PPD's fractional `PaperDimension` entries (printable
area), which are smaller than the physical label — e.g. `MediaBadge` prints
63.5 × 48.1 mm on the 70 × 54 mm badge. AddressSmall is capture-validated
(984 × 285 confirmed on hardware); validate other media the same way before
relying on exact dot geometry.

Note: labels feed with their **short edge across the printhead**, which is why
the height (≤ 576) is the constrained dimension while the width can exceed 576.
The renderer produces the canvas in reading orientation; the CUPS raster stage
handles orientation for the printhead.

## Custom canvases

When designing labels as raw images, useful starting canvases are
`576×300`, `576×900`, and `576×1500` (printhead-width strips of increasing
length).

## Adding a new media size

1. Add the point dimensions to `MEDIA_POINTS` in `src/slp650_sdk/config.py`
   (they must match a `PageSize` the PPD accepts).
2. Add a test in `tests/test_config.py`.
3. Print a test label and verify physical alignment before relying on it.
