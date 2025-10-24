"""Utilities for accessing the installed semcode version."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources


_PACKAGE_NAME = "semcode"
_VERSION_FILENAME = "VERSION"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the current semcode version string."""
    try:
        version_file = resources.files(_PACKAGE_NAME).joinpath(_VERSION_FILENAME)
        return version_file.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, ModuleNotFoundError):
        return "unknown"


__all__ = ["get_version", "__version__"]

__version__ = get_version()
