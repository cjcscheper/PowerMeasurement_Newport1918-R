# Newport 1918-R Power Measurement Utilities

This branch is focused on the Python migration workflow for Newport 1918-R measurements.

## Repository layout
- `connect_and_log.py`: Python utility to connect through VISA and log power readings over time.
- `requirements.txt`: Python dependency list.
- `drivers/`: Architecture-specific Newport USB driver distributions (`Win32`, `x64`, `x86Onx64`).
- `Archive_for_ChatGPT/`: Archived LabVIEW assets kept for reference/comparison without cluttering the top-level workflow.

## Python starter
A minimal script is included:

- `connect_and_log.py`: Connects through VISA, optionally probes identity, then logs:
  - elapsed time in seconds (high precision via `perf_counter_ns` + `Decimal`)
  - power reading (parsed as `Decimal` when possible)
  - raw response string
  - UTC timestamp

### Install
Windows (PowerShell):
```powershell
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
  --output logs/power_log.csv \
  --sample-interval 0.1 \
  --max-samples 100
```

### Notes for Newport 1918-R migration
- The default power query in the script is `MEAS:POW?` as a placeholder.
- If your old LabVIEW VIs used a different command path (or DLL call), set `--power-query` accordingly.
- If `*IDN?` is unsupported on your firmware/transport, set `--idn-query` to the appropriate command or ignore the warning.
