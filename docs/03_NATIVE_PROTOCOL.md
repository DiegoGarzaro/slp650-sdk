# Native protocol

The SLP650 does **not** speak PostScript, PCL, or ESC/POS. The open-source
Linux driver converts a 1-bit CUPS raster page into a compact Seiko-native
command stream and writes it to USB bulk OUT endpoint `0x01`.

Source of truth so far: the GPL driver at
<https://github.com/fawkesley/smart-label-printer-slp-linux-driver>.

## Known command bytes

| Command | Byte |
|---|---:|
| NOP | `0x00` |
| Status | `0x01` |
| Version | `0x02` |
| Print raster | `0x04` |
| Print RLE raster | `0x05` |
| Margin | `0x06` |
| Repeat | `0x07` |
| Line feed | `0x0A` |
| Form feed | `0x0C` |
| Speed | `0x0D` |
| Density | `0x0E` |
| Reset | `0x0F` |
| Model | `0x12` |
| Indent | `0x16` |
| Fine mode | `0x17` |

## Page structure (as emitted by the driver)

At page start the driver sends **margin**, **density**, and **speed** settings,
then emits the raster payload via its bitmap processor. For the SLP650/650SE it
uses 576 dots across the printhead at 300 dpi.

## Open questions (to be reverse engineered)

- Exact argument encoding for each command (lengths, endianness).
- The raster line format for `0x04` and the RLE scheme for `0x05`.
- Status byte semantics on bulk IN endpoint `0x82`.
- Behavior of `Repeat` vs. host-side stream repetition for copies.

## Reverse-engineering workflow

The SDK ships two tools for this (`slp650_sdk.patterns`, `slp650_sdk.protocol`):

1. Generate the controlled test images — each isolates one visual variable
   (all-white, single pixel, one line, checkerboard, …):

   ```bash
   slp650-patterns --media AddressSmall --out fixtures/
   ```

2. Capture each pattern's native stream without printing:

   ```bash
   slp650 fixtures/pattern_white_984x285.png --media AddressSmall \
     --capture fixtures/pattern_white_984x285.slp --dry-run
   # or: ./scripts/capture_raw.sh input.png output.slp AddressSmall
   ```

   Also capture one fixed image while varying a single option at a time
   (`--density`, `--fine-print`, `--media`, `--copies`) to isolate the
   settings commands.

3. Inspect a stream with the annotated disassembler (or raw `xxd -g 1`):

   ```bash
   slp650-dump fixtures/pattern_white_984x285.slp
   ```

4. Diff two captures that differ by one variable — the diverging bytes encode
   that variable:

   ```bash
   slp650-dump white.slp pixel.slp
   ```

5. **Record every discovery and experiment in this file** — captured input,
   observed bytes, and conclusion — so the pure encoder can be written from
   documented facts.

6. Once a command's argument encoding is confirmed, add its byte count to
   `ARG_LENGTHS` in `src/slp650_sdk/protocol.py` — the dumps become more
   accurate with each confirmed command.

> **Note:** `slp650-dump` tokenization is heuristic until argument lengths are
> confirmed: a byte inside an undecoded payload that matches a command value
> is labeled as a command. Trust offsets and diffs; treat labels inside raster
> data with suspicion.

## Discovery log

*(append entries here: date, input, observation, conclusion)*
