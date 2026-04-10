"""Reusable 1D plotting helpers with consistent styling.

The functions in this module are designed for THz time traces, spectra, and
fitting diagnostics. They accept either single arrays or sequences of traces
and provide convenience options for styling, legends, and error bars.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union
import warnings

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
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

DEFAULT_COLORS: tuple[str, ...] = (
    "#003399",
    "#FFCC00",
    "#CC3333",
    "#FF6700",
    "#264B1E",
    "#4BB3E0",
    "#AD3C00",
    "#9853E3",
    "#008B8B",
    "#E37222",
    "#00A86B",
    "#C71585",
    "#FFD700",
    "#4682B4",
    "#9ACD32",
    "#A52A2A",
)


def _create_figure_and_axes(
    fig_textwidth_pt: float,
    fig_aspect_ratio: tuple[float, float],
    minor_tick_count: int,
    xticks_pos: Optional[list[float]],
    xticks_labels: Optional[list[str]],
    yticks_pos: Optional[list[float]],
    yticks_labels: Optional[list[str]],
) -> tuple[Figure, Axes]:
    """Create a figure/axes pair and configure major/minor ticks."""
    fig_width_in: float = fig_aspect_ratio[0] * fig_textwidth_pt / 72.27
    fig_height_in: float = fig_aspect_ratio[1] * fig_textwidth_pt / 72.27
    fig, ax = plt.subplots(figsize=(fig_width_in, fig_height_in), layout="constrained")

    if xticks_pos is not None:
        ax.set_xticks(xticks_pos)
        if xticks_labels is not None:
            if len(xticks_pos) != len(xticks_labels):
                raise ValueError("xticks_pos and xticks_labels lengths must match.")
            ax.set_xticklabels(xticks_labels)
    ax.xaxis.set_minor_locator(AutoMinorLocator(n=minor_tick_count + 1))

    if yticks_pos is not None:
        ax.set_yticks(yticks_pos)
        if yticks_labels is not None:
            if len(yticks_pos) != len(yticks_labels):
                raise ValueError("yticks_pos and yticks_labels lengths must match.")
            ax.set_yticklabels(yticks_labels)
    ax.yaxis.set_minor_locator(AutoMinorLocator(n=minor_tick_count + 1))

    return fig, ax


def _finalize_axes(
    ax: Axes,
    *,
    xlim: Optional[Union[tuple[float, float], list[float]]],
    ylim: Optional[Union[tuple[float, float], list[float]]],
    xlabel: str,
    ylabel: str,
    title: str,
    legend_show: bool,
    legend_labels: Optional[list[str]],
    legend_loc: str,
    legend_ncols: int,
    grid_show: bool,
    save_path: Optional[str],
    fig_show: bool,
    logx: bool,
    logy: bool,
) -> None:
    """Apply shared axis formatting and optional save/show actions."""
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")

    if xlim:
        ax.set_xlim(xlim)
    if ylim:
        ax.set_ylim(ylim)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)

    if legend_show and legend_labels:
        ax.legend(frameon=False, loc=legend_loc, ncol=legend_ncols)

    if grid_show:
        ax.grid()

    if save_path:
        plt.savefig(save_path)
    if fig_show:
        plt.show()


def _is_trace_sequence(data: ArrayLike | Sequence[ArrayLike]) -> bool:
    """Return True if input appears to be a sequence of traces."""
    if isinstance(data, np.ndarray):
        return False
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        return False
    if len(data) == 0:
        return False
    first = data[0]
    return isinstance(first, (Sequence, np.ndarray)) and not isinstance(
        first, (str, bytes)
    )


def _normalize_traces(
    data: ArrayLike | Sequence[ArrayLike] | None,
    name: str,
    target_count: int,
) -> Optional[list[np.ndarray]]:
    """Convert traces to NumPy arrays and validate against the target count."""
    if data is None:
        return None
    data_is_sequence = _is_trace_sequence(data)
    if target_count == 1 and data_is_sequence:
        raise ValueError(f"{name} must be a single trace.")
    if target_count > 1 and not data_is_sequence:
        raise ValueError(f"{name} must be a sequence of traces.")
    traces = [data] if not data_is_sequence else list(data)
    if len(traces) != target_count:
        raise ValueError(
            f"You provided {len(traces)} {name} traces, but expected {target_count}."
        )
    return [np.asarray(trace) for trace in traces]


def _cycle_values(values: Sequence[str], target_count: int, name: str) -> list[str]:
    """Return a list of length ``target_count`` by cycling ``values`` as needed."""
    values_list = list(values)
    if not values_list:
        raise ValueError(f"{name} must contain at least one value.")
    if len(values_list) >= target_count:
        return values_list[:target_count]
    repeats, remainder = divmod(target_count, len(values_list))
    return values_list * repeats + values_list[:remainder]


def _normalize_show_flags(
    flags: bool | Sequence[bool],
    target_count: int,
    name: str,
) -> list[bool]:
    """Normalize a bool or sequence[bool] to length ``target_count``.

    A single bool is broadcast to all traces. For sequences, values are copied and
    padded with the last provided value when shorter than ``target_count``.
    """
    if isinstance(flags, bool):
        return [flags] * target_count

    flags_list = list(flags)
    if not flags_list:
        raise ValueError(f"{name} must contain at least one value when provided as a sequence.")
    if len(flags_list) >= target_count:
        return [bool(flag) for flag in flags_list[:target_count]]

    return [bool(flag) for flag in flags_list] + [bool(flags_list[-1])] * (
        target_count - len(flags_list)
    )

def plot_1d(
    x_data: ArrayLike | Sequence[ArrayLike],
    y_data: ArrayLike | Sequence[ArrayLike],
    xerr_data: Optional[ArrayLike | Sequence[ArrayLike]] = None,
    yerr_data: Optional[ArrayLike | Sequence[ArrayLike]] = None,
    colors: Optional[Sequence[str]] = DEFAULT_COLORS,
    line_show: bool | Sequence[bool] = True,
    line_styles: Optional[list[str]] = None,
    scatter_show: bool | Sequence[bool] = False,
    scatter_colors: Optional[list[str]] = None,
    xlim: Optional[Union[tuple[float, float], list[float]]] = None,
    ylim: Optional[Union[tuple[float, float], list[float]]] = None,
    xlabel: str = "",
    ylabel: str = "",
    title: str = "",
    legend_show: bool = True,
    legend_labels: Optional[list[str]] = None,
    legend_loc: str = "best",
    legend_ncols: int = 1,
    save_path: Optional[str] = None,
    grid_show: bool = False,
    fig_show: bool = True,
    fig_textwidth_pt: float = 497.0,
    fig_aspect_ratio: tuple[float, float] = (1/2, 1/2),
    minor_tick_count: int = 1,
    xticks_pos: Optional[list[float]] = None,
    xticks_labels: Optional[list[str]] = None,
    yticks_pos: Optional[list[float]] = None,
    yticks_labels: Optional[list[str]] = None,
    vlines_pos: Optional[Sequence[float]] = None,
    vlines_colors: Optional[Sequence[str]] = None,
    vlines_styles: Optional[Sequence[str]] = None,
    vlines_labels: Optional[Sequence[str]] = None,
    hlines_pos: Optional[Sequence[float]] = None,
    hlines_colors: Optional[Sequence[str]] = None,
    hlines_styles: Optional[Sequence[str]] = None,
    hlines_labels: Optional[Sequence[str]] = None,
    err_colors: Optional[Sequence[str]] = None,
    err_linewidth: float = 1.0,
    bars_above: bool = False,
    logx: bool = False,
    logy: bool = False,
    first_on_top: bool = True,
) -> Tuple[Figure, Axes]:
    """Reusable 1D plotting function for THz time traces, spectra, and envelopes.

    Parameters
    ----------
    x_data : array-like or sequence[array-like]
        X-values. Provide either a single trace or a list of traces.
    y_data : array-like or sequence[array-like]
        Y-values. Provide either a single trace or a list of traces.
    xerr_data, yerr_data : array-like or sequence[array-like], optional
        Standard deviation errors for x and y. Provide either a single trace or a list
        of traces matching x_data and y_data.
    colors : list[str], optional
        Colors used for each plotted line.
    line_show : bool or sequence[bool], default True
        Whether to draw lines connecting data points. A single bool applies to all
        traces, or pass one flag per trace.
    line_styles : list[str], optional
        Line style for each trace (e.g. '-', '--').
    scatter_show : bool or sequence[bool], default False
        Whether to draw scatter markers at data points. A single bool applies to all
        traces, or pass one flag per trace.
    scatter_colors : list[str], optional
        Colors for scatter fill (center).
    xlim, ylim : tuple or list, optional
        Axis limits (min, max).
    xlabel, ylabel, title : str, optional
        Axis labels and plot title.
    legend_show : bool, default True
        Whether to display the legend.
    legend_labels : list[str], optional
        Labels for legend entries.
    legend_loc : str, default 'best'
        Legend position string.
    legend_ncols : int, default 1
        Number of columns for legend entries.
    save_path : str, optional
        If provided, figure is saved to this path.
    grid_show : bool, default False
        Whether to show grid lines.
    fig_show : bool, default True
        Whether to show the figure.
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
    vlines_pos, hlines_pos : list[float], optional
        Positions for vertical and horizontal reference lines.
    vlines_colors, hlines_colors : list[str], optional
        Colors for reference lines (default 'gray').
    vlines_styles, hlines_styles : list[str], optional
        Line styles for reference lines (default '--').
    vlines_labels, hlines_labels : list[str], optional
        Labels for reference lines (default '').
    err_colors : list[str], optional
        Colors for error bars per trace (default 'gray').
    err_linewidth : float
        Line width for error bars.
    bars_above : bool
        Whether error bars are drawn above plot elements.
    logx, logy : bool
        Whether to use logarithmic axis scaling.
    first_on_top : bool, default True
        If True: the *first* dataset is drawn last → appears on top.
        If False: plotting order is sequential → first dataset is at bottom.

    Returns
    -------
    matplotlib.figure.Figure, matplotlib.axes.Axes
        Figure and axes for further customization.
    """

    fig, ax = _create_figure_and_axes(
        fig_textwidth_pt,
        fig_aspect_ratio,
        minor_tick_count,
        xticks_pos,
        xticks_labels,
        yticks_pos,
        yticks_labels,
    )

    # --- Data preparation ---
    x_is_sequence = _is_trace_sequence(x_data)
    y_is_sequence = _is_trace_sequence(y_data)

    if x_is_sequence != y_is_sequence:
        raise ValueError(
            "x_data and y_data must both be a single trace or both be sequences of traces."
        )

    if not x_is_sequence:
        x_traces = [x_data]
        y_traces = [y_data]
    else:
        x_traces = list(x_data)
        y_traces = list(y_data)

    if len(x_traces) != len(y_traces):
        raise ValueError(
            f"You provided {len(x_traces)} x-traces and {len(y_traces)} y-traces; "
            "they must match."
        )

    x_arrays: list[np.ndarray] = []
    y_arrays: list[np.ndarray] = []
    for i, (x_trace, y_trace) in enumerate(zip(x_traces, y_traces)):
        x_array = np.asarray(x_trace)
        y_array = np.asarray(y_trace)
        if x_array.shape != y_array.shape:
            raise ValueError(
                f"Trace {i} mismatch: x has shape {x_array.shape}, "
                f"y has shape {y_array.shape}."
            )
        x_arrays.append(x_array)
        y_arrays.append(y_array)

    xerr_arrays = _normalize_traces(xerr_data, "xerr_data", len(x_arrays))
    yerr_arrays = _normalize_traces(yerr_data, "yerr_data", len(x_arrays))
    if xerr_arrays is not None:
        for i, (x_array, xerr_array) in enumerate(zip(x_arrays, xerr_arrays)):
            if xerr_array.shape != x_array.shape:
                raise ValueError(
                    f"xerr_data trace {i} mismatch: x has shape {x_array.shape}, "
                    f"xerr has shape {xerr_array.shape}."
                )
    if yerr_arrays is not None:
        for i, (y_array, yerr_array) in enumerate(zip(y_arrays, yerr_arrays)):
            if yerr_array.shape != y_array.shape:
                raise ValueError(
                    f"yerr_data trace {i} mismatch: y has shape {y_array.shape}, "
                    f"yerr has shape {yerr_array.shape}."
                )

    if colors is None:
        raise ValueError("colors cannot be None when plotting data.")
    colors = _cycle_values(colors, len(x_arrays), "colors")

    line_show_flags = _normalize_show_flags(line_show, len(x_arrays), "line_show")
    scatter_show_flags = _normalize_show_flags(
        scatter_show, len(x_arrays), "scatter_show"
    )

    if any(scatter_show_flags):
        if scatter_colors is None:
            scatter_colors = ["white"] * len(x_arrays)
        elif len(scatter_colors) < len(x_arrays):
            scatter_colors = scatter_colors + ["white"] * (
                len(x_arrays) - len(scatter_colors)
            )

    if legend_labels is None:
        legend_labels = [""] * len(x_arrays)
    elif len(legend_labels) < len(x_arrays):
        legend_labels = legend_labels + [""] * (len(x_arrays) - len(legend_labels))

    if line_styles is None:
        line_styles = ["-"] * len(x_arrays)
    elif len(line_styles) < len(x_arrays):
        line_styles = line_styles + ["-"] * (len(x_arrays) - len(line_styles))

    if err_colors is None:
        err_colors = ["gray"] * len(x_arrays)
    else:
        err_colors = list(err_colors)
        if len(err_colors) < len(x_arrays):
            err_colors += ["gray"] * (len(x_arrays) - len(err_colors))

    def normalize_line_styles(
        positions: Optional[Sequence[float]],
        colors_list: Optional[Sequence[str]],
        styles_list: Optional[Sequence[str]],
        labels_list: Optional[Sequence[str]],
    ) -> tuple[Optional[Sequence[float]], list[str], list[str], list[str]]:
        """Normalize per-line styles and fill missing values with defaults."""
        if positions is None:
            return None, [], [], []
        count = len(positions)
        colors_norm = ["gray"] * count if colors_list is None else list(colors_list)
        styles_norm = ["--"] * count if styles_list is None else list(styles_list)
        labels_norm = [""] * count if labels_list is None else list(labels_list)
        if len(colors_norm) < count:
            colors_norm += ["gray"] * (count - len(colors_norm))
        if len(styles_norm) < count:
            styles_norm += ["--"] * (count - len(styles_norm))
        if len(labels_norm) < count:
            labels_norm += [""] * (count - len(labels_norm))
        return positions, colors_norm, styles_norm, labels_norm

    vlines_pos, vlines_colors, vlines_styles, vlines_labels = normalize_line_styles(
        vlines_pos, vlines_colors, vlines_styles, vlines_labels
    )
    hlines_pos, hlines_colors, hlines_styles, hlines_labels = normalize_line_styles(
        hlines_pos, hlines_colors, hlines_styles, hlines_labels
    )

    # --- Plot lines ---

    # Determine plotting order
    indices = (
        range(len(x_arrays) - 1, -1, -1) if first_on_top else range(len(x_arrays))
    )

    for i in indices:
        line_show_i = line_show_flags[i]
        scatter_show_i = scatter_show_flags[i]

        if line_show_i and not scatter_show_i:
            ax.plot(
                x_arrays[i], y_arrays[i],
                label=legend_labels[i],
                color=colors[i],
                linestyle=line_styles[i],
                zorder=1.0,
            )

        if line_show_i and scatter_show_i:
            ax.plot(
                x_arrays[i], y_arrays[i],
                color=colors[i],
                linestyle=line_styles[i],
                zorder=1.0,
            )
            ax.scatter(
                x_arrays[i], y_arrays[i],
                label=legend_labels[i],
                edgecolor=colors[i],
                color=scatter_colors[i],
                s=30, linewidth=1.5,
                zorder=3.0,
            )

        if not line_show_i and scatter_show_i:
            ax.scatter(
                x_arrays[i], y_arrays[i],
                label=legend_labels[i],
                edgecolor=colors[i],
                color=scatter_colors[i],
                s=30, linewidth=1.5,
                zorder=3.0,
            )

        if not line_show_i and not scatter_show_i:
            continue

        if xerr_arrays is not None or yerr_arrays is not None:
            ax.errorbar(
                x_arrays[i],
                y_arrays[i],
                xerr=None if xerr_arrays is None else xerr_arrays[i],
                yerr=None if yerr_arrays is None else yerr_arrays[i],
                fmt="none",
                ecolor=err_colors[i],
                elinewidth=err_linewidth,
                barsabove=bars_above,
                capsize=3,
                zorder=2.0 if bars_above else 0.9,
            )

    # --- Vertical reference lines ---
    if vlines_pos:
        for pos, color, style, label in zip(
            vlines_pos, vlines_colors, vlines_styles, vlines_labels
        ):
            ax.axvline(
                x=pos,
                color=color,
                linestyle=style,
                label=label if label else None,
                linewidth=1.0,
                zorder=0.5,
            )

    # --- Horizontal reference lines ---
    if hlines_pos:
        for pos, color, style, label in zip(
            hlines_pos, hlines_colors, hlines_styles, hlines_labels
        ):
            ax.axhline(
                y=pos,
                color=color,
                linestyle=style,
                label=label if label else None,
                linewidth=1.0,
                zorder=0.5,
            )

    _finalize_axes(
        ax,
        xlim=xlim,
        ylim=ylim,
        xlabel=xlabel,
        ylabel=ylabel,
        title=title,
        legend_show=legend_show,
        legend_labels=legend_labels,
        legend_loc=legend_loc,
        legend_ncols=legend_ncols,
        grid_show=grid_show,
        save_path=save_path,
        fig_show=fig_show,
        logx=logx,
        logy=logy,
    )

    return fig, ax


def plot_histogram_1d(
    data: ArrayLike | Sequence[ArrayLike],
    bins: int | Sequence[float] | str = 10,
    range: Optional[tuple[float, float]] = None,
    density: bool = False,
    weights: Optional[ArrayLike | Sequence[ArrayLike]] = None,
    histtype: str | Sequence[str] = "step",
    fill: bool | Sequence[bool] = False,
    hatch: Optional[str | Sequence[Optional[str]]] = None,
    alpha: float | Sequence[float] = 1.0,
    edgecolor: Optional[str | Sequence[str]] = None,
    linewidth: float | Sequence[float] = 1.5,
    colors: Optional[Sequence[str]] = DEFAULT_COLORS,
    xlim: Optional[Union[tuple[float, float], list[float]]] = None,
    ylim: Optional[Union[tuple[float, float], list[float]]] = None,
    xlabel: str = "",
    ylabel: str = "",
    title: str = "",
    legend_show: bool = True,
    legend_labels: Optional[list[str]] = None,
    legend_loc: str = "best",
    legend_ncols: int = 1,
    save_path: Optional[str] = None,
    grid_show: bool = False,
    fig_show: bool = True,
    fig_textwidth_pt: float = 497.0,
    fig_aspect_ratio: tuple[float, float] = (1 / 2, 1 / 2),
    minor_tick_count: int = 1,
    xticks_pos: Optional[list[float]] = None,
    xticks_labels: Optional[list[str]] = None,
    yticks_pos: Optional[list[float]] = None,
    yticks_labels: Optional[list[str]] = None,
    logx: bool = False,
    logy: bool = False,
    first_on_top: bool = True,
) -> Tuple[Figure, Axes]:
    """Plot one or more 1D histograms with consistent styling.

    This function is intended for sample distributions (for example fit residuals,
    parameter spreads, noise distributions, or Monte-Carlo outputs). For paired
    ``x``/``y`` traces, use :func:`plot_1d` instead.

    Parameters
    ----------
    data : array-like or sequence[array-like]
        Histogram sample values. Pass a single array for one histogram, or a
        sequence of arrays for multiple histograms in the same axes.
    bins : int, sequence[float], or str, default 10
        Histogram bin specification forwarded to ``matplotlib.axes.Axes.hist``.
        - ``int``: number of equal-width bins.
        - ``sequence``: explicit bin edges.
        - ``str``: automatic strategy supported by NumPy/Matplotlib (for example
          ``"auto"``, ``"fd"``, ``"sturges"``).
    range : tuple[float, float], optional
        Lower and upper range of the bins. Values outside this interval are
        ignored.
    density : bool, default False
        If ``True``, normalize each histogram to a probability density.
    weights : array-like or sequence[array-like], optional
        Per-sample weights. For multiple datasets, provide one weight array per
        dataset and each must match the corresponding ``data`` shape.
    histtype : str or sequence[str], default "step"
        Histogram drawing style per dataset (for example ``"step"``, ``"bar"``,
        ``"barstacked"``, ``"stepfilled"``).
    fill : bool or sequence[bool], default False
        Convenience switch for colored/filled histograms. If ``True`` for a
        dataset and its ``histtype`` is ``"step"``, the function automatically
        uses ``"stepfilled"`` so the histogram area is color-filled instead of
        line-only.
    hatch : str, sequence[str | None], or None, default None
        Optional hatch pattern(s) for patterned fills, e.g. ``"/"``, ``"//"``,
        ``"x"``, or ``".."``. You can pass one value for all datasets or a
        sequence per dataset. To make hatch visible, use a filled histogram
        style (for example ``fill=True`` or ``histtype="bar"``/``"stepfilled"``).
    alpha : float or sequence[float], default 1.0
        Per-dataset opacity.
    edgecolor : str or sequence[str], optional
        Per-dataset edge color. If omitted, Matplotlib defaults are used.
    linewidth : float or sequence[float], default 1.5
        Per-dataset edge/line width.
    colors : sequence[str], optional
        Per-dataset face/line color list. Must include at least as many entries
        as datasets in ``data``.
    xlim, ylim : tuple[float, float] or list[float], optional
        Axis limits in the form ``(min, max)``.
    xlabel, ylabel, title : str, optional
        Axis labels and plot title.
    legend_show : bool, default True
        If ``True``, draw a legend when non-empty labels are supplied.
    legend_labels : list[str], optional
        Per-dataset legend labels. Missing labels are padded with empty strings.
    legend_loc : str, default "best"
        Legend location passed to Matplotlib.
    legend_ncols : int, default 1
        Number of legend columns.
    save_path : str, optional
        If provided, save the figure to this path.
    grid_show : bool, default False
        If ``True``, show major grid lines.
    fig_show : bool, default True
        If ``True``, call ``plt.show()`` at the end.
    fig_textwidth_pt : float, default 497.0
        Text width in points used to scale figure size.
    fig_aspect_ratio : tuple[float, float], default (1/2, 1/2)
        Relative ``(width, height)`` with respect to ``fig_textwidth_pt``.
    minor_tick_count : int, default 1
        Number of minor tick intervals between major ticks.
    xticks_pos, yticks_pos : list[float], optional
        Explicit major tick positions.
    xticks_labels, yticks_labels : list[str], optional
        Custom labels for the explicit tick positions.
    logx, logy : bool, default False
        If ``True``, apply logarithmic scaling on the corresponding axis.
    first_on_top : bool, default True
        Draw order control for overlapping histograms.
        - ``True``: first dataset is drawn last (appears on top).
        - ``False``: datasets are drawn in listed order.

    Returns
    -------
    matplotlib.figure.Figure, matplotlib.axes.Axes
        The created figure and axes objects.

    Examples
    --------
    ``plot_histogram_1d(samples, bins=60, density=True)`` for line-style bins.
    ``plot_histogram_1d(samples, bins=60, fill=True, alpha=0.4)`` for filled bins.
    ``plot_histogram_1d(samples, bins=40, fill=True, hatch="//")`` for striped fills.
    """
    fig, ax = _create_figure_and_axes(
        fig_textwidth_pt,
        fig_aspect_ratio,
        minor_tick_count,
        xticks_pos,
        xticks_labels,
        yticks_pos,
        yticks_labels,
    )

    data_is_sequence = _is_trace_sequence(data)
    datasets = [data] if not data_is_sequence else list(data)
    data_arrays = [np.asarray(dataset) for dataset in datasets]

    histogram_bins: int | Sequence[float] | str = bins
    bins_is_explicit_edges = isinstance(bins, Sequence) and not isinstance(bins, (str, bytes))
    if len(data_arrays) > 1 and not bins_is_explicit_edges:
        # Keep explicit scalar-bin behavior for single datasets while ensuring
        # overlaid histograms share identical bin edges.
        finite_values = [arr[np.isfinite(arr)] for arr in data_arrays]
        finite_values = [arr for arr in finite_values if arr.size > 0]
        if finite_values:
            histogram_bins = np.histogram_bin_edges(
                np.concatenate(finite_values),
                bins=bins,
                range=range,
            )

    weights_arrays = _normalize_traces(weights, "weights", len(data_arrays))
    if weights_arrays is not None:
        for i, (values, w) in enumerate(zip(data_arrays, weights_arrays)):
            if values.shape != w.shape:
                raise ValueError(
                    f"weights trace {i} mismatch: data has shape {values.shape}, "
                    f"weights has shape {w.shape}."
                )

    if colors is None:
        raise ValueError("colors cannot be None when plotting data.")
    colors = _cycle_values(colors, len(data_arrays), "colors")

    if legend_labels is None:
        legend_labels = [""] * len(data_arrays)
    elif len(legend_labels) < len(data_arrays):
        legend_labels = legend_labels + [""] * (len(data_arrays) - len(legend_labels))

    def _normalize_per_dataset(
        value: str | float | Sequence[str] | Sequence[float] | None,
        default: str | float | None,
    ) -> list[str | float | None]:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            normalized = list(value)
            if not normalized:
                return [default] * len(data_arrays)
            if len(normalized) < len(data_arrays):
                normalized += [normalized[-1]] * (len(data_arrays) - len(normalized))
            return normalized

        # Broadcast scalar values (or None) to every dataset.
        return [value] * len(data_arrays)

    histtype_list = _normalize_per_dataset(histtype, "step")
    fill_list = _normalize_per_dataset(fill, False)
    hatch_list = _normalize_per_dataset(hatch, None)
    alpha_list = _normalize_per_dataset(alpha, 1.0)
    edgecolor_list = _normalize_per_dataset(edgecolor, None)
    linewidth_list = _normalize_per_dataset(linewidth, 1.5)

    indices = (
        builtins.range(len(data_arrays) - 1, -1, -1)
        if first_on_top
        else builtins.range(len(data_arrays))
    )
    for i in indices:
        histtype_i = str(histtype_list[i])
        if bool(fill_list[i]) and histtype_i == "step":
            histtype_i = "stepfilled"

        _, _, patches = ax.hist(
            data_arrays[i],
            bins=histogram_bins,
            range=range,
            density=density,
            weights=None if weights_arrays is None else weights_arrays[i],
            histtype=histtype_i,
            alpha=float(alpha_list[i]),
            edgecolor=edgecolor_list[i],
            linewidth=float(linewidth_list[i]),
            color=colors[i],
            label=legend_labels[i],
        )

        hatch_i = hatch_list[i]
        if hatch_i is not None:
            for patch in patches:
                patch.set_hatch(str(hatch_i))

    _finalize_axes(
        ax,
        xlim=xlim,
        ylim=ylim,
        xlabel=xlabel,
        ylabel=ylabel,
        title=title,
        legend_show=legend_show,
        legend_labels=legend_labels,
        legend_loc=legend_loc,
        legend_ncols=legend_ncols,
        grid_show=grid_show,
        save_path=save_path,
        fig_show=fig_show,
        logx=logx,
        logy=logy,
    )

    return fig, ax
