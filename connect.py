#!/usr/bin/env python3
"""Newport 1918-R connection probe via Newport USB driver DLL (non-VISA).

This is intentionally *not* PyVISA. It follows the same vendor-DLL approach used by
many LabVIEW/Newport examples, inspired by:
https://github.com/plasmon360/python_newport_1918_powermeter

Expected platform: Windows + Newport USB driver installed.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
from ctypes import byref, c_bool, c_int, c_long, c_ulong, create_string_buffer
from pathlib import Path
from typing import Iterable


DEFAULT_DLL_CANDIDATES = (
    r"C:\Program Files\Newport\Newport USB Driver\Bin\usbdll.dll",
    r"C:\Program Files (x86)\Newport\Newport USB Driver\Bin\usbdll.dll",
    "Archive_for_ChatGPT/UsbDllWrap.dll",
)



def detect_architecture() -> tuple[int, int]:
    """Return (os_bits, python_bits)."""
    python_bits = 64 if sys.maxsize > 2**32 else 32
    # On Windows, PROCESSOR_ARCHITEW6432 is set for 32-bit process on 64-bit OS.
    if os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROGRAMFILES(X86)"):
        os_bits = 64
    else:
        os_bits = python_bits
    return os_bits, python_bits


class NewportConnectionError(RuntimeError):
    """Raised when Newport DLL setup/commands fail."""


def parse_product_id(value: str) -> int:
    return int(value, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connect to Newport meter via Newport USB driver DLL (LabVIEW-style)."
    )
    parser.add_argument(
        "--dll",
        default=None,
        help="Path to usbdll.dll. If omitted, common install paths are tried.",
    )
    parser.add_argument(
        "--product-id",
        type=parse_product_id,
        default=0xCEC7,
        help="USB product ID (accepts hex like 0xCEC7 or decimal).",
    )
    parser.add_argument(
        "--idn-query",
        default="*IDN?",
        help="ASCII query to verify communication after connect.",
    )
    parser.add_argument(
        "--show-devices",
        action="store_true",
        help="Try GetInstrumentList and print the first returned values.",
    )
    return parser


def resolve_dll_candidates(user_path: str | None) -> list[Path]:
    candidates: Iterable[str] = (user_path,) if user_path else DEFAULT_DLL_CANDIDATES
    existing = [Path(candidate).expanduser().resolve() for candidate in candidates if Path(candidate).expanduser().exists()]
    if not existing:
        raise NewportConnectionError(
            "Could not find Newport USB DLL. Pass --dll or install Newport USB driver."
        )
    return existing


def load_library(candidates: list[Path]) -> tuple[ctypes.WinDLL, Path]:
    if sys.platform != "win32":
        raise NewportConnectionError(
            f"This script targets Windows Newport drivers. Current platform: {sys.platform}"
        )

    load_errors: list[str] = []
    for dll_path in candidates:
        try:
            return ctypes.WinDLL(str(dll_path)), dll_path
        except OSError as exc:
            # WinError 193 usually means 32/64-bit mismatch.
            if getattr(exc, "winerror", None) == 193:
                load_errors.append(
                    f"{dll_path} -> WinError 193 (bitness mismatch: DLL vs Python)"
                )
                continue
            load_errors.append(f"{dll_path} -> {exc}")

    os_bits, py_bits = detect_architecture()
    raise NewportConnectionError(
        "Failed to load any Newport DLL candidate. "
        f"OS={os_bits}-bit, Python={py_bits}-bit. Tried: " + "; ".join(load_errors)
    )


def configure_signatures(lib: ctypes.WinDLL) -> None:
    lib.newp_usb_open_devices.argtypes = [c_int, c_bool, ctypes.POINTER(c_int)]
    lib.newp_usb_open_devices.restype = c_long

    lib.newp_usb_uninit_system.argtypes = []
    lib.newp_usb_uninit_system.restype = None

    lib.newp_usb_send_ascii.argtypes = [c_long, ctypes.c_char_p, c_ulong]
    lib.newp_usb_send_ascii.restype = c_long

    lib.newp_usb_get_ascii.argtypes = [
        c_long,
        ctypes.c_char_p,
        c_ulong,
        ctypes.POINTER(c_ulong),
    ]
    lib.newp_usb_get_ascii.restype = c_long

    # Optional helper in some Newport builds.
    if hasattr(lib, "GetInstrumentList"):
        lib.GetInstrumentList.argtypes = [
            ctypes.POINTER(c_int),
            ctypes.POINTER(c_int),
            ctypes.POINTER(c_int),
            ctypes.POINTER(c_int),
        ]
        lib.GetInstrumentList.restype = c_long


def open_devices(lib: ctypes.WinDLL, product_id: int) -> int:
    count = c_int()
    status = lib.newp_usb_open_devices(c_int(product_id), c_bool(True), byref(count))
    if status != 0:
        raise NewportConnectionError(
            f"newp_usb_open_devices failed with status={status} for product_id=0x{product_id:04X}"
        )
    return count.value


def get_instrument_list(lib: ctypes.WinDLL) -> tuple[int, int, int, int] | None:
    if not hasattr(lib, "GetInstrumentList"):
        return None

    device_ids = c_int()
    model_numbers = c_int()
    serial_numbers = c_int()
    array_size = c_int()

    status = lib.GetInstrumentList(
        byref(device_ids),
        byref(model_numbers),
        byref(serial_numbers),
        byref(array_size),
    )
    if status != 0:
        raise NewportConnectionError(f"GetInstrumentList failed with status={status}")

    return (device_ids.value, model_numbers.value, serial_numbers.value, array_size.value)


def query_ascii(lib: ctypes.WinDLL, device_id: int, command: str) -> str:
    payload = (command + "\r\n").encode("ascii", errors="ignore")
    write_buf = ctypes.create_string_buffer(payload)
    status = lib.newp_usb_send_ascii(c_long(device_id), write_buf, c_ulong(len(payload)))
    if status != 0:
        raise NewportConnectionError(f"newp_usb_send_ascii failed with status={status}")

    read_buf = create_string_buffer(1024)
    read_len = c_ulong(1024)
    n_read = c_ulong(0)
    status = lib.newp_usb_get_ascii(c_long(device_id), read_buf, read_len, byref(n_read))
    if status != 0:
        raise NewportConnectionError(f"newp_usb_get_ascii failed with status={status}")

    return read_buf.raw[: n_read.value].decode(errors="ignore").strip()


def close_devices(lib: ctypes.WinDLL) -> None:
    lib.newp_usb_uninit_system()


def main() -> int:
    args = build_parser().parse_args()
    try:
        os_bits, py_bits = detect_architecture()
        print(f"System architecture: OS={os_bits}-bit, Python={py_bits}-bit")

        dll_candidates = resolve_dll_candidates(args.dll)
        lib, dll_path = load_library(dll_candidates)
        print(f"Using DLL: {dll_path}")
        configure_signatures(lib)

        device_count = open_devices(lib, args.product_id)
        print(f"Connected/opened devices: {device_count}")

        if args.show_devices:
            info = get_instrument_list(lib)
            if info is None:
                print("GetInstrumentList not available in this DLL build.")
            else:
                device_id, model_num, serial_num, array_size = info
                print(
                    "GetInstrumentList -> "
                    f"device_id={device_id}, model={model_num}, serial={serial_num}, count={array_size}"
                )

        if device_count > 0:
            # Default to first USB address/device id used by Newport API.
            response = query_ascii(lib, device_id=0, command=args.idn_query)
            print(f"{args.idn_query} -> {response}")

        close_devices(lib)
        print("Closed Newport USB session.")
        return 0

    except NewportConnectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Hint: if you see WinError 193, use a DLL matching your Python architecture (32-bit vs 64-bit).", file=sys.stderr)
        print("On a 64-bit OS, 32-bit Python still requires a 32-bit DLL.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
