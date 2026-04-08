# Newport DLL placement

Place the Newport USB DLL here:

- `requirements/Newport/usbdll.dll`

## Notes for a new PC

In many setups, `usbdll.dll` is sufficient **only after** installing Newport USB drivers.

Depending on the Newport driver package and Windows runtime state, you may also need:

- Driver package files (already in `drivers/` in this repository)
- Microsoft Visual C++ runtime components required by the Newport DLL build

If the script reports DLL load failures even when `usbdll.dll` exists, install/reinstall Newport USB drivers and required VC++ runtimes.
