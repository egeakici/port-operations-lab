from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("berth-allocation-lab")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]

