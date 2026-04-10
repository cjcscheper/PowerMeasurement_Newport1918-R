"""Shared plotting API for Version 2 optical-pump / THz-probe analysis.

Centralizes 1D/2D/3D Matplotlib helpers and style conventions so figures remain
consistent across simulation scripts, fitting workflows, and THz-TDS
measurement analysis.
"""

from .plot_1d import plot_1d
from .plot_2d import plot_2d
from .plot_3d import plot_3d

__all__ = ["plot_1d", "plot_2d", "plot_3d"]
