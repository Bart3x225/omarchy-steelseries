# Dependencies and explicit setup

The plugin's own code is MIT licensed. No compiled HeadsetControl binary,
HeadsetControl source tree or Python virtual environment is bundled in the plugin.
The small dependency patch and its GPLv3 license are included under `patches/`. External tools retain their own licenses.
Installing the plugin alone does not download, compile, install, or configure
anything. Importing its modules does not perform setup or query hardware.

## System prerequisites

Use Linux, Python 3.12 or newer, Quickshell/Omarchy, and a normal user session.
The core polling, normalization, preferences and history code uses Python's
standard library (including SQLite). USB inventory uses Linux sysfs. Aerox
battery reads additionally need the Python `hid` module supplied by `hidapi`;
this can come from the system Python or the isolated mouse venv below.
Bluetooth inventory uses **system Python's `dbus-python`** with the system
D-Bus and BlueZ services. UPower is optional for additional battery/charging
properties. Missing Bluetooth support is reported independently of USB results.
Neither Bluetooth discovery/pairing nor settings restoration is performed.

Building the pinned HeadsetControl requires CMake, a C++20 toolchain (GCC 13+
or Clang 16+), make/build tools, `patch`, pkg-config, and the hidapi library and headers.
The built CLI continues to need the system hidapi shared library. The mouse
venv requires Python venv/ensurepip support and network access to PyPI. If a
hidapi wheel is unavailable for your Python/architecture, pip may need the
compiler, Python headers, hidapi/libusb/udev development packages to build it.
No tool in this repository installs system packages.

Typical package names (review against your distribution release):

| Distribution | Build and Python prerequisites |
| --- | --- |
| Arch / Omarchy | `base-devel cmake pkgconf hidapi python python-pip python-dbus`; optional system `python-hidapi` |
| Ubuntu 24.04+ / Debian with GCC 13+ | `build-essential cmake pkg-config libhidapi-dev python3 python3-dev python3-venv python3-dbus`; optional system `python3-hid` |
| Fedora | `gcc-c++ make cmake pkgconf-pkg-config hidapi-devel python3 python3-devel python3-pip python3-dbus` |

Install such packages separately using your distribution's package manager.
Never run this setup script or pip with sudo/root. On Omarchy, use
`/usr/bin/python` so the Bluetooth worker and dependency report see system
D-Bus bindings; a separate developer Python may not see those packages.

## Commands

Run these in the plugin directory, as your ordinary user:

```sh
/usr/bin/python -B setup.py --help
/usr/bin/python -B setup.py --check
/usr/bin/python -B setup.py --headsetcontrol
/usr/bin/python -B setup.py --mouse-controls
# Equivalent to the previous two installation operations:
/usr/bin/python -B setup.py --all
# Separately, only if you need a permissions template:
/usr/bin/python -B setup.py --udev-rules
```

No arguments prints help without installing anything. `--check` performs
read-only inspection (no backend/HID invocation, downloads, mkdir, pip, or
hardware operations). It reports paths, receipt validation, installed mouse
package versions, system imports and build-tool availability. Exit status 0
means both pinned controls backends and telemetry imports are ready; 1 means
something is missing or mismatched. Missing build tools alone do not invalidate
an already built backend. It does not test device permissions, service health,
wireless connectivity or settings readback. `--check` cannot be combined with installation/staging flags.

All application dependencies live under
`${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-steelseries`. XDG_DATA_HOME must
be absolute; unset, empty or relative values use `$HOME/.local/share`.
The default mouse path remains compatible with an existing
`~/.local/share/omarchy-steelseries/venv` installation. Set XDG_DATA_HOME before
both setup and launching the plugin if you relocate dependencies.

### HeadsetControl: pinned, separately built

- Upstream: <https://github.com/Sapd/HeadsetControl>
- Source commit: `0c8a76fa019cd02263a1c69e00e18e229b16d87f`
- Archive: <https://codeload.github.com/Sapd/HeadsetControl/tar.gz/0c8a76fa019cd02263a1c69e00e18e229b16d87f>
- Archive SHA256: `4215cef92588422eb326390be11e1f5308e98b35a551e187f17c3eed1c199402`

That SHA256 was calculated from the actual downloaded archive, not from a
local prebuilt executable. Setup verifies it **before extraction/building**.
It safely extracts the archive, builds only CMake's `headsetcontrol` target,
and never runs `cmake --install`, the CLI's default action, its integration
tests, or any hardware command. Build work is outside the plugin, in a
temporary directory within the XDG dependency tree.

The installation at `headsetcontrol/<commit>-zero-padding-v1/` contains:

