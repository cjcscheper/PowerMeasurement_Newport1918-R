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
            python script.py --resource USB0::--sample-interval 0.5 --max-samples 100
    """

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Connect to meter and log time + power"
    )
    parser.add_argument("--list", action="store_true", help="List VISA resources and exit")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Open instrument, run ID and single power query, then exit",
    )
    parser.add_argument("--resource", help="VISA resource string for the instrument")
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "CSV output path. If omitted, filename is derived from first sample timestamp as "
            "YYYY-MM-DD-hh-mm-ss_Newport1918R.csv"
        ),
    )
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
        decode_termination("\\n")
        '\\n'  # actual newline character

        decode_termination("\\r\\n")
        '\\r\\n'  # carriage return + newline

        decode_termination(";")
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
        to_decimal_seconds(1_000_000_000)
        Decimal('1')

        to_decimal_seconds(123_456_789)
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
    """Attempt to extract and parse a numeric value from instrument response text.

    This function processes a raw response string—typically returned by a
    measurement instrument—and attempts to convert the first CSV-like field
    into a `Decimal`. Many instruments return values in formats such as:

        "123.45"
        "123.45,OK"
        "123.45,0"
        "  123.45\\n"

    The function performs minimal normalization by:
        1. Stripping leading/trailing whitespace
        2. Splitting on commas (",") and selecting the first field

    This makes it resilient to common SCPI-style responses where additional
    metadata or status codes follow the primary numeric value.

    Args:
        text (str):
            Raw response string from the instrument. May include whitespace,
            newline characters, or comma-separated fields.

    Returns:
        Optional[Decimal]:
            - A `Decimal` representing the parsed numeric value if successful
            - `None` if parsing fails due to invalid format or non-numeric content

    Examples:
        try_parse_decimal("123.45")
        Decimal('123.45')

        try_parse_decimal("123.45,OK")
        Decimal('123.45')

        try_parse_decimal("  123.45\\n")
        Decimal('123.45')

        try_parse_decimal("ERROR")
        None

        try_parse_decimal("")
        None

    Notes:
        - Parsing is strict: the extracted field must be directly interpretable
          by `Decimal`. Scientific notation (e.g., "1.23E-3") is supported.
        - Only the first comma-separated field is considered; additional fields
          are ignored.
        - If the instrument returns localized formats (e.g., commas as decimal
          separators), this function will not handle them correctly without
          preprocessing.

    Typical usage:
        response = instrument.query("MEAS:POW?")
        value = try_parse_decimal(response)

        if value is None:
            log.warning("Failed to parse measurement: %r", response)
        else:
            process(value)
    """

    cleaned_text: str = text.strip().split(",")[0]
    try:
        parsed_value: Decimal = Decimal(cleaned_text)
        return parsed_value
    except (InvalidOperation, ValueError):
        return None


def format_decimal(value: Optional[Decimal]) -> str:
    """Format a Decimal value as a fixed-point string for output.

    This function converts a `Decimal` value into a string representation suitable
    for CSV files or console output. It ensures a consistent, non-scientific notation
    (fixed-point) format, which is often required for interoperability with tools
    like spreadsheets, data pipelines, or logging systems.

    If the input is `None`, the function returns an empty string. This allows
    seamless handling of missing or invalid values (e.g., failed parses) without
    introducing placeholders like "None" or "NaN" into the output.

    Internally, the function uses Python's built-in `format(..., "f")`, which:
        - Produces a fixed-point decimal representation
        - Avoids scientific notation (e.g., "1E-6" → "0.000001")
        - Preserves the full precision of the Decimal value

    Args:
        value (Optional[Decimal]):
            The Decimal value to format. If `None`, it is treated as missing data.

    Returns:
        str:
            - A fixed-point string representation of the Decimal value
            - An empty string ("") if `value` is None

    Examples:
        format_decimal(Decimal("123.45"))
        "123.45"

        format_decimal(Decimal("1E-6"))
        "0.000001"

        format_decimal(None)
        ""

    Notes:
        - The exact number of digits shown depends on the Decimal's internal
          representation and the current context; no rounding or quantization
          is applied.
        - If consistent column width or precision is required (e.g., always
          6 decimal places), consider applying `value.quantize(...)` before
          formatting.
        - Returning an empty string for None is useful for CSV output, where
          missing fields are typically represented as empty cells.

    Typical usage:
        value = try_parse_decimal(response)
        output_str = format_decimal(value)
        csv_writer.writerow([timestamp, output_str])
    """

    formatted_value: str = "" if value is None else format(value, "f")
    return formatted_value


def csv_filename_from_iso_utc(iso_utc: str) -> str:
    """Build CSV filename from a sample UTC timestamp.

    Format:
        YYYY-MM-DD-hh-mm-ss_Newport1918R.csv
    """

    timestamp: datetime = datetime.fromisoformat(iso_utc)
    return f"{timestamp.strftime('%Y-%m-%d-%H-%M-%S')}_Newport1918R.csv"


def list_resources(rm: pyvisa.ResourceManager) -> int:
    """Enumerate and display available VISA resources.

    This function queries the provided PyVISA ResourceManager for all detected
    VISA resources (i.e., connected instruments or interfaces) and prints them
    to standard output in a human-readable format.

    A VISA resource represents an addressable instrument or interface, such as:
        - USB instruments (e.g., "USB0::0x1234::0x5678::INSTR")
        - GPIB devices (e.g., "GPIB0::14::INSTR")
        - Serial ports (e.g., "ASRL3::INSTR")
        - TCP/IP instruments (e.g., "TCPIP0::192.168.0.10::INSTR")

    This function is typically used as a discovery step to help users identify
    the correct resource string required for establishing communication with
    an instrument.

    Args:
        rm (pyvisa.ResourceManager):
            An initialized PyVISA ResourceManager instance used to query
            available resources. This object manages communication backends
            (e.g., NI-VISA, pyvisa-py).

    Returns:
        int:
            Exit status code:
                - 0: One or more resources were found and listed successfully
                - 1: No resources were detected

    Behavior:
        - Calls `rm.list_resources()` to retrieve a tuple of resource strings
        - Prints a header followed by each resource on its own line
        - Prints a message if no resources are found

    Examples:
        rm = pyvisa.ResourceManager()
        list_resources(rm)
        Detected VISA resources:
          - USB0::0x1234::0x5678::INSTR
          - TCPIP0::192.168.0.10::INSTR
        0

        # No devices connected
        list_resources(rm)
        No VISA resources found.
        1

    Notes:
        - The availability of resources depends on the installed VISA backend
          and connected hardware.
        - If using the pure Python backend (`pyvisa-py`), ensure the appropriate
          drivers (e.g., USBTMC, serial) are available on the system.
        - This function performs no filtering; all detected resources are shown.

    Typical usage:
        rm = pyvisa.ResourceManager()
        exit_code = list_resources(rm)
        sys.exit(exit_code)
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
    """Open and configure a VISA instrument session based on CLI arguments.

    This function establishes a connection to a measurement instrument using a
    VISA resource string and applies communication settings such as timeouts
    and termination characters. It acts as a thin abstraction over
    `pyvisa.ResourceManager.open_resource`, augmenting it with user-provided
    configuration from parsed command-line arguments.

    A VISA instrument session represents an active communication channel to a
    device (e.g., power meter, oscilloscope, multimeter) over interfaces such
    as USB, GPIB, serial, or TCP/IP.

    Args:
        args (argparse.Namespace):
            Parsed command-line arguments, typically produced by
            `ArgumentParser.parse_args()`. The following attributes are expected:
                - resource (str):
                    VISA resource string identifying the instrument
                    (e.g., "USB0::0x1234::0x5678::INSTR")
                - timeout_ms (int):
                    Communication timeout in milliseconds
                - read_termination (str):
                    Read termination sequence (may include escaped characters
                    such as "\\n", "\\r\\n")
                - write_termination (str):
                    Write termination sequence (may include escaped characters)

        rm (pyvisa.ResourceManager):
            An initialized PyVISA ResourceManager used to open the connection.

    Returns:
        Any:
            A PyVISA instrument handle (typically a `pyvisa.resources.MessageBasedResource`
            or subclass) that can be used to send commands (`write`, `query`)
            and read responses from the instrument.

    Behavior:
        - Opens the instrument using the provided resource string
        - Sets the communication timeout (`instrument.timeout`)
        - Decodes and applies read/write termination characters using
          `decode_termination`
        - Returns the configured instrument handle

    Raises:
        pyvisa.errors.VisaIOError:
            If the resource cannot be opened (e.g., invalid resource string,
            device not connected, or backend issue)
        AttributeError:
            If required attributes are missing from `args`

    Examples:
        args = parser.parse_args([
            "--resource", "USB0::0x1234::0x5678::INSTR",
            "--timeout-ms", "3000"
        ])
        rm = pyvisa.ResourceManager()
        inst = open_instrument(args, rm)
        inst.query("*IDN?")
        "Manufacturer,Model,Serial,1.0"

    Notes:
        - Termination characters are critical for correct communication:
            * Read termination defines when a response is considered complete
            * Write termination is appended to each command sent
        - Incorrect termination settings are a common source of timeouts or
          partial reads.
        - The returned object should be explicitly closed when no longer needed:
              inst.close()

    Typical usage:
        rm = pyvisa.ResourceManager()
        inst = open_instrument(args, rm)

        idn = inst.query(args.idn_query)
        print(idn)
    """

    instrument: Any = rm.open_resource(args.resource)
    instrument.timeout = args.timeout_ms
    instrument.read_termination = decode_termination(args.read_termination)
    instrument.write_termination = decode_termination(args.write_termination)
    return instrument


