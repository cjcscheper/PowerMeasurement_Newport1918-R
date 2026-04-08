# Newport 1918-R Power Measurement Utilities

This branch is focused on the Python migration workflow for Newport 1918-R measurements.

## Repository layout
- `connect_and_log.py`: Python utility to connect through VISA and log power readings over time.
- `simulate_and_profile.py`: Offline simulator + per-function timing profiler for bottleneck discovery.
- `requirements.txt`: Python dependency list.
- `drivers/`: Architecture-specific Newport USB driver distributions (`Win32`, `x64`, `x86Onx64`).
- `Archive_for_ChatGPT/`: Archived LabVIEW assets kept for reference/comparison without cluttering the top-level workflow.
- `COMMAND_MAPPING.md`: Draft migration mapping from archived LabVIEW VIs to Python/SCPI concepts.

## Python starter
A minimal script is included:

- `connect_and_log.py`: Connects through VISA, optionally probes identity, then logs:
  - elapsed time in seconds (high precision via `perf_counter_ns` + `Decimal`)
  - power reading (parsed as `Decimal` when possible)
  - raw response string
  - UTC timestamp

### Install
Windows (PowerShell):
```
python -m venv .venv
# Windows (Git Bash):
source .venv/Scripts/activate
# macOS/Linux (if needed):
# source .venv/bin/activate
python -m pip install -r requirements.txt
```

> Run `python -m venv .venv` once when setting up. If the virtual environment is already active, skip recreating it.

### Discover instrument resource
```bash
python connect_and_log.py --list
```

### Log 100 samples at 10 Hz
```bash
python connect_and_log.py \
  --resource "USB0::...::INSTR" \
  --sample-interval 0.1 \
  --max-samples 100
```

### Quick connection check (no long logging run)
```bash
python connect_and_log.py \
  --resource "USB0::...::INSTR" \
  --check
```
This opens the device, runs the ID query, executes one power query, and exits.

If `--output` is omitted, the filename is auto-generated from the first measurement timestamp:
`YYYY-MM-DD-hh-mm-ss_Newport1918R.csv`.


### LabVIEW-style USB DLL connection check (non-VISA)
```bash
python connect.py --dll "C:\Program Files\Newport\Newport USB Driver\Bin\usbdll.dll" --show-devices
python connect.py --idn-query "*IDN?" --device-id <id_from_show_devices>
```
Use this when you want to mirror the LabVIEW/vendor-driver path (`usbdll.dll`) instead of PyVISA.

> `connect.py` no longer sends `*IDN?` by default. This avoids driver crashes when the wrong device ID/address is used.

> If you hit `WinError 193`, your Python bitness and DLL bitness do not match.
> Even on a 64-bit Windows OS, a 32-bit Python install must use a 32-bit DLL.
> Try 64-bit Python with `C:\Program Files\...\usbdll.dll`, or 32-bit Python with `C:\Program Files (x86)\...\usbdll.dll`.

### Simulate + profile without hardware
```bash
python simulate_and_profile.py \
  --max-samples 200 \
  --sample-interval 0.02 \
  --output-dir logs
```

### Notes for Newport 1918-R migration
- The default power query in the script is `MEAS:POW?` as a placeholder.
- If your old LabVIEW VIs used a different command path (or DLL call), set `--power-query` accordingly.
- If `*IDN?` is unsupported on your firmware/transport, set `--idn-query` to the appropriate command or ignore the warning.
