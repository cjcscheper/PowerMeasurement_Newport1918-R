#!/usr/bin/env python3
"""Plot laser spot position metrics alongside lab temperature data.

The script ingests a temperature log and a spot position file named in the
``spot_position_YYYYMMDD_HHMMSS.txt`` format, builds a timestamped series for the
spot frames (one-minute cadence), and produces two plots:

1. Temperature plus the five spot parameters (and the r^2 shift from frame 0)
   versus time, sharing the same x-axis.
2. The r^2 shift versus temperature, aligning temperature readings to the
   closest spot timestamp.

Usage example::

    python analyze_spot_and_temperature.py \\
        --temperature-file path/to/lab_temperature.csv \\
        --spot-file data/spot_position_20240522_153000.txt \\
        --output-dir plots
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Tuple

import matplotlib.pyplot as plt
import pandas as pd

SPOT_FILENAME_PATTERN = re.compile(r"spot_position_(\d{8})_(\d{6})\.txt$")


def parse_spot_start_datetime(path: Path) -> datetime:
    """Parse the acquisition start datetime from a spot filename.

    Expected format: ``spot_position_YYYYMMDD_HHMMSS.txt``. Returns a naïve
    ``datetime`` object interpreted in the local timezone context.
    """
    match = SPOT_FILENAME_PATTERN.search(path.name)
    if not match:
        raise ValueError(
            f"Filename '{path.name}' does not match 'spot_position_YYYYMMDD_HHMMSS.txt'"
        )

    date_str, time_str = match.groups()
    return datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")


def clean_number(value: str) -> float:
    """Convert numbers that use repeated dots as thousands/decimal separators.

    The sample data uses strings such as ``20.369.706`` to represent
    ``20.369706``. This helper keeps the first dot (treated as the decimal
    separator) and strips any subsequent dots before converting to ``float``.
    Commas are normalized to dots as well to keep parsing permissive.
    """
    if pd.isna(value):
        return float("nan")

    text = str(value).strip().replace(",", ".")
    if text.count(".") > 1:
        first_dot = text.find(".")
        text = text[: first_dot + 1] + text[first_dot + 1 :].replace(".", "")

    return float(text)


def load_spot_positions(spot_path: Path) -> pd.DataFrame:
    """Load spot ellipse parameters and attach timestamps and r^2 shift."""
    start_dt = parse_spot_start_datetime(spot_path)

    spot_df = pd.read_csv(spot_path, sep=r"\s+", engine="python")
    required_columns = [
        "frame_index",
        "center_x_mm",
        "center_y_mm",
        "minor_axis_mm",
        "major_axis_mm",
        "angle_deg",
    ]

    missing_columns = [col for col in required_columns if col not in spot_df.columns]
    if missing_columns:
        raise ValueError(
            f"Spot file {spot_path} is missing required columns: {missing_columns}"
        )

    spot_df["frame_index"] = spot_df["frame_index"].astype(int)
    for column in required_columns[1:]:
        spot_df[column] = spot_df[column].apply(clean_number)

    reference_x = spot_df.at[0, "center_x_mm"]
    reference_y = spot_df.at[0, "center_y_mm"]
    spot_df["timestamp"] = spot_df["frame_index"].apply(
        lambda frame: start_dt + timedelta(minutes=int(frame))
    )
    spot_df["r_squared_shift_mm2"] = (
        (spot_df["center_x_mm"] - reference_x) ** 2
        + (spot_df["center_y_mm"] - reference_y) ** 2
    )

    return spot_df


def _identify_temperature_columns(df: pd.DataFrame) -> Tuple[str, str]:
    """Heuristically identify timestamp and temperature columns."""
    timestamp_candidates = [
        col
        for col in df.columns
        if "time" in col.lower() or "date" in col.lower() or col.lower() == "timestamp"
    ]
    if not timestamp_candidates:
        timestamp_candidates = [df.columns[0]]

    value_candidates = [
        col
        for col in df.columns
        if col not in timestamp_candidates
        and any(key in col.lower() for key in ["temp", "deg", "celsius"])
    ]
    if not value_candidates:
        value_candidates = [
            col
            for col in df.columns
            if col not in timestamp_candidates and pd.api.types.is_numeric_dtype(df[col])
        ]

    if not timestamp_candidates or not value_candidates:
        raise ValueError(
            "Could not infer timestamp/temperature columns. Please ensure the file has "
            "a time column and a temperature column."
        )

    return timestamp_candidates[0], value_candidates[0]


def load_temperature_data(temp_path: Path) -> pd.DataFrame:
    """Load temperature data using the same CSV-style workflow as before."""
    temp_df = pd.read_csv(temp_path)
    timestamp_col, temperature_col = _identify_temperature_columns(temp_df)

    temp_df["timestamp"] = pd.to_datetime(temp_df[timestamp_col])
    temp_df["temperature_C"] = pd.to_numeric(temp_df[temperature_col], errors="coerce")
    temp_df = temp_df.dropna(subset=["timestamp", "temperature_C"])
    return temp_df.sort_values("timestamp").reset_index(drop=True)


def plot_time_series(
    temp_df: pd.DataFrame, spot_df: pd.DataFrame, output_path: Path
) -> None:
    """Plot temperature and spot parameters versus time with shared x-axis."""
    fig, (ax_temp, ax_params) = plt.subplots(
        2, 1, figsize=(11, 9), sharex=True, constrained_layout=True
    )

    ax_temp.plot(
        temp_df["timestamp"], temp_df["temperature_C"], color="tab:red", label="Temperature (°C)"
    )
    ax_temp.set_ylabel("Temperature (°C)")
    ax_temp.legend(loc="best")
    ax_temp.grid(True, linestyle=":", alpha=0.6)

    parameter_columns = [
        "center_x_mm",
        "center_y_mm",
        "minor_axis_mm",
        "major_axis_mm",
        "angle_deg",
    ]
    for column in parameter_columns:
        ax_params.plot(spot_df["timestamp"], spot_df[column], label=column)

    ax_params.plot(
        spot_df["timestamp"],
        spot_df["r_squared_shift_mm2"],
        label="r^2 shift (mm²)",
        linestyle="--",
        color="black",
    )
    ax_params.set_ylabel("Spot parameters")
    ax_params.legend(loc="best", ncol=2)
    ax_params.grid(True, linestyle=":", alpha=0.6)

    ax_params.set_xlabel("Timestamp")
    fig.suptitle("Temperature and Spot Position Parameters vs Time")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_r2_vs_temperature(
    temp_df: pd.DataFrame, spot_df: pd.DataFrame, output_path: Path
) -> None:
    """Plot r^2 shift against temperature using nearest timestamps for alignment."""
    merged = pd.merge_asof(
        spot_df.sort_values("timestamp"),
        temp_df.sort_values("timestamp"),
        on="timestamp",
        direction="nearest",
    )

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(
        merged["temperature_C"], merged["r_squared_shift_mm2"], c="tab:blue", alpha=0.75
    )
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("r^2 shift from frame 0 (mm²)")
    ax.set_title("Spot displacement vs Temperature")
    ax.grid(True, linestyle=":", alpha=0.6)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate plots comparing laser spot position to lab temperature."
    )
    parser.add_argument(
        "--temperature-file",
        type=Path,
        required=True,
        help="CSV file containing temperature readings (timestamp + temperature).",
    )
    parser.add_argument(
        "--spot-file",
        type=Path,
        required=True,
        help="Spot position file named spot_position_YYYYMMDD_HHMMSS.txt",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("plots"),
        help="Directory to write plot images to (default: ./plots)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    temperature_df = load_temperature_data(args.temperature_file)
    spot_df = load_spot_positions(args.spot_file)

    output_dir: Path = args.output_dir
    plot_time_series(temperature_df, spot_df, output_dir / "spot_parameters_vs_time.png")
    plot_r2_vs_temperature(temperature_df, spot_df, output_dir / "spot_shift_vs_temperature.png")


if __name__ == "__main__":
    main()
