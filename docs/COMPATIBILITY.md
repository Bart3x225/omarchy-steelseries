# Compatibility and test boundaries

## Inventory

Physical SteelSeries USB devices (vendor 1038) are shown independently of battery support, including wired keyboards and mousepads. HID interfaces are not separate devices; two physically separate identical peripherals remain separate.

Known paired SteelSeries Bluetooth devices are read through BlueZ. Standard Battery1 is preferred; UPower fallback requires exact identity. No radio scanning, pairing or connection is performed. Bluetooth/USB entries merge only when an unambiguous shared hardware identity exists, never just because names match.

## Battery telemetry

| Model | Transport | Verification |
| --- | --- | --- |
| Arctis Nova 5 (1038:2232) | 2.4 GHz USB receiver | Actual normal-user battery reads and online/offline states tested |
| Aerox 5 Wireless (1038:1854) | USB cable | Actual battery and charging reads tested |
| Aerox 5 Wireless (1038:1852) | 2.4 GHz receiver | Actual normal-user battery reads tested |
| Apex 9 Mini (1038:1620) | USB | Inventory tested; no battery expected or fabricated |
| QCK Prism Cloth (1038:150d) | USB | Inventory tested; no battery expected or fabricated |
| Other HeadsetControl-supported SteelSeries headsets | Backend-dependent | Not physically tested by this project |
| Aerox special editions / Nova 5X | Audited backend profiles | Automated protocol tests only |
| SteelSeries Bluetooth telemetry and dual-transport merging | BlueZ / UPower | Real service access and fixture tests; no paired SteelSeries Bluetooth hardware was available |

An unknown battery is not 0%. Read errors and inventory-source failures are not confirmed disconnects. Firmware and operating-system permissions can affect individual models.

## Experimental controls

Hardware controls are off by default. Enable them in Settings only if you accept the experimental status, then edit fields and click Apply. Neither enabling the feature nor loading a saved profile applies hardware settings.

Nova 5/5X: sidetone, EQ presets and auto-off. Aerox 5 Wireless: DPI, reporting rate and sleep timer. Setting DPI replaces the mouse's DPI preset list with a single preset. Bluetooth-only controls are not supported. Lighting belongs exclusively to OpenRGB; there are no RGB controls or writes.

Write packets, target validation, command allowlists and failure behavior have automated tests with injected transports. Physical hardware-setting writes have NOT been performed as a release-verification step. Backend acknowledgement is labelled unverified, not independent setting readback. Multiple settings are not an atomic transaction; a failure can leave earlier settings applied.

## History and estimates

History contains actual successful readings only. Sampling is throttled, retained locally for 30 days and limited to 200 displayed points per device. Runtime estimates need a continuous discharge segment of at least 30 minutes, at least three measurements and at least five percentage-points of decline. They are approximate and are withheld when data is insufficient.
