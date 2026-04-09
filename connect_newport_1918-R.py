#!/usr/bin/env python3
"""Newport 1918-R connection helper (USB DLL mode, ID query only).

This script is intentionally focused on *simple, practical diagnostics* for
teams migrating from LabVIEW or vendor examples to Python.

What it does, step by step:
1) Loads Newport's USB DLL (``usbdll.dll``).
2) Opens devices for a configurable USB product ID.
3) Automatically prints detected device metadata (ID/model/serial/count) when
   ``GetInstrumentList`` is available.
4) Sends an ASCII identity command (default ``*IDN?``) and prints the response.

What it does *not* do:
- Continuous logging.
- Wavelength/measurement configuration.
- Data export.

This limited scope is deliberate: if connection basics are clear and stable,
higher-level measurement workflows are much easier to debug later.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
from ctypes import byref, c_bool, c_int, c_long, c_ulong, create_string_buffer
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable


class NewportConnectionError(RuntimeError):
    """Raised when Newport DLL setup or command execution fails.

    This exception type is used to make all operational failures explicit and
    consistent. Instead of returning ambiguous ``None`` values during critical
    operations (DLL load, open devices, query), the script raises this error
    with a direct message.

    Why this helps:
    - Main flow stays simple and readable.
    - Error handling is centralized in ``main()``.
    - Users get one clear failure reason per run.
    """




@dataclass(frozen=True)
class InstrumentInfo:
    """Human-readable snapshot of one Newport instrument entry from the driver list.

    The Newport DLL function ``GetInstrumentList`` provides four integer outputs:
    the Newport device ID, model number, serial number, and number of instruments
    reported by the driver call. Packaging those values into this small dataclass
    makes the code easier to follow, especially for teammates who are less familiar
    with pointer-based C APIs and ctypes output parameters.

    Attributes:
        device_id: Address/identifier used by ASCII command functions.
        model: Numeric model code (for example, 1918 for a 1918-R meter).
        serial: Instrument serial number as returned by the DLL.
        count: Number of instruments reported by the DLL call.
    """

    device_id: int
    model: int
    serial: int
    count: int

DEFAULT_DLL_CANDIDATES: tuple[str, ...] = (
    r"C:\Program Files\Newport\Newport USB Driver\Bin\usbdll.dll",
    r"C:\Program Files (x86)\Newport\Newport USB Driver\Bin\usbdll.dll",
)


def detect_architecture_bits() -> tuple[int, int]:
    """Detect operating system and Python interpreter bitness.

    Returns:
        tuple[int, int]:
            ``(os_bits, python_bits)`` where each value is expected to be
            32 or 64.

    How detection works:
        - ``python_bits`` is inferred from ``sys.maxsize``.
        - ``os_bits`` is inferred from Windows environment variables that are
          typically present on 64-bit systems.

    Important detail:
        On a 64-bit Windows OS running 32-bit Python, this function should
        return ``(64, 32)``. This distinction is useful when diagnosing
        DLL load errors such as WinError 193.
    """

    python_bits: int = 64 if sys.maxsize > 2**32 else 32
    operating_system_looks_64bit: bool = bool(
        os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROGRAMFILES(X86)")
    )
    os_bits: int = 64 if operating_system_looks_64bit else python_bits
    return os_bits, python_bits


def parse_product_id(value: str) -> int:
    """Parse a product ID from CLI text into an integer.

    Supports:
    - decimal input (example: ``52935``)
    - hexadecimal input (example: ``0xCEC7``)

    Args:
        value (str): Raw CLI value.

    Returns:
        int: Parsed product ID.
    """

    return int(value, 0)


def build_parser() -> argparse.ArgumentParser:
    """Create and configure all command-line options for this script.

    This function exists so a non-coder can quickly scan *one place* and
    understand what can be configured without reading low-level USB details.

    Think of the parser like a "form" for terminal input:
    - each ``add_argument`` call defines one field in that form,
    - type conversions happen automatically (for example, text -> int),
    - help strings are surfaced when running ``python script.py --help``.

    Returns:
        argparse.ArgumentParser: Ready-to-use parser object.
    """

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Connect to Newport USB device(s) and print ID query response(s)."
    )
    parser.add_argument(
        "--dll",
        default=None,
        help="Optional explicit path to usbdll.dll.",
    )
    parser.add_argument(
        "--product-id",
        type=parse_product_id,
        default=0xCEC7,
        help="USB product ID (decimal or hex like 0xCEC7).",
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=None,
        help="Optional explicit Newport device ID for ID query.",
    )
    parser.add_argument(
        "--idn-query",
        default="*IDN?",
        help="ASCII ID query command.",
    )
    parser.add_argument(
        "--response-buffer-bytes",
        type=int,
        default=1024,
        help="Read buffer size for ASCII response.",
    )
    parser.add_argument(
        "--show-device",
        action="store_true",
        default=True,
        help=(
            "Print GetInstrumentList details automatically (device_id/model/serial/count). "
            "Enabled by default to make troubleshooting easier for non-coders."
        ),
    )
    return parser


def resolve_dll_candidates(user_supplied_path: str | None) -> list[Path]:
    """Build a trusted list of DLL files that we can actually load.

    Why this matters for non-coders:
    - Windows hardware utilities often fail with vague errors when a path is
      wrong. This function checks paths up front and fails with one clear
      message if no usable DLL exists.
    - It also keeps precedence simple: an explicit ``--dll`` path always wins.

    Resolution strategy:
    1) If ``--dll`` is provided, test only that path.
    2) If ``--dll`` is not provided, test built-in default install paths.
    3) Keep only paths that exist and are files.

    Args:
        user_supplied_path (str | None): Value of ``--dll`` from CLI input.

    Returns:
        list[Path]: Existing DLL files in priority order.

    Raises:
        NewportConnectionError: If zero candidate DLLs are found.
    """

    raw_candidates: Iterable[str] = (
        (user_supplied_path,) if user_supplied_path else DEFAULT_DLL_CANDIDATES
    )

    existing_candidates: list[Path] = []
    for raw_candidate in raw_candidates:
        candidate_path = Path(raw_candidate).expanduser().resolve()
        if candidate_path.exists() and candidate_path.is_file():
            existing_candidates.append(candidate_path)

    if not existing_candidates:
        raise NewportConnectionError(
            "Could not find usbdll.dll. Install Newport USB drivers or pass --dll <path>."
        )

    return existing_candidates


def load_newport_library(dll_candidates: list[Path]) -> tuple[ctypes.WinDLL, Path]:
    """Try loading the Newport DLL from candidates and return the loaded library.

    Args:
        dll_candidates (list[Path]): Existing candidate DLL files.

    Returns:
        tuple[ctypes.WinDLL, Path]: ``(library, loaded_path)``.

    Raises:
        NewportConnectionError: If all candidates fail to load.

    Notes:
        - WinError 193 usually indicates architecture mismatch.
        - The full load error list is included in the raised message.
    """

    load_errors: list[str] = []

    for dll_path in dll_candidates:
        try:
            return ctypes.WinDLL(str(dll_path)), dll_path
        except OSError as load_error:
            if getattr(load_error, "winerror", None) == 193:
                load_errors.append(f"{dll_path} -> WinError 193 (bitness mismatch)")
            else:
                load_errors.append(f"{dll_path} -> {load_error}")

    os_bits, python_bits = detect_architecture_bits()
    raise NewportConnectionError(
        "Failed to load any Newport DLL candidate. "
        f"OS={os_bits}-bit, Python={python_bits}-bit. "
        f"Errors: {'; '.join(load_errors)}"
    )


def configure_newport_function_signatures(library: ctypes.WinDLL) -> None:
    """Declare ctypes signatures for the Newport DLL functions we use.

    Why this is important:
        Correct signatures prevent ctypes from passing wrong value types or
        wrong pointer types, which can lead to incorrect behavior or crashes.

    Functions configured:
        - ``newp_usb_open_devices``
        - ``newp_usb_uninit_system``
        - ``newp_usb_send_ascii``
        - ``newp_usb_get_ascii``
        - optional ``GetInstrumentList`` (if exported by this DLL build)
    """

    library.newp_usb_open_devices.argtypes = [c_int, c_bool, ctypes.POINTER(c_int)]
    library.newp_usb_open_devices.restype = c_long

    library.newp_usb_uninit_system.argtypes = []
    library.newp_usb_uninit_system.restype = None

    library.newp_usb_send_ascii.argtypes = [c_long, ctypes.c_char_p, c_ulong]
    library.newp_usb_send_ascii.restype = c_long

    library.newp_usb_get_ascii.argtypes = [
        c_long,
        ctypes.c_char_p,
        c_ulong,
        ctypes.POINTER(c_ulong),
    ]
    library.newp_usb_get_ascii.restype = c_long

    if hasattr(library, "GetInstrumentList"):
        library.GetInstrumentList.argtypes = [
            ctypes.POINTER(c_int),
            ctypes.POINTER(c_int),
            ctypes.POINTER(c_int),
            ctypes.POINTER(c_int),
        ]
        library.GetInstrumentList.restype = c_long


def open_newport_devices(library: ctypes.WinDLL, product_id: int) -> int:
    """Ask the Newport driver to open devices and report how many it sees.

    Args:
        library (ctypes.WinDLL): Loaded Newport DLL handle.
        product_id (int): USB product ID.

    Returns:
        int: Number of opened/connected devices reported by DLL.

    Raises:
        NewportConnectionError:
            Raised when the driver returns a non-zero status code, which means
            open failed (for example wrong product ID or driver/device issue).
    """

    opened_device_count = c_int(0)
    open_status = library.newp_usb_open_devices(
        c_int(product_id), c_bool(True), byref(opened_device_count)
    )

    if open_status != 0:
        raise NewportConnectionError(
            f"newp_usb_open_devices failed with status={open_status} for product_id=0x{product_id:04X}."
        )

    return int(opened_device_count.value)


def try_get_instrument_info(library: ctypes.WinDLL) -> InstrumentInfo | None:
    """Attempt to read and return instrument details via ``GetInstrumentList``.

    Why this helper is important for non-coders:
    - It translates low-level driver outputs into clear labels.
    - It keeps "best effort" behavior: discovery problems are *reported* but do
      not crash the whole script.
    - It enables an easy-to-read print line in ``main()`` like:
      ``GetInstrumentList -> device_id=2, model=1918, serial=13487, count=1``

    Behavior summary:
    1) If the DLL does not expose ``GetInstrumentList``, return ``None``.
    2) If the call returns non-zero status, return ``None``.
    3) If count is zero, return ``None``.
    4) Otherwise return an ``InstrumentInfo`` instance.

    Args:
        library (ctypes.WinDLL): Loaded Newport DLL handle.

    Returns:
        InstrumentInfo | None: Parsed instrument info when available.
    """

    if not hasattr(library, "GetInstrumentList"):
        print(
            "GetInstrumentList is not exported by this usbdll.dll; "
            "cannot auto-discover Newport device details.",
            file=sys.stderr,
        )
        return None

    # Each c_int acts like a mutable "box" that the DLL function fills in.
    instrument_device_id = c_int(0)
    instrument_model_number = c_int(0)
    instrument_serial_number = c_int(0)
    instrument_count = c_int(0)

    get_list_status = library.GetInstrumentList(
        byref(instrument_device_id),
        byref(instrument_model_number),
        byref(instrument_serial_number),
        byref(instrument_count),
    )

    if get_list_status != 0:
        print(
            "GetInstrumentList returned non-zero status "
            f"({get_list_status}); cannot auto-discover device details.",
            file=sys.stderr,
        )
        return None

    if instrument_count.value <= 0:
        print(
            "GetInstrumentList succeeded but reported zero instruments; "
            "cannot auto-discover device details.",
            file=sys.stderr,
        )
        return None

    return InstrumentInfo(
        device_id=int(instrument_device_id.value),
        model=int(instrument_model_number.value),
        serial=int(instrument_serial_number.value),
        count=int(instrument_count.value),
    )


def choose_device_ids_to_query(
    explicit_device_id: int | None,
    discovered_device_id: int | None,
    opened_device_count: int,
) -> list[int]:
    """Choose which device IDs should receive the ID query.

    Priority order:
        1) Explicit ``--device-id`` from user.
        2) Device ID discovered from ``GetInstrumentList``.
        3) Fallback probe across ``0..opened_device_count-1``.

    Args:
        explicit_device_id (int | None): User-provided device ID.
        discovered_device_id (int | None): ID from discovery helper.
        opened_device_count (int): Count from ``newp_usb_open_devices``.

    Returns:
        list[int]: Ordered list of device IDs to query.
    """

    if explicit_device_id is not None:
        return [explicit_device_id]

    if discovered_device_id is not None:
        return [discovered_device_id]

    if opened_device_count <= 0:
        return []

    return list(range(opened_device_count))


def query_device_ascii(
    library: ctypes.WinDLL,
    device_id: int,
    command_text: str,
    response_buffer_bytes: int,
) -> str:
    """Send one text command to one device and read back a text response.

    This is the key "question/answer" step with the meter:
    - we send a command like ``*IDN?``,
    - the device sends back plain text,
    - we decode the bytes to human-readable text.

    Extra notes for non-coders:
    - ``\\r\\n`` is command termination expected by many instrument protocols.
    - ``errors='ignore'`` avoids crashes if a response contains unexpected
      byte values; problematic bytes are skipped instead.
    - any non-zero status from the driver is treated as a hard error so the
      caller can print an explicit failure reason.

    Args:
        library (ctypes.WinDLL): Loaded Newport DLL handle.
        device_id (int): Newport device ID target.
        command_text (str): Command to send (for example ``*IDN?``).
        response_buffer_bytes (int): Read buffer size in bytes.

    Returns:
        str: Response text decoded with ``errors='ignore'`` and stripped.

    Raises:
        NewportConnectionError: If send/read status is non-zero.
    """

    command_payload = (command_text + "\r\n").encode("ascii", errors="ignore")
    command_buffer = create_string_buffer(command_payload)

    send_status = library.newp_usb_send_ascii(
        c_long(device_id), command_buffer, c_ulong(len(command_payload))
    )
    if send_status != 0:
        raise NewportConnectionError(
            f"newp_usb_send_ascii failed for device_id={device_id} with status={send_status}."
        )

    response_buffer = create_string_buffer(response_buffer_bytes)
    requested_length = c_ulong(response_buffer_bytes)
    received_length = c_ulong(0)

    read_status = library.newp_usb_get_ascii(
        c_long(device_id), response_buffer, requested_length, byref(received_length)
    )
    if read_status != 0:
        raise NewportConnectionError(
            f"newp_usb_get_ascii failed for device_id={device_id} with status={read_status}."
        )

    response_text = response_buffer.raw[: received_length.value].decode(errors="ignore").strip()
    return response_text


def close_newport_session_safely(library: ctypes.WinDLL | None) -> None:
    """Best-effort shutdown helper used during program exit.

    Why this helper exists:
    - We always want cleanup to run, even when earlier steps fail.
    - We do not want a cleanup exception to hide the *real* root-cause error.

    Behavior:
    - If no library was loaded, do nothing.
    - If shutdown fails, swallow the exception intentionally.
    """

    if library is None:
        return

    try:
        library.newp_usb_uninit_system()
    except Exception:
        pass


def main() -> int:
    """Orchestrate the full connection workflow and return shell exit code.

    High-level steps:
    1) Parse CLI input.
    2) Check basic runtime platform and print architecture info.
    3) Resolve/load DLL and configure signatures.
    4) Open devices and print count.
    5) Automatically print ``GetInstrumentList`` details (if available).
    6) Determine device ID(s) and run ID query.
    7) Exit with ``0`` on success, ``1`` on connection/command error.
    """

    args = build_parser().parse_args()
    loaded_library: ctypes.WinDLL | None = None

    try:
        if sys.platform != "win32":
            raise NewportConnectionError(
                f"This script supports Windows only. Detected platform: {sys.platform}."
            )

        os_bits, python_bits = detect_architecture_bits()
        print(f"Detected architecture: OS={os_bits}-bit, Python={python_bits}-bit")

        dll_candidates = resolve_dll_candidates(args.dll)
        loaded_library, loaded_dll_path = load_newport_library(dll_candidates)
        print(f"Loaded DLL: {loaded_dll_path}")

        configure_newport_function_signatures(loaded_library)

        opened_device_count = open_newport_devices(loaded_library, args.product_id)
        print(f"Open/connected Newport devices: {opened_device_count}")

        discovered_info = try_get_instrument_info(loaded_library)
        if args.show_device and discovered_info is not None:
            print(
                "GetInstrumentList -> "
                f"device_id={discovered_info.device_id}, "
                f"model={discovered_info.model}, "
                f"serial={discovered_info.serial}, "
                f"count={discovered_info.count}"
            )

        device_ids_to_query = choose_device_ids_to_query(
            explicit_device_id=args.device_id,
            discovered_device_id=(discovered_info.device_id if discovered_info else None),
            opened_device_count=opened_device_count,
        )

        if not device_ids_to_query:
            print("No device IDs available for ID query.")
            return 0

        print(f"Running ID query '{args.idn_query}' for device IDs: {device_ids_to_query}")
        for device_id in device_ids_to_query:
            try:
                idn_response = query_device_ascii(
                    library=loaded_library,
                    device_id=device_id,
                    command_text=args.idn_query,
                    response_buffer_bytes=args.response_buffer_bytes,
                )
                print(f"ID query response (device_id={device_id}): {idn_response or '<empty response>'}")
            except NewportConnectionError as query_error:
                print(f"ID query failed (device_id={device_id}): {query_error}", file=sys.stderr)

        return 0

    except NewportConnectionError as connection_error:
        print(f"ERROR: {connection_error}", file=sys.stderr)
        return 1
    finally:
        close_newport_session_safely(loaded_library)


if __name__ == "__main__":
    raise SystemExit(main())
