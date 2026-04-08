#!/usr/bin/env python3
"""Simulation + profiling harness for Newport 1918-R logging workflow.

This script avoids hardware dependencies by using a simulated instrument that
returns deterministic power readings. It also times key functions so bottlenecks
can be tracked over time.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

from connect_and_log import (
    Sample,
    csv_filename_from_iso_utc,
    format_decimal,
    read_sample,
    to_decimal_seconds,
    try_parse_decimal,
)


@dataclass
class ProfileRecord:
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0

    def add(self, duration_ms: float) -> None:
        self.count += 1
        self.total_ms += duration_ms
        self.min_ms = min(self.min_ms, duration_ms)
        self.max_ms = max(self.max_ms, duration_ms)

    @property
    def avg_ms(self) -> float:
        return 0.0 if self.count == 0 else self.total_ms / self.count


class FunctionProfiler:
    """Tiny profiler for named callables."""

    def __init__(self) -> None:
        self.records: dict[str, ProfileRecord] = defaultdict(ProfileRecord)
        self.samples: dict[str, list[float]] = defaultdict(list)

    def time_call(self, name: str, fn: Callable[..., object], *args: object, **kwargs: object) -> object:
        t0_ns: int = time.perf_counter_ns()
        result: object = fn(*args, **kwargs)
        duration_ms: float = (time.perf_counter_ns() - t0_ns) / 1_000_000.0
        self.records[name].add(duration_ms)
        self.samples[name].append(duration_ms)
        return result

    def print_summary(self) -> None:
        print("\nFunction timing summary (simulation)")
        headers = ["Function", "Count", "Avg (ms)", "P50 (ms)", "P95 (ms)", "Min (ms)", "Max (ms)", "Total (ms)"]

        rows: list[list[str]] = []
        for name in sorted(self.records):
            record = self.records[name]
            latencies = sorted(self.samples[name])
            p50 = statistics.median(latencies) if latencies else 0.0
            p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0.0
            rows.append(
                [
                    name,
                    str(record.count),
                    f"{record.avg_ms:.6f}",
                    f"{p50:.6f}",
                    f"{p95:.6f}",
                    f"{record.min_ms:.6f}",
                    f"{record.max_ms:.6f}",
                    f"{record.total_ms:.6f}",
                ]
            )

        widths = [len(header) for header in headers]
        for row in rows:
            for i, value in enumerate(row):
                widths[i] = max(widths[i], len(value))

        def make_row(values: list[str]) -> str:
            padded = [value.ljust(widths[i]) for i, value in enumerate(values)]
            return f"| {' | '.join(padded)} |"

        separator = f"+-{'-+-'.join('-' * width for width in widths)}-+"
        print(separator)
        print(make_row(headers))
        print(separator)
        for row in rows:
            print(make_row(row))
        print(separator)


class SimulatedInstrument:
    """Simple query() compatible object for offline testing."""

    def __init__(self, base_watts: Decimal, noise_watts: Decimal) -> None:
        self.base_watts = base_watts
        self.noise_watts = noise_watts
        self.read_count = 0

    def query(self, command: str) -> str:
        if command.strip().upper() == "*IDN?":
            return "SIMULATED,Newport1918R,000000,1.0"

        phase = Decimal(self.read_count % 10) - Decimal("5")
        value = self.base_watts + (phase * self.noise_watts / Decimal("5"))
        self.read_count += 1
        return format(value, "f")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run simulated measurements and profile function timings")
    parser.add_argument("--max-samples", type=int, default=100, help="Number of simulated samples")
    parser.add_argument("--sample-interval", type=float, default=0.05, help="Seconds between samples")
    parser.add_argument("--power-query", default="MEAS:POW?", help="Power query command")
    parser.add_argument("--output-dir", default=".", help="Directory for generated CSV")
    parser.add_argument("--base-watts", default="0.001000", help="Base simulated power in watts")
    parser.add_argument("--noise-watts", default="0.000050", help="Peak-to-peak style noise magnitude")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profiler = FunctionProfiler()

    base_watts = Decimal(args.base_watts)
    noise_watts = Decimal(args.noise_watts)
    instrument = SimulatedInstrument(base_watts=base_watts, noise_watts=noise_watts)

    start_ns = time.perf_counter_ns()
    output_path: Optional[Path] = None
    csv_file = None
    writer: Optional[csv.writer] = None

    try:
        for _ in range(args.max_samples):
            sample = profiler.time_call("read_sample", read_sample, instrument, start_ns, args.power_query)
            assert isinstance(sample, Sample)

            profiler.time_call("try_parse_decimal", try_parse_decimal, sample.raw_response)
            profiler.time_call("format_decimal_elapsed", format_decimal, sample.elapsed_s)
            profiler.time_call("format_decimal_power", format_decimal, sample.power_w)
            profiler.time_call("to_decimal_seconds", to_decimal_seconds, 123_456_789)

            if output_path is None:
                filename = profiler.time_call("csv_filename_from_iso_utc", csv_filename_from_iso_utc, sample.iso_utc)
                assert isinstance(filename, str)
                output_path = Path(args.output_dir) / filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
                csv_file = output_path.open("w", newline="", encoding="utf-8")
                writer = csv.writer(csv_file)
                writer.writerow(["elapsed_s", "power_w", "raw_response", "timestamp_utc"])

            assert writer is not None
            writer.writerow(
                [
                    format_decimal(sample.elapsed_s),
                    format_decimal(sample.power_w),
                    sample.raw_response,
                    sample.iso_utc,
                ]
            )

            if args.sample_interval > 0:
                profiler.time_call("sleep", time.sleep, args.sample_interval)
    finally:
        if csv_file is not None:
            csv_file.close()

    idn = profiler.time_call("idn_query", instrument.query, "*IDN?")
    print(f"Simulated IDN: {idn}")
    print(f"Samples written: {args.max_samples}")
    print(f"CSV output: {output_path}")
    print(f"Completed at: {datetime.now(timezone.utc).isoformat()}")
    profiler.print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