def read_sample(instrument: Any, start_ns: int, power_query: str) -> Sample:
    """Acquire a single power measurement and annotate it with timing metadata.

    This function performs one measurement cycle by sending a query command to
    the instrument, parsing the returned value, and packaging it together with
    precise timing and timestamp information into a `Sample` structure.

    The timing model is relative: elapsed time is computed from a shared
    reference (`start_ns`) using a high-resolution monotonic clock
    (`time.perf_counter_ns`). This avoids issues with system clock adjustments
    and ensures stable interval measurement.

    Args:
        instrument (Any):
            An open PyVISA instrument handle (typically a
            `MessageBasedResource`) that supports `.query()`.

        start_ns (int):
            Reference start time in nanoseconds, typically obtained from
            `time.perf_counter_ns()` at the beginning of the logging session.

        power_query (str):
            SCPI-like command used to request a power measurement from the
            instrument (e.g., "MEAS:POW?").

    Returns:
        Sample:
            A structured record containing:
                - elapsed_s (Decimal): Time since start, in seconds
                - power_w (Optional[Decimal]): Parsed power value (None if parsing fails)
                - raw_response (str): Raw instrument response (trimmed)
                - iso_utc (str): UTC timestamp in ISO 8601 format

    Behavior:
        - Sends `power_query` to the instrument via `.query()`
        - Strips trailing whitespace from the response
        - Attempts to parse the first numeric field using `try_parse_decimal`
        - Computes elapsed time relative to `start_ns`
        - Captures a wall-clock UTC timestamp for traceability
        - Returns all data as a `Sample` instance

    Raises:
        Exception:
            Propagates any communication or query errors raised by the
            instrument (e.g., timeouts, VISA I/O errors)

    Examples:
        start = time.perf_counter_ns()
        sample = read_sample(inst, start, "MEAS:POW?")
        sample.power_w
        Decimal('12.34')

    Notes:
        - The function does not perform retries; transient failures should be
          handled by the caller.
        - `elapsed_s` is monotonic and suitable for time-series analysis,
          whereas `iso_utc` provides real-world correlation.
        - Parsing failures do not raise exceptions; instead, `power_w` is set
          to None to preserve the raw response for diagnostics.

    Typical usage:
        sample = read_sample(instrument, start_ns, args.power_query)
        writer.writerow([...])
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
    """Execute either resource listing or continuous measurement logging.

    This function is the main orchestration entry point for the script. It
    interprets CLI arguments to either:
        1. List available VISA resources (`--list` mode), or
        2. Connect to a specified instrument and log power measurements to CSV

    In logging mode, the function establishes a VISA session, optionally queries
    the instrument identity, and enters a sampling loop that:
        - Acquires measurements at fixed intervals
        - Writes structured data to a CSV file
        - Prints a live status line to the console

    Args:
        args (argparse.Namespace):
            Parsed command-line arguments. Expected attributes include:
                - list (bool): Enable resource listing mode
                - resource (str): VISA resource string
                - output (str): Output CSV file path
                - sample_interval (float): Delay between samples (seconds)
                - max_samples (int): Maximum number of samples (0 = infinite)
                - idn_query (str): Identity query command
                - power_query (str): Measurement query command

    Returns:
        int:
            Process exit code:
                - 0: Success
                - 1: No resources found (listing mode)
                - 2: Missing required arguments
                - 3: Failed to open instrument

    Behavior:
        Initialization:
            - Creates a PyVISA ResourceManager
            - Handles `--list` mode early and exits if requested
            - Validates required arguments (e.g., `--resource`)
            - Ensures output directory exists

        Connection:
            - Opens and configures the instrument via `open_instrument`
            - Attempts an identification query (`*IDN?` by default)

        Logging loop:
            - Opens CSV file and writes header row
            - Repeatedly:
                * Reads a sample using `read_sample`
                * Writes formatted values to CSV
                * Flushes output to disk (minimizing data loss risk)
                * Prints progress to console
                * Sleeps for `sample_interval`

        Termination:
            - Stops when:
                * `max_samples` is reached (if > 0), or
                * User interrupts with Ctrl+C
            - Prints summary of samples written

    Error handling:
        - Connection failures result in exit code 3
        - Read errors are logged as warnings and skipped
        - KeyboardInterrupt cleanly terminates the loop
        - ID query failures are non-fatal

    Examples:
        args = parser.parse_args([
            "--resource", "USB0::0x1234::0x5678::INSTR",
            "--output", "log.csv",
            "--sample-interval", "0.5",
            "--max-samples", "100"
        ])
        run_logging(args)
        0

    Notes:
        - The CSV is flushed after each write, trading performance for safety.
        - Timing accuracy depends on `time.sleep()` and system scheduling;
          this is not a real-time data acquisition loop.
        - Instrument communication errors are tolerated to allow long-running
          logging sessions.

    Typical usage:
        if __name__ == "__main__":
            parser = build_parser()
            args = parser.parse_args()
            sys.exit(run_logging(args))
    """

    resource_manager: pyvisa.ResourceManager = pyvisa.ResourceManager()
    if args.list:
        return list_resources(resource_manager)

    if not args.resource:
        print("ERROR: --resource is required unless --list is used.", file=sys.stderr)
        return 2

    output_arg: Optional[str] = args.output
    output_path: Optional[Path] = Path(output_arg) if output_arg else None
    if output_path is not None:
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

        if args.check:
            try:
                sample = read_sample(
                    instrument=instrument,
                    start_ns=time.perf_counter_ns(),
                    power_query=args.power_query,
                )
                print(
                    "Connection check OK: "
                    f"power={format_decimal(sample.power_w)} W "
                    f"(raw='{sample.raw_response}')"
                )
                return 0
            except Exception as exc:  # noqa: BLE001
                print(f"Connection check failed during power query: {exc}", file=sys.stderr)
                return 4

        print("Press Ctrl+C to stop.")

        start_ns: int = time.perf_counter_ns()
        samples_written: int = 0

        writer: Optional[csv.writer] = None
        csv_file: Optional[Any] = None

        try:
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

                if csv_file is None:
                    if output_path is None:
                        output_path = Path(csv_filename_from_iso_utc(sample.iso_utc))
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    print(f"Logging to: {output_path}")
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
                assert csv_file is not None
                csv_file.flush()

                samples_written += 1
                print(
                    f"{samples_written:06d}  t={format_decimal(sample.elapsed_s)} s  "
                    f"P={format_decimal(sample.power_w)} W  raw='{sample.raw_response}'"
                )

                time.sleep(args.sample_interval)
        finally:
            if csv_file is not None:
                csv_file.close()

    final_output_path: str = str(output_path) if output_path is not None else "(no file written)"
    print(f"Done. Wrote {samples_written} samples to {final_output_path}")
    return 0


def main() -> int:
    """Entry point for the CLI application.

    This function is responsible for:
        1. Constructing the command-line argument parser
        2. Parsing user-provided CLI arguments
        3. Dispatching execution to the main application logic (`run_logging`)

    It serves as the top-level coordination layer between user input (CLI)
    and the program’s operational behavior.

    Returns:
        int:
            Process exit code returned by `run_logging`, suitable for use with
            `sys.exit()`. Typical values include:
                - 0: Successful execution
                - Non-zero: Error or early termination condition

    Behavior:
        - Calls `build_parser()` to define supported CLI options
        - Parses arguments from `sys.argv` using `parse_args()`
        - Passes the parsed arguments to `run_logging()`
        - Returns the resulting exit code without modification

    Raises:
        SystemExit:
            Raised implicitly by `argparse` if argument parsing fails
            (e.g., invalid flags or `--help` invocation)

    Examples:
        if __name__ == "__main__":
            import sys
            sys.exit(main())

        Command-line usage:
            python script.py --resource USB0::--output log.csv

    Notes:
        - This function intentionally contains minimal logic to keep the entry
          point simple and testable.
        - All operational behavior (I/O, logging, instrument interaction) is
          delegated to `run_logging`.
        - Separating `main()` from `run_logging()` improves reusability and
          allows programmatic invocation without CLI parsing.

    Typical usage:
        # Standard Python entry point pattern
        if __name__ == "__main__":
            sys.exit(main())
    """

    parser: argparse.ArgumentParser = build_parser()
    parsed_args: argparse.Namespace = parser.parse_args()
    return run_logging(parsed_args)


if __name__ == "__main__":
    raise SystemExit(main())
