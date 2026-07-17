"""Printer configuration and label media geometry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Printhead resolution of the SLP650/SLP650SE.
DPI = 300

#: Dots across the printhead. Every rendered label is at most this wide.
PRINTHEAD_DOTS = 576

#: Label media sizes in PostScript points (1/72 inch), from the PPD's
#: fractional PaperDimension entries (dot-exact at 300 dpi, unlike the
#: integer PageSize values). The PPD supports more sizes; add them here
#: after validating the raster dimensions with a capture.
MEDIA_POINTS: dict[str, tuple[float, float]] = {
    "AddressSmall": (236.16, 68.40),
    "AddressLarge": (236.16, 98.64),
    "MediaBadge": (180.00, 136.224),  # name badges: SLP-NB, SLP-NR, SLP-NWB
    "MultiPurpose": (126.00, 68.40),
    "Return": (122.40, 45.00),
    "Shipping": (271.44, 136.224),
}


def media_pixels(media: str, dpi: int = DPI) -> tuple[int, int]:
    """Convert a named media size to a pixel canvas.

    Args:
        media (str): Media name, one of ``MEDIA_POINTS``.
        dpi (int): Target resolution in dots per inch.

    Returns:
        tuple[int, int]: Canvas size as ``(width, height)`` in pixels.

    Raises:
        ValueError: If ``media`` is not a known media name.
    """
    try:
        width_points, height_points = MEDIA_POINTS[media]
    except KeyError:
        raise ValueError(
            f"Unsupported media {media!r}; use one of {sorted(MEDIA_POINTS)}"
        ) from None
    return round(width_points * dpi / 72), round(height_points * dpi / 72)


@dataclass(frozen=True)
class SLPConfig:
    """Paths and print options for one printer.

    Attributes:
        ppd_path (Path): PPD file describing the printer to CUPS tools.
        filter_path (Path): Seiko ``rastertolabel`` filter binary.
        device_path (Path): Character device of the printer (usblp).
        lock_path (Path): Lock file serializing access to the device.
        media (str): Label media name, e.g. ``AddressSmall``.
        density (str): Print density (``LowQuality``/``MediumQuality``/``HighQuality``).
        fine_print (bool): Enable the printer's fine mode.
    """

    ppd_path: Path = Path("/opt/slp650/siislp650.ppd")
    filter_path: Path = Path("/usr/lib/cups/filter/seikoslp.rastertolabel")
    device_path: Path = Path("/dev/usb/lp0")
    lock_path: Path = Path("/run/lock/slp650.lock")
    media: str = "AddressSmall"
    density: str = "MediumQuality"
    fine_print: bool = False

    @property
    def filter_options(self) -> str:
        """CUPS option string passed to the Seiko raster filter.

        The filter detects fine mode by searching the option string for the
        literal ``noFinePrint`` (CUPS boolean-option style); a ``key=value``
        form like ``FinePrint=False`` is ignored and leaves fine mode on.

        Returns:
            str: Space-separated CUPS options.
        """
        fine = "FinePrint" if self.fine_print else "noFinePrint"
        return (
            f"PageSize={self.media} "
            f"Density={self.density} "
            f"{fine} "
            "Resolution=300dpi"
        )

    @classmethod
    def from_env(
        cls,
        media: str = "AddressSmall",
        density: str = "MediumQuality",
        fine_print: bool = False,
    ) -> SLPConfig:
        """Build a config from ``SLP650_*`` environment variables.

        Args:
            media (str): Label media name.
            density (str): Print density option.
            fine_print (bool): Enable fine mode.

        Returns:
            SLPConfig: Configuration with env overrides applied.
        """
        defaults = cls()
        return cls(
            ppd_path=Path(os.getenv("SLP650_PPD", str(defaults.ppd_path))),
            filter_path=Path(os.getenv("SLP650_FILTER", str(defaults.filter_path))),
            device_path=Path(os.getenv("SLP650_DEVICE", str(defaults.device_path))),
            lock_path=Path(os.getenv("SLP650_LOCK", str(defaults.lock_path))),
            media=media,
            density=density,
            fine_print=fine_print,
        )
