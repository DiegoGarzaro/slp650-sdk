# Hardware

## Printer

| Property | Value |
|---|---|
| Model | Seiko Smart Label Printer 650 / 650SE |
| USB VID:PID | `0619:0126` |
| Print technology | Direct thermal (no ink or toner) |
| Resolution | 300 dpi |
| Printhead width | 576 dots (≈ 48.8 mm printable) |

## USB interface

The printer enumerates as **USB Printer Class 7, subclass 1, protocol 2**
(bidirectional):

| Endpoint | Direction | Purpose |
|---|---|---|
| `0x01` | Bulk OUT | Native SLP command stream (print data) |
| `0x82` | Bulk IN | Status responses |

On Linux the `usblp` kernel module exposes the printer as `/dev/usb/lp0`.
Writing a valid native stream to that device prints a label — no CUPS queue
required:

```bash
cat label.slp > /dev/usb/lp0
```

Verify detection:

```bash
lsusb -d 0619:0126
ls -l /dev/usb/lp0
```

## Consumables

Direct thermal label rolls; see [04_LABEL_MEDIA.md](04_LABEL_MEDIA.md) for the
supported media names and their pixel geometry.
