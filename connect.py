#!/usr/bin/env python3
"""Try Newport 1918-R connection through the same USB DLL path used by LabVIEW.

The archived LabVIEW project uses command VIs backed by `UsbDllWrap.dll` / `PowerMeterLib.dll`
rather than VISA nodes. This script tries that same vendor-driver route from Python
using pythonnet reflection so we can verify device discovery/connection behavior.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Attempt Newport USB DLL connection (LabVIEW-style, non-VISA)."
    )
    parser.add_argument(
        "--dll",
        default="Archive_for_ChatGPT/UsbDllWrap.dll",
        help="Path to UsbDllWrap.dll from Newport/LabVIEW archive.",
    )
    parser.add_argument(
        "--class-name",
        default="Newport.USBComm",
        help="Fully qualified .NET class name to instantiate.",
    )
    parser.add_argument(
        "--list-methods",
        action="store_true",
        help="Only print discovered methods and exit.",
    )
    return parser


def _import_net_modules() -> tuple[Any, Any]:
    try:
        import clr  # type: ignore
        from System import Activator  # type: ignore
        from System.Reflection import BindingFlags  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "pythonnet is required. Install with: pip install pythonnet"
        ) from exc
    return (clr, (Activator, BindingFlags))


def _method_names(dotnet_type: Any, binding_flags: Any) -> list[str]:
    methods = dotnet_type.GetMethods(binding_flags.Public | binding_flags.Instance)
    names = sorted({m.Name for m in methods})
    return names


def _invoke_noarg_if_exists(instance: Any, method_name: str) -> Any:
    method = instance.GetType().GetMethod(method_name)
    if method is None:
        return None
    return method.Invoke(instance, None)


def _to_py_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [item for item in value]  # IEnumerable / arrays
    except TypeError:
        return [value]


def _print_methods(names: Iterable[str]) -> None:
    print("Discovered public instance methods:")
    for name in names:
        print(f"  - {name}")


def main() -> int:
    args = build_parser().parse_args()

    dll_path = Path(args.dll).expanduser().resolve()
    if not dll_path.exists():
        print(f"ERROR: DLL not found: {dll_path}", file=sys.stderr)
        return 2

    try:
        clr, (activator, binding_flags) = _import_net_modules()
        clr.AddReference(str(dll_path))

        from System import Type  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Could not load .NET runtime/assembly: {exc}", file=sys.stderr)
        return 3

    dotnet_type = Type.GetType(args.class_name)
    if dotnet_type is None:
        print(
            f"ERROR: Class '{args.class_name}' not found after loading {dll_path.name}",
            file=sys.stderr,
        )
        return 4

    instance = activator.CreateInstance(dotnet_type)
    method_names = _method_names(dotnet_type, binding_flags)
    _print_methods(method_names)

    if args.list_methods:
        return 0

    # Match likely LabVIEW workflow naming found in the archived binaries:
    # Init -> Get keys -> Open -> Close.
    init_result = _invoke_noarg_if_exists(instance, "EventInit")
    if init_result is not None:
        print(f"EventInit() -> {init_result}")

    keys_result = _invoke_noarg_if_exists(instance, "GetDeviceKeys")
    keys = _to_py_list(keys_result)
    print(f"GetDeviceKeys() returned {len(keys)} item(s): {keys}")

    if keys:
        first_key = str(keys[0])
        print(f"Using first key: {first_key}")

        open_method = instance.GetType().GetMethod("OpenDevices")
        close_method = instance.GetType().GetMethod("CloseDevices")

        if open_method is None:
            print("OpenDevices(...) not found; cannot attempt device open.")
            return 5

        open_params = open_method.GetParameters()
        if len(open_params) == 1:
            open_result = open_method.Invoke(instance, [first_key])
        elif len(open_params) == 0:
            open_result = open_method.Invoke(instance, None)
        else:
            print(
                "OpenDevices has unsupported signature for auto-invoke; "
                f"parameter count = {len(open_params)}"
            )
            return 6

        print(f"OpenDevices(...) -> {open_result}")

        if close_method is not None:
            close_result = close_method.Invoke(instance, None)
            print(f"CloseDevices() -> {close_result}")

        return 0

    print("No device keys found. Check Newport USB driver installation and meter connection.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