- `bin/headsetcontrol`: the locally built executable;
- `source.tar.gz`: the complete verified upstream source archive;
- `headsetcontrol-zero-padding.patch`: the exact applied GPLv3 dependency patch;
- `LICENSE`: the upstream archive's `license` (GNU GPL version 3);
- `NOTICE`: upstream attribution, source commit and license separation;
- `receipt.json`: source URL/commit/archive SHA256, patch SHA256 and **this build's** binary
  SHA256. The receipt is written last; incomplete installs cannot enable Apply.

Both polling and Apply require the patched local executable and validate its
pinned source commit, archive digest, patch digest and current binary checksum
against the build receipt. Unverified PATH backends and old cached builds are
not used. No machine-specific binary hash is baked into the plugin.
Capabilities only inspect local files/receipts: no subprocesses or hardware
queries. A failed/missing receipt hides headset controls until explicit setup.
The worker revalidates immediately before launching a setting command.

A receipt guards accidental replacement and unsupported versions; it is not a
signature or protection against the user who owns both receipt and executable.
Compiler/OS differences may legitimately produce different binary hashes.
Retain the archive/license/notices when moving a locally built backend. The
plugin's MIT license does not relicense this GPL dependency; distributing
HeadsetControl binaries carries separate GPL obligations, including applicable
corresponding-source requirements. This repository does not distribute them.

### Security patch and regression proof

Beta.1 used short Nova 5/5X commands with an explicit 64-byte write size.
The pinned production HID overload forwarded that size without padding,
reading beyond the command buffer. Beta.2 fixes the production explicit-size
write and feature-report overloads to copy the payload into zero-initialized
storage whenever the requested report is larger than the input span.

Setup applies `patches/headsetcontrol-zero-padding.patch` with zero fuzz after
verifying the source archive and original header. It verifies both the patch
and resulting header hashes and aborts before compilation on any mismatch.
Patch SHA256: `f4f3064a677fbaa205bf62e28440a3f999e3b77fa43d5928b3d1d3227c4b7151`.
The separate build directory and mandatory patch-aware receipt invalidate old
installs. Update the plugin, then explicitly rerun `python3 -B setup.py --headsetcontrol`;
no background rebuild, download or hardware-setting change occurs.

For an offline regression, supply the retained verified upstream archive:

```sh
python3 -B scripts/check-headsetcontrol-memory.py --archive /absolute/path/to/source.tar.gz --prove-regression
```

This compiles the actual upstream `RealHIDInterface` and result implementation
with C++23, AddressSanitizer and UndefinedBehaviorSanitizer. Only the HIDAPI
boundary is stubbed, so no devices can be opened. It requires the original
zero-padding assertion to fail, then runs short/exact/truncated/empty writes,
feature reports and failure propagation against the patched implementation.
The CI security job downloads only the pinned archive and runs the same proof.

### Mouse controls: isolated Python environment

`--mouse-controls` creates/reuses `venv/`, then runs **that interpreter's** pip
with `--isolated --require-virtualenv --no-deps` and the exact requirements:

```text
rivalcfg==4.17.0
hidapi==0.15.0
```

There is no global/user pip install and no unpinned runtime dependency
resolution. These are version pins, not a cross-platform wheel hash lock;
packages are fetched from pip's default index. Existing installed dependency
license metadata remains in the venv. The `hidapi` Python binding and its
underlying native library retain their respective upstream license terms;
rivalcfg also retains its own upstream license. Lighting remains exclusively
OpenRGB-owned: the plugin never calls rivalcfg RGB/reset/default APIs.
Aerox telemetry workers prefer this venv when available, otherwise system
Python; Bluetooth workers always use system Python. Hardware settings remain
behind explicit, opt-in, per-device Apply. Setup itself never changes settings.

## Optional staged permissions rules

`--udev-rules` writes only the staged rule file
`udev/70-omarchy-steelseries.rules` under the XDG dependency directory. It
matches `hidraw`, SteelSeries vendor `1038`, and only the eight audited headset
and Aerox product IDs. It grants `uaccess` to the active local session; it does
not use world-writable modes, invoke programs, touch `/etc`, reload udev,
reconnect devices, or run a root install. Review the file and existing
OpenRGB/distribution rules first. Any administrator installation and subsequent
udev reload/replug are separate, manual decisions. Permissions do not establish
that an unsupported model is safe to control.

## Offline verification and removal

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python -m unittest test_runtime test_setup -v
```

Tests build fake backends only inside unittest fixtures and never issue real
hardware setting commands. For an isolated real dependency build, set
XDG_DATA_HOME to an absolute scratch directory and run `--all`, then `--check`.
There is deliberately no hardware smoke-test command in the installer.

To remove dependencies, stop the plugin and remove only the
`headsetcontrol/`, `venv/`, and optional `udev/` subdirectories from the XDG
dependency directory after reviewing the paths. Do not remove the whole parent
if it also contains your history/preferences. Removing a staged rule does not
remove a separately, manually installed system rule.
