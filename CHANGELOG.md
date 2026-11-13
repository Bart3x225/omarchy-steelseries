# Changelog

## 0.1.0-beta.2

- Fix the pinned external HeadsetControl production HID overloads: short explicit-size writes and feature reports are zero-padded rather than reading beyond the command span. Preserve sidetone, EQ and auto-off controls.
- Verify the upstream archive, patch, original header and patched header before building. Retain the patch alongside corresponding source, license and receipt.
- Use a separate patched build directory and require its patch-aware checksum receipt for both telemetry and Apply; reject legacy builds and unverified PATH executables. Existing installations must explicitly rerun `python3 -B setup.py --headsetcontrol`.
- Add a no-hardware ASan/UBSan test compiled against real upstream production code: prove the original fails, then verify zero padding, exact/truncated/empty payloads, feature reports and backend errors after patching. Run this regression in CI.
- No physical device-setting writes were used to validate this fix; experimental controls remain opt-in and their hardware readback limitations are unchanged.

## 0.1.0-beta.1

- First public beta under `bart.steelseries` / SteelSeries Devices.
- Per-device USB/2.4 GHz inventory, supported headset/Aerox battery telemetry and paired Bluetooth discovery.
- Configurable monitoring, debounced notifications and local 30-day history.
- Explicit experimental-control opt-in; no automatic hardware-setting writes or RGB management.
- Portable dependency setup, test/CI scaffolding, MIT license and separate third-party notices.
- Migration from the earlier local plugin ID, preserving preferences and history.

Physical hardware-setting writes and SteelSeries Bluetooth telemetry remain unverified by this release's hardware test coverage.
