#!/usr/bin/env python3
"""UI layout prototype for a future interactive Newport measurement window.

This module intentionally focuses on *layout and control flow scaffolding*.
Measurement hardware integration and fitting logic can be connected later.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk


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
        self.y_axis_var = tk.StringVar(value="PowerMeasurement")
        self.sampling_time_ms_var = tk.StringVar(value="100")
        self.x_axis_max_var = tk.StringVar(value="30")
        self.axis_mode_var = tk.StringVar(value="Linear")
        self.measure_min_var = tk.StringVar(value="0")
        self.measure_max_var = tk.StringVar(value="1")
        self.file_path_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready. Configure settings and press Start.")
        self.start_button: ttk.Button | None = None

        self._build_layout()
        self._draw_plot_frame()

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(14, 0))

        self.canvas = tk.Canvas(
            left,
            width=self.PLOT_WIDTH,
            height=self.PLOT_HEIGHT,
            background="white",
            highlightthickness=1,
            highlightbackground="#b0b0b0",
        )
        self.canvas.pack(fill=tk.BOTH, expand=False)

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
            values=["PowerMeasurement"],
            state="readonly",
            width=24,
        ).grid(row=0, column=3, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="Sampling time (ms)").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.sampling_time_ms_var).grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="Y-axis min").grid(row=1, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.measure_min_var).grid(row=1, column=3, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="X-axis max (s)").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.x_axis_max_var).grid(row=2, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text="Y-axis max").grid(row=2, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(controls, textvariable=self.measure_max_var).grid(row=2, column=3, sticky="ew", padx=4, pady=4)

        ttk.Label(controls, text=" ").grid(row=3, column=0, sticky="w", padx=4, pady=4)

        ttk.Label(controls, text="Y Axis mode").grid(row=3, column=2, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.axis_mode_var,
            values=["Linear", "Log"],
            state="readonly",
        ).grid(row=3, column=3, sticky="ew", padx=4, pady=4)

        run_controls = ttk.Frame(controls)
        run_controls.grid(row=4, column=0, columnspan=4, sticky="ew", padx=4, pady=(10, 4))
        self.start_button = ttk.Button(run_controls, text="Start", command=self.start)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(run_controls, text="Stop", command=self.stop).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(controls, textvariable=self.status_var).grid(
            row=5,
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

    def _draw_plot_frame(self) -> None:
        self.canvas.delete("all")
        x0 = self.PLOT_MARGIN
        y0 = self.PLOT_HEIGHT - self.PLOT_MARGIN
        x1 = self.PLOT_WIDTH - self.PLOT_MARGIN
        y1 = self.PLOT_MARGIN

        self.canvas.create_rectangle(x0, y1, x1, y0, outline="#606060")
        grid_lines = 8
        for i in range(1, grid_lines):
            gx = x0 + (x1 - x0) * i / grid_lines
            gy = y1 + (y0 - y1) * i / grid_lines
            self.canvas.create_line(gx, y1, gx, y0, fill="#e8e8e8")
            self.canvas.create_line(x0, gy, x1, gy, fill="#e8e8e8")
        self.canvas.create_text((x0 + x1) / 2, self.PLOT_HEIGHT - 14, text=self.x_axis_var.get())
        self.canvas.create_text(16, (y0 + y1) / 2, text=self.y_axis_var.get(), angle=90)

        self._draw_line_data()

    def _draw_line_data(self) -> None:
        if len(self._samples) < 2:
            return

        x0 = self.PLOT_MARGIN
        y0 = self.PLOT_HEIGHT - self.PLOT_MARGIN
        x1 = self.PLOT_WIDTH - self.PLOT_MARGIN
        y1 = self.PLOT_MARGIN

        window_seconds = self._safe_positive_float(self.x_axis_max_var.get(), default=30.0)
        right_t = self._samples[-1].time_s
        left_t = max(0.0, right_t - window_seconds)

        visible = [s for s in self._samples if s.time_s >= left_t]
        if len(visible) < 2:
            return

        min_y = self._safe_float(self.measure_min_var.get(), default=min(s.power_w for s in visible))
        max_y = self._safe_float(self.measure_max_var.get(), default=max(s.power_w for s in visible))
        if max_y <= min_y:
            max_y = min_y + 1.0

        points: list[float] = []
        log_mode = self.axis_mode_var.get().strip().lower() == "log"

        for sample in visible:
            tx = (sample.time_s - left_t) / max(window_seconds, 1e-9)
            px = x0 + tx * (x1 - x0)

            value = sample.power_w
            lo, hi = min_y, max_y
            if log_mode:
                value = max(value, 1e-12)
                lo = max(lo, 1e-12)
                hi = max(hi, lo * 10)
                value = math.log10(value)
                lo = math.log10(lo)
                hi = math.log10(hi)

            ty = (value - lo) / (hi - lo)
            ty = min(1.0, max(0.0, ty))
            py = y0 - ty * (y0 - y1)
            points.extend([px, py])

        if len(points) >= 4:
            self.canvas.create_line(*points, fill="#1368ce", width=2, smooth=True)

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
        baseline = self._safe_float(self.measure_min_var.get(), default=0.0)
        span = max(0.1, self._safe_float(self.measure_max_var.get(), default=1.0) - baseline)
        power = baseline + 0.5 * span + 0.45 * span * math.sin(elapsed * 1.5)
        self._samples.append(SamplePoint(time_s=elapsed, power_w=power))

        if len(self._samples) > 5000:
            self._samples = self._samples[-2500:]

        self._draw_plot_frame()
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
