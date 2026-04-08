# Newport 1918-R Command Mapping (LabVIEW Archive → Python/SCPI)

This document maps archived LabVIEW command VI names in `Archive_for_ChatGPT/Command VIs/` to likely SCPI-style commands or Python workflow responsibilities.

> Status legend:
> - **Mapped**: likely direct command mapping.
> - **Verify on hardware**: probable mapping, requires meter validation.
> - **Workflow/API**: VI is orchestration/helper and may not be a direct SCPI command.

| Archived VI | Likely Python / SCPI mapping | Status | Notes |
|---|---|---|---|
| `CmdGetPower.vi` | `MEAS:POW?` (or model-specific equivalent) | Verify on hardware | Default in current Python logger. |
| `GetPowerReadings.vi` | repeated `read_sample(...)` loop | Mapped | Python loop writes each sample to CSV. |
| `CmdGetWavelength.vi` | `SENS:WAV?` | Verify on hardware | Common optical power meter convention. |
| `CmdSetWavelength.vi` | `SENS:WAV <value>` | Verify on hardware | Set channel wavelength calibration. |
| `CmdGetRange.vi` | `SENS:POW:RANG?` | Verify on hardware | Range query may vary by firmware. |
| `CmdSetRange.vi` | `SENS:POW:RANG <value>` | Verify on hardware | |
| `CmdGetAutoRangeEnable.vi` | `SENS:POW:RANG:AUTO?` | Verify on hardware | |
| `CmdSetAutoRangeEnable.vi` | `SENS:POW:RANG:AUTO <0/1>` | Verify on hardware | |
| `CmdGetUnits.vi` | `UNIT:POW?` | Verify on hardware | |
| `CmdSetUnits.vi` | `UNIT:POW <unit>` | Verify on hardware | |
| `CmdGetFilterType.vi` | model-specific filter query | Verify on hardware | Might not be standard SCPI. |
| `CmdSetFilterType.vi` | model-specific filter set | Verify on hardware | |
| `CmdGetAnalogFilter.vi` | analog filter query | Verify on hardware | |
| `CmdSetAnalogFilter.vi` | analog filter set | Verify on hardware | |
| `CmdGetDigitalFilter.vi` | digital filter query | Verify on hardware | |
| `CmdSetDigitalFilter.vi` | digital filter set | Verify on hardware | |
| `CmdSetAcquisitionMode.vi` | acquisition mode set | Verify on hardware | |
| `CmdGetAcquisitionMode.vi` | acquisition mode query | Verify on hardware | |
| `CmdSetZeroValue.vi` | zero/calibrate set | Verify on hardware | |
| `CmdGetZeroValue.vi` | zero query | Verify on hardware | |
| `CmdSetAttenuatorEnable.vi` | attenuator enable set | Verify on hardware | |
| `CmdGetAttenuatorEnable.vi` | attenuator enable query | Verify on hardware | |
| `CmdGetIdentification.vi` | `*IDN?` (or vendor equivalent) | Mapped | Used optionally in Python script. |
| `GetZeroOffset.vi` | device zero offset read | Verify on hardware | Could be derived command/API read. |
| `GetNumChannels.vi` | channel count query | Verify on hardware | |
| `SetChannel.vi` | channel selection set | Verify on hardware | |
| `GetSampleCount.vi` | sample count/statistics read | Verify on hardware | |
| `GetFrequency.vi` | frequency query | Verify on hardware | |
| `GetFrequencyValue.vi` | parsed frequency numeric | Workflow/API | Post-query conversion likely. |
| `PerformDAQ.vi` | acquisition orchestration loop | Workflow/API | Equivalent to run loop logic. |
| `GetStatsMean.vi` | statistics mean query | Verify on hardware | |
| `GetStatsMax.vi` | statistics max query | Verify on hardware | |
| `GetStatsMin.vi` | statistics min query | Verify on hardware | |
| `GetStatsStdDev.vi` | statistics std-dev query | Verify on hardware | |
| `GetStatsRange.vi` | statistics range query | Verify on hardware | |
| `CmdGetStatsMeanValue.vi` | statistics mean numeric value | Workflow/API | Likely parse helper. |
| `CmdGetStatsMaxValue.vi` | statistics max numeric value | Workflow/API | |
| `CmdGetStatsMinValue.vi` | statistics min numeric value | Workflow/API | |
| `CmdGetStatsStdDevValue.vi` | statistics std-dev numeric value | Workflow/API | |
| `CmdGetStatsMaxMinusMinValue.vi` | statistics span (`max-min`) | Workflow/API | Derived from two stats. |
| `GetFirstDeviceKey.vi` | first connected device handle/key | Workflow/API | Discovery helper, not direct SCPI. |
| `InitCmdLib.vi` | command library init/loading | Workflow/API | Startup helper around DLL/API. |

## Practical next step

When hardware is available, validate each **Verify on hardware** row by running direct queries and recording:
1. accepted command string,
2. raw response shape,
3. parsed numeric/unit behavior,
4. error code/timeout behavior.

After validation, this file can become the authoritative migration table.
