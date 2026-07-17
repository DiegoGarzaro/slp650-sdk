#!/usr/bin/env bash
set -euo pipefail

INPUT=${1:?Usage: capture_raw.sh INPUT_FILE [OUTPUT.slp] [MEDIA]}
OUTPUT=${2:-label.slp}
MEDIA=${3:-AddressSmall}
PPD=${SLP650_PPD:-/opt/slp650/siislp650.ppd}
FILTER=${SLP650_FILTER:-/usr/lib/cups/filter/seikoslp.rastertolabel}

TMP=$(mktemp --suffix=.raster)
trap 'rm -f "$TMP"' EXIT

cupsfilter \
  -p "$PPD" \
  -m application/vnd.cups-raster \
  -o "PageSize=$MEDIA" \
  -o Resolution=300dpi \
  "$INPUT" > "$TMP"

PPD="$PPD" "$FILTER" \
  1 "${USER:-slp650}" "$(basename "$INPUT")" 1 \
  "PageSize=$MEDIA Density=MediumQuality FinePrint=False Resolution=300dpi" \
  "$TMP" > "$OUTPUT"

printf 'Captured %s bytes in %s\n' "$(stat -c %s "$OUTPUT")" "$OUTPUT"
printf 'First 128 bytes:\n'
xxd -g 1 -l 128 "$OUTPUT"
