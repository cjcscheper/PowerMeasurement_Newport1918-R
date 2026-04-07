#!/usr/bin/env python3
"""Minimal Newport 1918-R logger.

Phase-1 goal:
1) Connect to the instrument.
2) Record elapsed time in seconds with high precision.
3) Record power readings with maximum textual precision returned by device.

Usage examples:
  python connect_and_log.py --list
  python connect_and_log.py --resource "USB0::0x104D::0xCEC7::INSTR" \
      --output data.csv --sample-interval 0.1 --max-samples 100
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

import pyvisa


@dataclass
class Sample:
    """Single measurement sample written to CSV.

    Attributes:
        elapsed_s: Elapsed time since logging started, in seconds.
        power_w: Parsed power reading in watts (None when parsing fails).
        raw_response: Raw response string returned by the instrument.
        iso_utc: UTC timestamp in ISO-8601 format.
    """

    elapsed_s: Decimal
    power_w: Optional[Decimal]
    raw_response: str
    iso_utc: str


def build_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line parser for this script.

    Returns:
        argparse.ArgumentParser: A parser with all script options registered.
    """

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Connect to meter and log time + power"
    )
    parser.add_argument("--list", action="store_true", help="List VISA resources and exit")
    parser.add_argument("--resource", help="VISA resource string for the instrument")
    parser.add_argument("--output", default="power_log.csv", help="CSV output path")
    parser.add_argument("--sample-interval", type=float, default=0.1, help="Seconds between samples")
    parser.add_argument("--max-samples", type=int, default=0, help="Number of samples (0 = infinite)")
    parser.add_argument("--idn-query", default="*IDN?", help="Identity query command")
    parser.add_argument(
        "--power-query",
        default="MEAS:POW?",
        help="Power query command (adjust to match LabVIEW command set)",
    )
    parser.add_argument("--timeout-ms", type=int, default=5000, help="VISA timeout in milliseconds")
    parser.add_argument("--read-termination", default="\\n", help="Read termination character")
    parser.add_argument("--write-termination", default="\\n", help="Write termination character")
    return parser


def decode_termination(value: str) -> str:
    """Convert escaped termination text (e.g., ``"\\n"``) to actual characters.

    Args:
        value: User-provided string with optional escape sequences.

    Returns:
        str: Decoded termination string used by VISA read/write settings.
    """

    decoded_value: str = value.encode("utf-8").decode("unicode_escape")
    return decoded_value


def to_decimal_seconds(delta_ns: int) -> Decimal:
    """Convert nanoseconds to Decimal seconds with stable precision.

    Args:
        delta_ns: Elapsed duration in nanoseconds.

    Returns:
        Decimal: Duration represented in seconds.
    """

    seconds: Decimal = Decimal(delta_ns) / Decimal("1000000000")
    return seconds


def try_parse_decimal(text: str) -> Optional[Decimal]:
    """Try to parse the first CSV-like field from text into Decimal.

    Args:
        text: Raw response string from the instrument.

    Returns:
        Optional[Decimal]: Parsed Decimal value, or None if parsing fails.
    """

    cleaned_text: str = text.strip().split(",")[0]
    try:
        parsed_value: Decimal = Decimal(cleaned_text)
        return parsed_value
    except (InvalidOperation, ValueError):
        return None


def format_decimal(value: Optional[Decimal]) -> str:
    """Format Decimal values for CSV/console output.

    Args:
        value: Decimal value to format, or None.

    Returns:
        str: Fixed-point representation, or an empty string when value is None.
    """

    formatted_value: str = "" if value is None else format(value, "f")
    return formatted_value


def list_resources(rm: pyvisa.ResourceManager) -> int:
    """List available VISA resources.

    Args:
        rm: Active VISA resource manager.

    Returns:
        int: Exit code (0 on success, 1 when no resources are found).
    """

    resources: tuple[str, ...] = rm.list_resources()
    if not resources:
        print("No VISA resources found.")
        return 1

    print("Detected VISA resources:")
    for resource_name in resources:
        print(f"  - {resource_name}")
    return 0


