#!/usr/bin/env python3
"""UI layout prototype for a future interactive Newport measurement window.

This module intentionally focuses on *layout and control flow scaffolding*.
Measurement hardware integration and fitting logic can be connected later.
"""

from __future__ import annotations

import math
import time
import tkinter as tk

import numpy as np
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from visualization import plot_1d


@dataclass
class SamplePoint:
    """Single in-memory sample used by the plotting placeholder."""

    time_s: float
    power_w: float


class InteractiveLayoutApp:
    """Tkinter app that provides the requested future interactive-window layout."""

    PLOT_WIDTH = 820
    PLOT_HEIGHT = 380
    PLOT_MARGIN = 36

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Newport 1918-R Interactive Window (Layout Prototype)")
        self.root.geometry("1280x820")

        self._running = False
        self._start_perf_s = 0.0
        self._samples: list[SamplePoint] = []
        self._job_id: str | None = None

        self.x_axis_var = tk.StringVar(value="Time")
        self.y_axis_var = tk.StringVar(value="Test")
        self.sampling_time_ms_var = tk.StringVar(value="100")
        self.x_axis_min_var = tk.StringVar(value="0")
        self.x_axis_max_var = tk.StringVar(value="30")
        self.x_axis_mode_var = tk.StringVar(value="Linear")
        self.y_axis_mode_var = tk.StringVar(value="Linear")
        self.measure_min_var = tk.StringVar(value="0")
        self.measure_max_var = tk.StringVar(value="1")
        self.file_path_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready. Configure settings and press Start.")
        self.start_button: ttk.Button | None = None

        self._build_layout()
        self._render_plot()

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(14, 0))

        plot_frame = ttk.Frame(left)
        plot_frame.pack(fill=tk.BOTH, expand=False)
        self.fig, self.ax = plot_1d(
            x_data=np.array([0.0, 1.0]),
            y_data=np.array([0.0, 1.0]),
            xlabel=self.x_axis_var.get(),
            ylabel=self.y_axis_var.get(),
            title="",
            legend_show=False,
            grid_show=True,
            fig_show=False,
        )
        self.fig.set_size_inches(9.5, 4.5)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().configure(highlightthickness=1, highlightbackground="#b0b0b0")
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=False)

        controls = ttk.LabelFrame(left, text="Acquisition and Axis Controls", padding=10)
        controls.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        for idx in range(4):
            controls.columnconfigure(idx, weight=1)

        ttk.Label(controls, text="X Axis").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.x_axis_var,
            values=["Time"],
            state="readonly",
            width=24,
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="Y Axis").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.y_axis_var,
            values=["Test"],
            state="readonly",
            width=24,
        ).grid(row=0, column=3, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="Sampling time (ms)").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.sampling_time_ms_var).grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="Y-axis min").grid(row=1, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.measure_min_var).grid(row=1, column=3, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="X-axis min (s)").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.x_axis_min_var).grid(row=2, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="Y-axis max").grid(row=2, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.measure_max_var).grid(row=2, column=3, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="X-axis max (s)").grid(row=3, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.x_axis_max_var).grid(row=3, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="X Axis mode").grid(row=3, column=2, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.x_axis_mode_var,
            values=["Linear", "Log"],
            state="readonly",
        ).grid(row=3, column=3, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text=" ").grid(row=4, column=0, sticky="w", padx=4, pady=4)

        ttk.Label(controls, text="Y Axis mode").grid(row=4, column=2, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.y_axis_mode_var,
            values=["Linear", "Log"],
            state="readonly",
        ).grid(row=4, column=3, sticky="ew", padx=4, pady=4)

        run_controls = ttk.Frame(controls)
        run_controls.grid(row=5, column=0, columnspan=4, sticky="ew", padx=4, pady=(10, 4))
        self.start_button = ttk.Button(run_controls, text="Start", command=self.start)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(run_controls, text="Stop", command=self.stop).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(controls, textvariable=self.status_var).grid(
            row=6,
            column=0,
            columnspan=4,
            sticky="w",
            padx=4,
            pady=(8, 2),
        )

        file_controls = ttk.LabelFrame(left, text="Save / Load", padding=10)
        file_controls.pack(fill=tk.X, expand=False, pady=(10, 0))
        file_controls.columnconfigure(0, weight=1)
        file_controls.columnconfigure(1, weight=0)
        ttk.Entry(file_controls, textvariable=self.file_path_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        file_buttons = ttk.Frame(file_controls)
        file_buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(file_buttons, text="Browse…", command=self._browse_file).pack(side=tk.LEFT)
        ttk.Button(file_buttons, text="Save As…", command=self._save_as).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(file_buttons, text="Load…", command=self._load_file).pack(side=tk.LEFT, padx=(6, 0))

        fitting = ttk.LabelFrame(right, text="Fitting (Black Box Placeholder)", padding=10)
        fitting.pack(fill=tk.BOTH, expand=True)
        self.fitting_canvas = tk.Canvas(
            fitting,
            width=320,
            background="black",
            highlightthickness=1,
            highlightbackground="#303030",
        )
        self.fitting_canvas.pack(fill=tk.BOTH, expand=True)
        self.fitting_canvas.create_text(
            160,
            30,
            text="Fitting block placeholder",
            fill="white",
            font=("TkDefaultFont", 10, "bold"),
        )

    def _render_plot(self) -> None:
        x_data = np.array([sample.time_s for sample in self._samples], dtype=float)
        y_data = np.array([sample.power_w for sample in self._samples], dtype=float)

        logx = self.x_axis_mode_var.get().strip().lower() == "log"
        logy = self.y_axis_mode_var.get().strip().lower() == "log"

        x_min = self._safe_float(self.x_axis_min_var.get(), default=0.0)
        x_max = self._safe_float(self.x_axis_max_var.get(), default=30.0)
        y_min = self._safe_float(self.measure_min_var.get(), default=0.0)
        y_max = self._safe_float(self.measure_max_var.get(), default=1.0)

        if x_max <= x_min:
            x_max = x_min + 1.0
        if y_max <= y_min:
            y_max = y_min + 1.0

        if logx:
            x_min = max(x_min, 1e-6)
            x_max = max(x_max, x_min * 10)
            positive_mask = x_data > 0
            x_data = x_data[positive_mask]
            y_data = y_data[positive_mask]

        if logy:
            y_min = max(y_min, 1e-6)
            y_max = max(y_max, y_min * 10)
            y_data = np.maximum(y_data, 1e-6)

        if x_data.size == 0:
            x_data = np.array([x_min, x_max], dtype=float)
            y_data = np.array([0.0, 1.0], dtype=float)
            if logy:
                y_data = np.maximum(y_data, 1e-6)

        new_fig, new_ax = plot_1d(
            x_data=x_data,
            y_data=y_data,
            colors=["#1368ce"],
            line_show=True,
            scatter_show=False,
            xlim=(x_min, x_max),
            ylim=(y_min, y_max),
            xlabel=self.x_axis_var.get(),
            ylabel=self.y_axis_var.get(),
            title="",
            legend_show=False,
            grid_show=True,
            fig_show=False,
            logx=logx,
            logy=logy,
        )
        new_fig.set_size_inches(9.5, 4.5)
        self.canvas.figure.clf()
        self.fig = new_fig
        self.ax = new_ax
        self.canvas.figure = self.fig
        self.canvas.draw()

    def _browse_file(self) -> None:
        initial = self.file_path_var.get().strip() or str(Path.cwd())
        chosen = filedialog.askopenfilename(initialdir=str(Path(initial).parent))
        if chosen:
            self.file_path_var.set(chosen)

    def _save_as(self) -> None:
        initial = self.file_path_var.get().strip() or str(Path.cwd() / "newport_capture.csv")
        chosen = filedialog.asksaveasfilename(
            initialfile=Path(initial).name,
            initialdir=str(Path(initial).parent),
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if chosen:
            self.file_path_var.set(chosen)
            self.status_var.set(f"Save target selected: {chosen}")

    def _load_file(self) -> None:
        initial = self.file_path_var.get().strip() or str(Path.cwd())
        chosen = filedialog.askopenfilename(
            initialdir=str(Path(initial).parent),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if chosen:
            self.file_path_var.set(chosen)
            self.status_var.set(f"Load file selected: {chosen}")

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._samples.clear()
        self._start_perf_s = time.perf_counter()
        if self.start_button is not None:
            self.start_button.configure(text="Running")
        self.status_var.set("Acquisition running.")
        self._schedule_next_tick()

    def stop(self) -> None:
        self._running = False
        if self._job_id is not None:
            self.root.after_cancel(self._job_id)
            self._job_id = None
        if self.start_button is not None:
            self.start_button.configure(text="Start")
        self.status_var.set("Acquisition stopped.")

    def _schedule_next_tick(self) -> None:
        sampling_time_ms = self._safe_positive_float(self.sampling_time_ms_var.get(), default=100.0)
        delay_ms = max(20, int(sampling_time_ms))
        self._job_id = self.root.after(delay_ms, self._tick)

    def _tick(self) -> None:
        if not self._running:
            return

        elapsed = time.perf_counter() - self._start_perf_s
        power = 0.5 + 0.5 * math.sin(elapsed * 1.5)
        self._samples.append(SamplePoint(time_s=elapsed, power_w=power))

        if len(self._samples) > 5000:
            self._samples = self._samples[-2500:]

        self._render_plot()
        self._schedule_next_tick()

    @staticmethod
    def _safe_float(raw: str, default: float) -> float:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _safe_positive_float(cls, raw: str, default: float) -> float:
        parsed = cls._safe_float(raw, default=default)
        return parsed if parsed > 0 else default


def main() -> None:
    root = tk.Tk()
    app = InteractiveLayoutApp(root)

    def on_close() -> None:
        app.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
