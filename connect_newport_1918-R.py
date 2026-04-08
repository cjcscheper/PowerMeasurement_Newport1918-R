#!/usr/bin/env python3
"""Newport 1918-R connection helper (USB DLL mode, ID query only).

Goal of this script:
1) Open Newport USB devices through Newport's vendor DLL.
2) Print how many devices were opened.
3) Run and print an ID query (default: ``*IDN?``).

Design notes:
- This script intentionally focuses on *essentials* only.
- No wavelength logic is included.
- Runtime checks are lightweight and practical:
  - hard fail on non-Windows,
  - architecture is reported for troubleshooting,
  - no strict 64-bit enforcement function.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
from ctypes import byref, c_bool, c_int, c_long, c_ulong, create_string_buffer
from pathlib import Path
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
    """Create and configure the command-line argument parser.

    The parser is intentionally small and focused on the essentials:
    - choose DLL path,
    - choose product ID,
    - choose optional explicit device ID,
    - choose ID query string,
    - choose response buffer size.

    Returns:
        argparse.ArgumentParser: Configured parser.
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
    return parser


def resolve_dll_candidates(user_supplied_path: str | None) -> list[Path]:
    """Resolve candidate DLL paths and return those that exist.

    Resolution strategy:
    1) If ``--dll`` is given, only that path is considered.
    2) Otherwise, common Newport install locations are tried.

    Args:
        user_supplied_path (str | None): Value of ``--dll``.

    Returns:
        list[Path]: Existing candidate paths in priority order.

    Raises:
        NewportConnectionError: If no DLL candidates exist on disk.
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
    """Open Newport devices for a USB product ID and return open count.

    Args:
        library (ctypes.WinDLL): Loaded Newport DLL handle.
        product_id (int): USB product ID.

    Returns:
        int: Number of opened/connected devices reported by DLL.

    Raises:
        NewportConnectionError: On non-zero driver status.
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


def try_get_instrument_device_id(library: ctypes.WinDLL) -> int | None:
    """Try to discover Newport's instrument device ID using ``GetInstrumentList``.

    This function is intentionally non-fatal:
    - If the function is unavailable in the DLL, it returns ``None``.
    - If the call fails, it returns ``None``.
    - If no instruments are listed, it returns ``None``.

    In all ``None`` cases, a detailed message is printed to stderr so the user
    understands *why* discovery did not produce a device ID.

    Args:
        library (ctypes.WinDLL): Loaded Newport DLL handle.

    Returns:
        int | None: Discovered device ID, or None.
    """

    if not hasattr(library, "GetInstrumentList"):
        print(
            "GetInstrumentList is not exported by this usbdll.dll; "
            "cannot auto-discover Newport device_id.",
            file=sys.stderr,
        )
        return None

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
            f"({get_list_status}); cannot auto-discover device_id.",
            file=sys.stderr,
        )
        return None

    if instrument_count.value <= 0:
        print(
            "GetInstrumentList succeeded but reported zero instruments; "
            "cannot auto-discover device_id.",
            file=sys.stderr,
        )
        return None

    return int(instrument_device_id.value)


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
    """Send one ASCII command and return stripped ASCII response text.

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
    """Attempt to close/uninitialize Newport USB system without raising errors.

    This helper is used in ``finally`` so cleanup always runs.
    Cleanup errors are intentionally swallowed to avoid masking the original
    operational error that triggered shutdown.
    """

    if library is None:
        return

    try:
        library.newp_usb_uninit_system()
    except Exception:
        pass


def main() -> int:
    """Run connect + ID query workflow and return process exit code.

    High-level steps:
    1) Parse CLI input.
    2) Check basic runtime platform and print architecture info.
    3) Resolve/load DLL and configure signatures.
    4) Open devices and print count.
    5) Determine device ID(s) and run ID query.
    6) Exit with 0 on success, 1 on connection/command error.
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

        discovered_device_id = try_get_instrument_device_id(loaded_library)
        device_ids_to_query = choose_device_ids_to_query(
            explicit_device_id=args.device_id,
            discovered_device_id=discovered_device_id,
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
