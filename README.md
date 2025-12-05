# Newport 1918-R Power Measurement Utilities

This repository packages the LabVIEW utilities and drivers used for Newport 1918-R power meter measurements. It keeps the instrument VIs and supporting binaries together so you can run the provided LabVIEW projects without hunting for dependencies.

## Repository layout
- `Power-DAQ-Stats.lvproj` and `Sample Power-DAQ-Stats.vi`: LabVIEW project and example VI for acquiring and logging power statistics.
- `make_powerlog.vi`: Utility VI that starts a logging session, creates a timestamped file when measurement begins, and records elapsed time and measured power for each sample.
- `Command VIs/`: Individual command VIs that wrap common instrument actions (reading power, configuring filters, setting ranges, etc.).
- `PowerMeterLib.dll`, `PowerMeterCommands.dll`, `UsbDllWrap.dll`: Supporting DLLs needed by the LabVIEW VIs.
- `drivers/`: Architecture-specific driver distributions organized by platform (`Win32`, `x64`, `x86Onx64`).
- `Setup.exe`: Windows installer provided by Newport.
- `Readme.pdf`, `Newport.ico`, `Autorun.inf`: Original vendor documentation and assets kept for reference.

## Getting started
1. Install the Newport instrument drivers for your platform from the `drivers/` directory (pick `Win32`, `x64`, or `x86Onx64`).
2. Run `Setup.exe` if you prefer the vendor installer to place dependencies automatically.
3. Open `Power-DAQ-Stats.lvproj` in LabVIEW to explore the included example (`Sample Power-DAQ-Stats.vi`) and the command VIs.

## Notes
- File contents are left unchanged from the vendor distribution; only the repository layout has been organized.
- Keep the DLLs alongside the VIs or in your LabVIEW search path to avoid missing dependency prompts.
