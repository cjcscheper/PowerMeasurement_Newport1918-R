#!/usr/bin/env python3
"""Robust Newport 1918-R connection helper using Newport's USB DLL API.

This script keeps the same vendor-DLL approach as ``connect.py`` but adds:
- strict 64-bit requirement checks,
- stronger DLL path validation,
- consistent cleanup,
- per-device ID query output on every run,
- clearer status and error messages.

Expected environment:
- Windows
- 64-bit OS and 64-bit Python
- Newport USB driver installed
- ``usbdll.dll`` available at ``requirements/Newport/usbdll.dll``
  (or provided via ``--dll``)
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
    """Raised when Newport USB DLL initialization or communication fails."""


DEFAULT_DLL_CANDIDATES: tuple[str, ...] = (
    "requirements/Newport/usbdll.dll",
    r"C:\Program Files\Newport\Newport USB Driver\Bin\usbdll.dll",
    r"C:\Program Files (x86)\Newport\Newport USB Driver\Bin\usbdll.dll",
)


def detect_architecture_bits() -> tuple[int, int]:
    """Detect OS and Python bitness as ``(os_bits, python_bits)``.

    Returns:
        tuple[int, int]:
            - os_bits: 32 or 64, best-effort from Windows environment
            - python_bits: 32 or 64 from interpreter size
    """

    python_bits: int = 64 if sys.maxsize > 2**32 else 32
    os_is_64bit: bool = bool(
        os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROGRAMFILES(X86)")
    )
    os_bits: int = 64 if os_is_64bit else python_bits
    return os_bits, python_bits


def enforce_windows_64bit_only() -> None:
    """Fail fast unless running on Windows with both OS and Python in 64-bit mode."""

    if sys.platform != "win32":
        raise NewportConnectionError(
            f"This script supports Windows only. Detected platform: {sys.platform}."
        )

    operating_system_bits, python_interpreter_bits = detect_architecture_bits()
    if operating_system_bits != 64 or python_interpreter_bits != 64:
        raise NewportConnectionError(
            "64-bit only requirement not met. "
            f"Detected OS={operating_system_bits}-bit, Python={python_interpreter_bits}-bit. "
            "Use a 64-bit Windows installation and a 64-bit Python interpreter."
        )


def parse_product_id(value: str) -> int:
    """Parse USB product ID from decimal or hexadecimal text."""

    return int(value, 0)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser for this script."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Connect to Newport 1918-R via usbdll.dll, print device count, and run ID query "
            "for each open device."
        )
    )
    parser.add_argument(
        "--dll",
        default=None,
        help=(
            "Path to Newport usbdll.dll. If omitted, script tries requirements/Newport/usbdll.dll "
            "and common driver install paths."
        ),
    )
    parser.add_argument(
        "--product-id",
        type=parse_product_id,
        default=0xCEC7,
        help="USB product ID in decimal or hex (example: 0xCEC7).",
    )
    parser.add_argument(
        "--idn-query",
        default="*IDN?",
        help="ASCII identification query command (default: *IDN?).",
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=None,
        help=(
            "Optional single device ID to query. If omitted, the script queries all device IDs "
            "from 0 to device_count-1."
        ),
    )
    parser.add_argument(
        "--timeout-buffer-bytes",
        type=int,
        default=1024,
        help="Read buffer size used for responses (bytes).",
    )
    return parser


def resolve_dll_candidates(user_supplied_path: str | None) -> list[Path]:
    """Resolve and validate candidate DLL paths.

    Args:
        user_supplied_path: Explicit ``--dll`` path if provided by the user.

    Returns:
        list[Path]: Existing candidate paths in priority order.

    Raises:
        NewportConnectionError: If no candidate file exists.
    """

    candidate_strings: Iterable[str] = (
        (user_supplied_path,) if user_supplied_path else DEFAULT_DLL_CANDIDATES
    )

    existing_candidates: list[Path] = []
    for candidate_string in candidate_strings:
        candidate_path: Path = Path(candidate_string).expanduser().resolve()
        if candidate_path.exists() and candidate_path.is_file():
            existing_candidates.append(candidate_path)

    if not existing_candidates:
        raise NewportConnectionError(
            "Could not find Newport usbdll.dll. Expected at requirements/Newport/usbdll.dll "
            "or pass --dll with an absolute path."
        )

    return existing_candidates


def load_newport_library(dll_candidates: list[Path]) -> tuple[ctypes.WinDLL, Path]:
    """Load Newport DLL from a list of candidates and return ``(library, dll_path)``."""

    load_failure_messages: list[str] = []

    for dll_path in dll_candidates:
        try:
            loaded_library: ctypes.WinDLL = ctypes.WinDLL(str(dll_path))
            return loaded_library, dll_path
        except OSError as load_error:
            if getattr(load_error, "winerror", None) == 193:
                load_failure_messages.append(
                    f"{dll_path} -> WinError 193 (DLL and Python bitness mismatch)"
                )
            else:
                load_failure_messages.append(f"{dll_path} -> {load_error}")

    operating_system_bits, python_interpreter_bits = detect_architecture_bits()
    raise NewportConnectionError(
        "Failed to load any Newport DLL candidate. "
        f"Detected OS={operating_system_bits}-bit, Python={python_interpreter_bits}-bit. "
        f"Load errors: {'; '.join(load_failure_messages)}"
    )


def configure_newport_function_signatures(library: ctypes.WinDLL) -> None:
    """Configure ctypes function signatures for required Newport DLL calls."""

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


def open_newport_devices(library: ctypes.WinDLL, product_id: int) -> int:
    """Open devices for a given USB product ID and return count of opened devices."""

    opened_device_count: c_int = c_int(0)
    status_code: int = library.newp_usb_open_devices(
        c_int(product_id), c_bool(True), byref(opened_device_count)
    )
    if status_code != 0:
        raise NewportConnectionError(
            "newp_usb_open_devices failed with non-zero status. "
            f"status={status_code}, product_id=0x{product_id:04X}"
        )

    return int(opened_device_count.value)


def query_device_ascii(
    library: ctypes.WinDLL,
    device_id: int,
    query_command: str,
    response_buffer_size_bytes: int,
) -> str:
    """Send one ASCII command to a specific Newport device ID and read response."""

    ascii_payload_bytes: bytes = (query_command + "\r\n").encode("ascii", errors="ignore")
    write_buffer = create_string_buffer(ascii_payload_bytes)

    send_status_code: int = library.newp_usb_send_ascii(
        c_long(device_id), write_buffer, c_ulong(len(ascii_payload_bytes))
    )
    if send_status_code != 0:
        raise NewportConnectionError(
            f"newp_usb_send_ascii failed for device_id={device_id}, status={send_status_code}."
        )

    read_buffer = create_string_buffer(response_buffer_size_bytes)
    requested_read_length = c_ulong(response_buffer_size_bytes)
    bytes_read = c_ulong(0)

    receive_status_code: int = library.newp_usb_get_ascii(
        c_long(device_id), read_buffer, requested_read_length, byref(bytes_read)
    )
    if receive_status_code != 0:
        raise NewportConnectionError(
            f"newp_usb_get_ascii failed for device_id={device_id}, status={receive_status_code}."
        )

    response_text: str = read_buffer.raw[: bytes_read.value].decode(errors="ignore").strip()
    return response_text


def close_newport_session_safely(library: ctypes.WinDLL | None) -> None:
    """Attempt to close Newport session; never raise from cleanup."""

    if library is None:
        return

    try:
        library.newp_usb_uninit_system()
    except Exception:
        # Cleanup must not hide earlier, more meaningful errors.
        pass


def build_device_id_list(user_selected_device_id: int | None, opened_device_count: int) -> list[int]:
    """Construct the device IDs that should be queried during this run."""

    if user_selected_device_id is not None:
        return [user_selected_device_id]

    if opened_device_count <= 0:
        return []

    return list(range(opened_device_count))


def main() -> int:
    """Script entry point."""

    parsed_arguments = build_parser().parse_args()
    loaded_library: ctypes.WinDLL | None = None

    try:
        enforce_windows_64bit_only()
        operating_system_bits, python_interpreter_bits = detect_architecture_bits()
        print(
            f"Architecture check passed: OS={operating_system_bits}-bit, "
            f"Python={python_interpreter_bits}-bit"
        )

        dll_candidates = resolve_dll_candidates(parsed_arguments.dll)
        loaded_library, loaded_dll_path = load_newport_library(dll_candidates)
        print(f"Loaded Newport DLL: {loaded_dll_path}")

        configure_newport_function_signatures(loaded_library)

        opened_device_count: int = open_newport_devices(
            loaded_library, parsed_arguments.product_id
        )
        print(f"Open/connected Newport devices: {opened_device_count}")

        candidate_device_ids: list[int] = build_device_id_list(
            parsed_arguments.device_id, opened_device_count
        )

        if not candidate_device_ids:
            print("No devices available to query.")
        else:
            print(
                f"Running ID query '{parsed_arguments.idn_query}' for device IDs: "
                f"{candidate_device_ids}"
            )
            for candidate_device_id in candidate_device_ids:
                try:
                    idn_response_text: str = query_device_ascii(
                        loaded_library,
                        device_id=candidate_device_id,
                        query_command=parsed_arguments.idn_query,
                        response_buffer_size_bytes=parsed_arguments.timeout_buffer_bytes,
                    )
                    printable_response: str = idn_response_text or "<empty response>"
                    print(
                        f"ID query response (device_id={candidate_device_id}): "
                        f"{printable_response}"
                    )
                except NewportConnectionError as query_error:
                    print(
                        f"ID query failed (device_id={candidate_device_id}): {query_error}",
                        file=sys.stderr,
                    )

        return 0

    except NewportConnectionError as connection_error:
        print(f"ERROR: {connection_error}", file=sys.stderr)
        return 1
    finally:
        close_newport_session_safely(loaded_library)


if __name__ == "__main__":
    raise SystemExit(main())
