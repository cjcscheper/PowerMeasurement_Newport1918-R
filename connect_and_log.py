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
    """
    Create and configure the command-line argument parser for this script.

    A parser (specifically argparse.ArgumentParser) is an object that defines how
    command-line arguments should be interpreted. It reads input provided when
    running the script (e.g., via the terminal), validates it, converts it to the
    correct types, and makes it accessible as attributes on a returned namespace.

    For example:
        python script.py --resource USB0::0x1234::0x5678::INSTR --output data.csv

    The parser will interpret these flags and return an object such that:
        args.resource == "USB0::0x1234::0x5678::INSTR"
        args.output == "data.csv"

    Returns:
        argparse.ArgumentParser:
            A fully configured parser with all supported command-line options.

    Registered arguments:
        --list (bool):
            If provided, lists all available VISA resources and exits the program.
            This is typically used to discover connected instruments.

        --resource (str):
            The VISA resource string identifying the instrument to connect to.
            Example: "USB0::0x1234::0x5678::INSTR"

        --output (str, default="power_log.csv"):
            File path where sampled data will be written as CSV.

        --sample-interval (float, default=0.1):
            Time in seconds between consecutive measurements.

        --max-samples (int, default=0):
            Maximum number of samples to collect.
            A value of 0 means sampling will continue indefinitely.

        --idn-query (str, default="*IDN?"):
            SCPI command used to query the instrument identity.

        --power-query (str, default="MEAS:POW?"):
            SCPI command used to query power measurements.
            May need adjustment depending on the instrument's command set.

        --timeout-ms (int, default=5000):
            Communication timeout in milliseconds for VISA operations.

        --read-termination (str, default="\\n"):
            Character(s) indicating the end of a read response.

        --write-termination (str, default="\\n"):
            Character(s) appended to commands sent to the instrument.

    Usage:
        1. Build the parser:
            parser = build_parser()

        2. Parse command-line arguments:
            args = parser.parse_args()

        3. Access values via attributes:
            print(args.resource)
            print(args.sample_interval)

        4. Example full command:
            python script.py --resource USB0::... --sample-interval 0.5 --max-samples 100
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
    """Convert a user-provided escaped string into its literal character form.

    This function is primarily used to translate command-line input representing
    termination characters (e.g., "\\n", "\\r\\n", "\\t") into the actual characters
    expected by VISA communication settings.

    In many CLI contexts, users must provide escape sequences as *text* (e.g., the
    two-character string "\\" + "n"), because the shell does not automatically
    interpret them as control characters. This function decodes those sequences
    into their true representations (e.g., newline, carriage return).

    Internally, this is achieved by encoding the string to bytes and then decoding
    it using the "unicode_escape" codec, which interprets Python-style escape
    sequences.

    Args:
        value (str):
            A string potentially containing escape sequences. Common examples:
                "\\n"      → newline character
                "\\r\\n"   → carriage return + newline
                "\\t"      → tab
                ""         → empty string (no termination)

    Returns:
        str:
            The decoded string with escape sequences converted to their literal
            character equivalents. This value can be passed directly to VISA
            attributes such as `read_termination` or `write_termination`.

    Examples:
        >>> decode_termination("\\n")
        '\\n'  # actual newline character

        >>> decode_termination("\\r\\n")
        '\\r\\n'  # carriage return + newline

        >>> decode_termination(";")
        ';'  # unchanged (no escape sequences)

    Notes:
        - If the input contains invalid or incomplete escape sequences, Python's
          "unicode_escape" decoding may raise a UnicodeDecodeError.
        - This function assumes input follows Python-style escape conventions.
        - Double-escaping may occur depending on how the shell passes arguments;
          users should verify input if results are unexpected.

    Typical usage:
        term = decode_termination(args.read_termination)
        instrument.read_termination = term
    """

    decoded_value: str = value.encode("utf-8").decode("unicode_escape")
    return decoded_value


def to_decimal_seconds(delta_ns: int) -> Decimal:
    """Convert a duration from nanoseconds to seconds using Decimal for precision.

    This function converts an integer duration expressed in nanoseconds into a
    Decimal representation of seconds. It is designed to preserve numerical
    stability and avoid floating-point rounding errors that can occur when using
    standard `float` arithmetic—especially important in high-resolution timing,
    logging, or scientific measurement contexts.

    Instead of dividing by a floating-point value (1e9), the function performs
    the operation entirely using Decimal objects, ensuring exact representation
    of both the numerator and denominator.

    Args:
        delta_ns (int):
            Elapsed time in nanoseconds. Typically obtained from high-resolution
            timers such as `time.perf_counter_ns()` or similar APIs.

    Returns:
        Decimal:
            The equivalent duration in seconds, represented with arbitrary
            precision (subject to the current Decimal context).

    Examples:
        >>> to_decimal_seconds(1_000_000_000)
        Decimal('1')

        >>> to_decimal_seconds(123_456_789)
        Decimal('0.123456789')

    Notes:
        - Using Decimal avoids cumulative precision errors that may arise when
          repeatedly summing or logging time intervals with floats.
        - The precision and rounding behavior are governed by the active
          Decimal context (`decimal.getcontext()`).
        - This is particularly useful when writing time-series data to CSV or
          performing post-processing that requires exact decimal representation.

    Typical usage:
        start = time.perf_counter_ns()
        ...
        end = time.perf_counter_ns()
        elapsed = to_decimal_seconds(end - start)
        print(elapsed)  # precise decimal seconds
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
