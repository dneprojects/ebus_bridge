# Changelog

## 1.2.1
- Sensor display precision derived from the data type (integer registers show without decimals).

## 1.2.0
- New `climate` entity per active heating zone (`Z<n>RoomTemp` / `Z<n>DayTemp` / `Z<n>OpMode`).

## 1.1.0
- New `water_heater` for DHW (`HwcStorageTemp` / `HwcTempDesired` / `HwcOpMode`).
- New `switch` "Warmwasser-Boost" (`HwcSFMode` = load/auto).

## 1.0.0
- Config flow pre-fills the host with the HA IP (editable for remote ebusd).
- First public release (HACS).

## 0.10.0
- Bundled brand icon (`brand/` folder); local icon takes priority over the brands CDN (HA 2026.3+).

## 0.9.0
- Fix: °C setpoints no longer clamped to 0–100 (range −60…150, negative values possible).
- Bridge device is named just "eBUS Bridge"; host exposed as its own text sensor (diagnostic).
- Unit tests for `model.py` + CI (hassfest, HACS, ruff, pytest); `codeowners` set.

## 0.8.0
- Bridge diagnostics from ebusd's global section (signal, symbol rate, reconnects, masters, QQ, version).
- Enhanced timing (arbitration/latency) as diagnostics, disabled by default.

## 0.7.3
- Icon heuristic, unit-first: temperatures always as a thermometer variant.

## 0.7.2
- Meaningful mdi icons for all entities instead of generic slider symbols.

## 0.7.1
- Clean per-circuit device names (no "ebusd" prefix); bridge parent device, circuits as children (`via_device`).

## 0.7.0
- Writable calendar (create/update/delete) once ebusd exposes a timer write message.

## 0.6.0
- New `ebus_bridge.write` service (generic pass-through to ebusd's `write`, with read-back).

## 0.5.0
- Renamed to "eBUS Bridge" (domain `ebus_bridge`); new switch platform; `issue_tracker` added.

## 0.4.1
- Fix: forced read after each write so setpoints don't fall to "unavailable".

## 0.4.0
- New binary_sensor + calendar (read-only) platforms; options flow (poll interval, exclude).

## 0.3.0
- Switched to ebusd HTTP-JSON (read) + TCP (write); field-based entity model; device metadata.