def open_instrument(args: argparse.Namespace, rm: pyvisa.ResourceManager) -> Any:
    """Open and configure the target VISA instrument.

    Args:
        args: Parsed CLI arguments containing connection and termination settings.
        rm: Active VISA resource manager.

    Returns:
        Any: Opened VISA instrument handle.
    """

    instrument: Any = rm.open_resource(args.resource)
    instrument.timeout = args.timeout_ms
    instrument.read_termination = decode_termination(args.read_termination)
    instrument.write_termination = decode_termination(args.write_termination)
    return instrument


def read_sample(instrument: Any, start_ns: int, power_query: str) -> Sample:
    """Query one power sample and package it with timing/metadata.

    Args:
        instrument: Open VISA instrument handle.
        start_ns: Start time in nanoseconds from ``time.perf_counter_ns()``.
        power_query: SCPI-like command used to request power.

    Returns:
        Sample: Measurement structure containing parsed and raw values.
    """

    raw_response: str = instrument.query(power_query).strip()
    parsed_power: Optional[Decimal] = try_parse_decimal(raw_response)
    elapsed_ns: int = time.perf_counter_ns() - start_ns
    elapsed_seconds: Decimal = to_decimal_seconds(elapsed_ns)
    timestamp_utc: str = datetime.now(timezone.utc).isoformat()

    sample: Sample = Sample(
        elapsed_s=elapsed_seconds,
        power_w=parsed_power,
        raw_response=raw_response,
        iso_utc=timestamp_utc,
    )
    return sample


def run_logging(args: argparse.Namespace) -> int:
    """Execute listing mode or live logging mode based on CLI arguments.

    Args:
        args: Parsed command-line arguments.

    Returns:
        int: Process exit code.
    """

    resource_manager: pyvisa.ResourceManager = pyvisa.ResourceManager()
    if args.list:
        return list_resources(resource_manager)

    if not args.resource:
        print("ERROR: --resource is required unless --list is used.", file=sys.stderr)
        return 2

    output_path: Path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to {args.resource} ...")
    try:
        instrument: Any = open_instrument(args, resource_manager)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to open resource: {exc}", file=sys.stderr)
        return 3

    with instrument:
        try:
            instrument_id: str = instrument.query(args.idn_query).strip()
            print(f"Instrument ID: {instrument_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: ID query failed ({exc}). Continuing.")

        print(f"Logging to: {output_path}")
        print("Press Ctrl+C to stop.")

        start_ns: int = time.perf_counter_ns()
        samples_written: int = 0

        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer: csv.writer = csv.writer(csv_file)
            writer.writerow(["elapsed_s", "power_w", "raw_response", "timestamp_utc"])

            while True:
                if args.max_samples > 0 and samples_written >= args.max_samples:
                    break

                try:
                    sample: Sample = read_sample(instrument, start_ns, args.power_query)
                except KeyboardInterrupt:
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"Read warning: {exc}", file=sys.stderr)
                    continue

                writer.writerow(
                    [
                        format_decimal(sample.elapsed_s),
                        format_decimal(sample.power_w),
                        sample.raw_response,
                        sample.iso_utc,
                    ]
                )
                csv_file.flush()

                samples_written += 1
                print(
                    f"{samples_written:06d}  t={format_decimal(sample.elapsed_s)} s  "
                    f"P={format_decimal(sample.power_w)} W  raw='{sample.raw_response}'"
                )

                time.sleep(args.sample_interval)

    print(f"Done. Wrote {samples_written} samples to {output_path}")
    return 0


def main() -> int:
    """Parse CLI arguments and run the logger.

    Returns:
        int: Process exit code from ``run_logging``.
    """

    parser: argparse.ArgumentParser = build_parser()
    parsed_args: argparse.Namespace = parser.parse_args()
    return run_logging(parsed_args)


if __name__ == "__main__":
    raise SystemExit(main())
