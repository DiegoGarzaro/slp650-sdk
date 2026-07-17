"""Exception types shared across the SDK."""

from __future__ import annotations


class SLPError(RuntimeError):
    """Raised when rendering, encoding, or printing fails."""
