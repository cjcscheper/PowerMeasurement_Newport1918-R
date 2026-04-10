"""Reusable 2D plotting helper for heatmaps and contour overlays.

Designed for frequency-delay maps, parametric sweeps, and other 2D fields with
optional contour overlays and colorbar configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Sequence, Union
import warnings

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.colors import LogNorm, Normalize
from matplotlib.ticker import AutoMinorLocator
import numpy as np
from numpy.typing import ArrayLike

script_dir = Path(__file__).resolve().parent
style_file_path = script_dir / "cjc_style.mplstyle"
if style_file_path.exists():
    plt.style.use(style_file_path)
else:
    warnings.warn(
        f"Style file {style_file_path} not found. Using default matplotlib style.",
        UserWarning,
        stacklevel=2,
    )


def plot_2d(
    x_data: ArrayLike,
    y_data: ArrayLike,
    z_data: ArrayLike,
    xlabel: str = "",
    ylabel: str = "",
    title: str = "",
    cbar_label: str = "",
    xlim: Optional[tuple[float, float]] = None,
    ylim: Optional[tuple[float, float]] = None,
    cmap: str = "inferno",
    shading: Optional[Literal["flat", "nearest", "gouraud", "auto"]] = "auto",
    aspect: Union[Literal["auto", "equal"], float] = "auto",
    fig_show: bool = True,
    save_path: Optional[str] = None,
    fig_textwidth_pt: float = 497.0,
    fig_aspect_ratio: tuple[float, float] = (1 / 2, 1 / 2),
    minor_tick_count: int = 1,
    xticks_pos: Optional[list[float]] = None,
    xticks_labels: Optional[list[str]] = None,
    yticks_pos: Optional[list[float]] = None,
    yticks_labels: Optional[list[str]] = None,
    grid_show: bool = False,
    cbar_show: bool = True,
    cbar_pad: float = 0.02,
    cbar_shrink: float = 1.0,
    cbar_aspect: float = 25,
    cbar_ticks: Optional[Sequence[float]] = None,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    norm: Optional[Normalize] = None,
    alpha: float = 0.92,
    logx: bool = False,
    logy: bool = False,
    logcbar: bool = False,
    contour: bool = False,
    contour_levels: Optional[Union[int, list[float]]] = 10,
    contour_cmap: Optional[str] = None,
    contour_linewidths: float = 1.0,
    contour_labels: bool = False,
) -> tuple[Figure, Axes]:
    """Render a 2D colormap (pcolormesh) with optional contour overlays.

    Parameters
    ----------
    x_data, y_data : array-like
        1D coordinate arrays or 2D meshgrids matching z_data.
    z_data : array-like
        2D array of shape (len(y_data), len(x_data)) if x/y are 1D.
    xlabel, ylabel, title : str, optional
        Axis labels and plot title.
    cbar_label : str, optional
        Colorbar label.
    xlim, ylim : tuple[float, float], optional
        Axis limits (min, max).
    cmap : str, default "inferno"
        Colormap name for the heatmap.
    shading : {"flat", "nearest", "gouraud", "auto"}, optional
        Matplotlib pcolormesh shading mode.
    aspect : {"auto", "equal"} or float, default "auto"
        Aspect ratio for the axes.
    fig_show : bool, default True
        Whether to show the figure.
    save_path : str, optional
        If provided, figure is saved to this path.
    fig_textwidth_pt : float
        LaTeX text width in points (default 497 pt).
    fig_aspect_ratio : tuple(float, float)
        Width and height relative to LaTeX textwidth.
    minor_tick_count : int
        Number of minor ticks between major ticks.
    xticks_pos, yticks_pos : list[float], optional
        Explicit tick locations.
    xticks_labels, yticks_labels : list[str], optional
        Tick labels matching the above.
    grid_show : bool, default False
        Whether to show grid lines.
    cbar_show : bool, default True
        Whether to show the colorbar.
    cbar_pad : float, default 0.02
        Padding between plot and colorbar.
    cbar_shrink : float, default 1.0
        Fraction by which to shrink the colorbar.
    cbar_aspect : float, default 25
        Aspect ratio for the colorbar.
    cbar_ticks : sequence[float], optional
        Explicit colorbar tick positions.
    vmin, vmax : float, optional
        Colormap data range limits.
    norm : matplotlib.colors.Normalize, optional
        Explicit normalization instance to override vmin/vmax.
    alpha : float, default 0.92
        Alpha value for the heatmap.
    logx, logy : bool, default False
        Whether to use logarithmic axis scaling.
    logcbar : bool, default False
        Whether to use logarithmic normalization for the colormap/colorbar.
    contour : bool, default False
        If True, overlay contour lines.
    contour_levels : int or list, optional
        Number of contour levels or explicit values.
    contour_cmap : str or None
        Colormap for contour lines. If None → uses original colormap.
    contour_linewidths : float
        Line width for contour lines.
    contour_labels : bool
        If True, label the contour lines.

    Returns
    -------
    matplotlib.figure.Figure, matplotlib.axes.Axes
        Figure and axes for further customization.
    """

    x_array = np.asarray(x_data)
    y_array = np.asarray(y_data)
    z_array = np.asarray(z_data)

    if z_array.ndim != 2:
        raise ValueError("z_data must be a 2D array.")

    if x_array.ndim == 1 and y_array.ndim == 1:
        if z_array.shape != (y_array.size, x_array.size):
            raise ValueError(
                "z_data shape must be (len(y_data), len(x_data)) when x_data/y_data are 1D."
            )
        x_plot = x_array
        y_plot = y_array
    elif x_array.ndim == 2 and y_array.ndim == 2:
        if x_array.shape != y_array.shape or z_array.shape != x_array.shape:
            raise ValueError(
                "x_data, y_data, and z_data must have matching shapes when using 2D grids."
            )
        x_plot = x_array
        y_plot = y_array
    else:
        raise ValueError("x_data and y_data must both be 1D or both be 2D arrays.")

    fig_width_in: float = fig_aspect_ratio[0] * fig_textwidth_pt / 72.27
    fig_height_in: float = fig_aspect_ratio[1] * fig_textwidth_pt / 72.27
    fig, ax = plt.subplots(figsize=(fig_width_in, fig_height_in), layout="constrained")

    if norm is not None and logcbar:
        raise ValueError("logcbar cannot be used together with an explicit norm.")

    color_norm = norm
    if logcbar:
        if np.any(z_array <= 0):
            raise ValueError("logcbar=True requires all z_data values to be strictly positive.")

        if vmin is None:
            vmin = float(np.nanmin(z_array))
        if vmax is None:
            vmax = float(np.nanmax(z_array))

        if vmin <= 0 or vmax <= 0:
            raise ValueError("logcbar=True requires vmin and vmax to be strictly positive.")
        if vmin >= vmax:
            raise ValueError("vmin must be smaller than vmax.")

        color_norm = LogNorm(vmin=vmin, vmax=vmax)

    if xticks_pos is not None:
        ax.set_xticks(xticks_pos)
        if xticks_labels is not None:
            if len(xticks_pos) != len(xticks_labels):
                raise ValueError("xticks_pos and xticks_labels lengths must match.")
            ax.set_xticklabels(xticks_labels)
        ax.xaxis.set_minor_locator(AutoMinorLocator(n=minor_tick_count + 1))
    else:
        ax.xaxis.set_minor_locator(AutoMinorLocator(n=minor_tick_count + 1))

    if yticks_pos is not None:
        ax.set_yticks(yticks_pos)
        if yticks_labels is not None:
            if len(yticks_pos) != len(yticks_labels):
                raise ValueError("yticks_pos and yticks_labels lengths must match.")
            ax.set_yticklabels(yticks_labels)
        ax.yaxis.set_minor_locator(AutoMinorLocator(n=minor_tick_count + 1))
    else:
        ax.yaxis.set_minor_locator(AutoMinorLocator(n=minor_tick_count + 1))

    pcolormesh_vmin = None if color_norm is not None else vmin
    pcolormesh_vmax = None if color_norm is not None else vmax

    im = ax.pcolormesh(
        x_plot,
        y_plot,
        z_array,
        cmap=cmap,
        shading=shading,
        alpha=alpha,
        vmin=pcolormesh_vmin,
        vmax=pcolormesh_vmax,
        norm=color_norm,
    )

    if contour:
        c_cmap = contour_cmap if contour_cmap is not None else cmap
        cs = ax.contour(
            x_plot,
            y_plot,
            z_array,
            levels=contour_levels,
            colors=None,
            cmap=c_cmap,
            linewidths=contour_linewidths,
        )
        if contour_labels:
            ax.clabel(cs, inline=True, fontsize=8)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)

    if xlim is not None:
        ax.set_xlim(xlim)
    if ylim is not None:
        ax.set_ylim(ylim)

    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")

    ax.set_aspect(aspect)

    if cbar_show:
        fig.colorbar(
            im,
            ax=ax,
            label=cbar_label,
            pad=cbar_pad,
            shrink=cbar_shrink,
            aspect=cbar_aspect,
            ticks=cbar_ticks,
        )

    if grid_show:
        ax.grid()

    if save_path:
        plt.savefig(save_path, dpi=300)

    if fig_show:
        plt.show()

    return fig, ax
