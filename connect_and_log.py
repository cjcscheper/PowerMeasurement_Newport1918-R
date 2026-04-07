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
from typing import Optional

import pyvisa


@dataclass
class Sample:
    elapsed_s: Decimal
    power_w: Optional[Decimal]
    raw_response: str
    iso_utc: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Connect to meter and log time + power")
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
    return value.encode("utf-8").decode("unicode_escape")


def to_decimal_seconds(delta_ns: int) -> Decimal:
    # Uses integer nanoseconds then decimal division to keep precision stable.
    return Decimal(delta_ns) / Decimal("1000000000")


def try_parse_decimal(text: str) -> Optional[Decimal]:
    cleaned = text.strip().split(",")[0]
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def format_decimal(value: Optional[Decimal]) -> str:
    return "" if value is None else format(value, "f")


def list_resources(rm: pyvisa.ResourceManager) -> int:
    resources = rm.list_resources()
    if not resources:
        print("No VISA resources found.")
        return 1

    print("Detected VISA resources:")
    for r in resources:
        print(f"  - {r}")
    return 0


def open_instrument(args: argparse.Namespace, rm: pyvisa.ResourceManager):
    instrument = rm.open_resource(args.resource)
    instrument.timeout = args.timeout_ms
    instrument.read_termination = decode_termination(args.read_termination)
    instrument.write_termination = decode_termination(args.write_termination)
    return instrument


def read_sample(instrument, start_ns: int, power_query: str) -> Sample:
    raw = instrument.query(power_query).strip()
    parsed = try_parse_decimal(raw)
    elapsed = to_decimal_seconds(time.perf_counter_ns() - start_ns)
    iso = datetime.now(timezone.utc).isoformat()
    return Sample(elapsed_s=elapsed, power_w=parsed, raw_response=raw, iso_utc=iso)


def run_logging(args: argparse.Namespace) -> int:
    rm = pyvisa.ResourceManager()
    if args.list:
        return list_resources(rm)

    if not args.resource:
        print("ERROR: --resource is required unless --list is used.", file=sys.stderr)
        return 2

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to {args.resource} ...")
    try:
        instrument = open_instrument(args, rm)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to open resource: {exc}", file=sys.stderr)
        return 3

    with instrument:
        # ID check is optional because some firmware may not support *IDN?
        try:
            idn = instrument.query(args.idn_query).strip()
            print(f"Instrument ID: {idn}")
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: ID query failed ({exc}). Continuing.")

        print(f"Logging to: {output_path}")
        print("Press Ctrl+C to stop.")

        start_ns = time.perf_counter_ns()
        samples_written = 0

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["elapsed_s", "power_w", "raw_response", "timestamp_utc"])

            while True:
                if args.max_samples > 0 and samples_written >= args.max_samples:
                    break

                try:
                    sample = read_sample(instrument, start_ns, args.power_query)
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
                f.flush()

                samples_written += 1
                print(
                    f"{samples_written:06d}  t={format_decimal(sample.elapsed_s)} s  "
                    f"P={format_decimal(sample.power_w)} W  raw='{sample.raw_response}'"
                )

                time.sleep(args.sample_interval)

    print(f"Done. Wrote {samples_written} samples to {output_path}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run_logging(args)


if __name__ == "__main__":
    raise SystemExit(main())
