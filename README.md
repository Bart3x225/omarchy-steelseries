# SteelSeries Devices for Omarchy

A community Omarchy/Quickshell bar plugin for SteelSeries peripheral battery status, connection notifications, local history and opt-in experimental hardware controls.

Plugin ID: `bart.steelseries` · Release: `0.1.0-beta.2` · Own code: MIT

Not affiliated with SteelSeries. This is a beta, not a claim of universal SteelSeries support. Read [compatibility and verification limits](docs/COMPATIBILITY.md) before enabling hardware controls.

## Features

- One icon per detected device: headsets, mice, keyboards, mousepads and unknown SteelSeries USB peripherals.
- Valid battery percentages and charging states where supported; no fabricated charge for unsupported models.
- Five-second polling by default, configurable thresholds and per-device bar visibility.
- Separate 20% low / 5% critical / full-charge alerts; connection changes require two consecutive observations.
- Read-only paired Bluetooth inventory through BlueZ and identity-checked UPower fallback. USB/Bluetooth entries merge only with exact hardware identity.
- Local 30-day battery history and a chart; approximate runtime appears only after sufficient actual discharge measurements.
- Optional, off-by-default hardware controls: Aerox 5 DPI/reporting/sleep and Nova 5/5X sidetone/EQ presets/auto-off. Only edited values are sent after **Apply**. No automatic restore.
- English and Polish strings follow Omarchy's selected language.
- No RGB control, firmware flashing or runtime telemetry uploads. OpenRGB remains responsible for lighting.

## Requirements

Omarchy with its Quickshell plugin host, Linux, system Python 3.12+, Python HID bindings, and optional Python D-Bus bindings with BlueZ/UPower for Bluetooth. Dependencies vary by distribution; see [dependency setup](docs/DEPENDENCIES.md).

HeadsetControl and rivalcfg are external dependencies, not binaries bundled in this repository. The explicit setup tool builds a pinned, checksum-verified HeadsetControl source revision and can create an isolated mouse-control environment. Installing the plugin alone does not run a downloader or a hardware configuration command.

## Installation

Review the source, then add the plugin without enabling it:

```sh
omarchy plugin add https://github.com/Bart3x225/omarchy-steelseries.git
cd ~/.config/omarchy/plugins/bart.steelseries
python3 setup.py --check
```

When the Omarchy installer asks about enabling the plugin, choose **No** until dependencies are ready. Install the documented system prerequisites first. To explicitly prepare the optional dependencies:

```sh
python3 setup.py --headsetcontrol
python3 setup.py --mouse-controls
python3 setup.py --check
omarchy plugin enable bart.steelseries --section right
```

`--headsetcontrol` downloads and builds upstream source; `--mouse-controls` downloads Python packages into an isolated user environment. These commands do not apply DPI, EQ, lighting or other hardware settings. Review [dependency/license details](docs/DEPENDENCIES.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

If HID access is denied, use the narrowly scoped udev-rule instructions in the dependency guide. Do not run the bar or its polling backend as root. Never replace access rules with world-writable access to all HID devices.

## Security upgrade from beta.1

After updating the plugin to beta.2, explicitly rebuild the headset dependency:

```sh
python3 -B setup.py --headsetcontrol
python3 -B setup.py --check
```

Beta.1 pinned a HeadsetControl revision with unsafe explicit-size HID writes in the Nova 5/5X setting path. Beta.2 applies a verified zero-padding patch before building. Older builds and arbitrary PATH executables are no longer used, including for polling; headset telemetry/controls remain unavailable until this explicit rebuild. Mouse monitoring, preferences and history are unaffected. No settings are automatically applied. See [dependency patch and regression proof](docs/DEPENDENCIES.md#security-patch-and-regression-proof).

## Usage

Click a device icon. Tabs: **Status**, **Settings**, **Hardware**, **History**. Right-click refreshes; Escape closes.

Settings are saved explicitly. Hardware controls are disabled by default; opting in does not apply anything. Their inputs are draft values, not a current-setting readout. Only fields you edit are sent after **Apply**. Setting Aerox DPI replaces its preset list with one preset.

Hardware-setting writes have automated injected-transport tests, but have not been physically verified as a release step. Responses are labelled unverified rather than pretending the device independently confirmed each setting. Operations are not transactional; a failure may leave an earlier setting applied. Details: [compatibility](docs/COMPATIBILITY.md).

Diagnostics (may contain serials/MACs; redact before posting):

```sh
omarchy-shell bart.steelseries.status status
omarchy-shell bart.steelseries.status refresh
omarchy-shell bart.steelseries showPage settings
python3 app.py snapshot
```

## Upgrade from the old custom Nova 5 plugin

Install `bart.steelseries` and dependencies first. Keep the old plugin until the new one is ready, then preview and explicitly apply the migration:

```sh
cd ~/.config/omarchy/plugins/bart.steelseries
python3 migrate.py
python3 migrate.py --apply
omarchy-shell shell rescanPlugins
```

Migration replaces the exact legacy plugin ID in the bar layout, preserves its placement/inline settings, backs up `shell.json`, and archives the old plugin outside the watched plugin directory. It does not delete preferences/history or write to hardware. The command prints the backup path. Restart the shell if stale QML remains.

## Data and removal

Default user paths (XDG environment overrides are respected):

- Preferences: `~/.config/omarchy/steelseries/settings.json`
- History: `~/.local/state/omarchy/steelseries/history.sqlite3`
- Optional dependency builds/environments: `~/.local/share/omarchy-steelseries/`
- Migration backups: `~/.local/state/omarchy/steelseries/migrations/`

Disable or uninstall the plugin with Omarchy:

```sh
omarchy plugin disable bart.steelseries
omarchy plugin remove bart.steelseries
```

Removal does not erase your history or dependency environment. You can manually remove the listed plugin-owned user directories if you no longer need them. Remove only a udev rule that you personally installed for this plugin; do not remove another application's shared rules. Nothing flashes firmware or restores hardware settings during uninstall.

## Development

See [contributing](CONTRIBUTING.md), [security](SECURITY.md), [architecture](docs/ARCHITECTURE.md) and the repository CI workflow. Tests use fixtures/fake transports; live hardware tests are opt-in. Do not add real hardware-setting writes to CI.

```sh
python3 -B -m unittest discover -s . -p 'test_*.py'
node test_model.cjs
node test_notifications.cjs
python3 scripts/check-release.py
omarchy plugin validate .
```

Qt6 linting needs the Omarchy `qs.*` imports; live popup/log checks are still required. Report firmware, PID/transport, observed behavior and whether it was hardware-tested, without posting personal device identities.

## License

Own source: [MIT](LICENSE), except the HeadsetControl dependency patch under [GPLv3](patches/LICENSE). Dependencies retain their own licenses, notably HeadsetControl GPLv3 and rivalcfg WTFPL. No compiled HeadsetControl binary is distributed by this repository or release. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
