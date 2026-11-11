# Contributing

This is a beta Omarchy plugin. Keep changes small, hardware access explicit, and unsupported devices read-only. RGB/lighting controls are out of scope. Contributions are licensed under the repository's MIT license; retain upstream license notices for dependencies rather than copying their binaries into the source tree.

## Offline development checks

Use Python 3.11 or newer and Node.js 22. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'rivalcfg==4.17.0' 'hidapi==0.15.0'
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s . -p 'test_*.py' -v
node test_model.cjs
node test_notifications.cjs
.venv/bin/python -m compileall -q -x '(^|/)(\.git|\.venv|venv|__pycache__)(/|$)' .
.venv/bin/python scripts/check-release.py .
```

The suite does not require attached devices, Bluetooth, a system D-Bus connection, HeadsetControl, root access, or udev changes. The pinned `hidapi` wheels provide the native code used when importing the real `rivalcfg` encoder. Do not add system HID/D-Bus packages to CI unless a new test genuinely requires them. Do not use `--system-site-packages` to hide missing dependencies. Test temporary directories use Python's `tempfile` defaults, respecting `TMPDIR`; set `TMPDIR` to an existing writable directory when needed.

Every control write test must inject a fake transport. The real-encoder test uses pinned rivalcfg with fake HID and checks exact packets. Never replace it with a mocked encoder or run a CLI Apply against attached hardware in CI. Hardware controls are experimental, disabled by default, and must require explicit user opt-in and Apply; no startup restore or polling writes.

Two live **read** smoke tests are skipped by default. Only on a machine where reading attached devices and the system bus is intentional:

```sh
STEELSERIES_HARDWARE_TESTS=1 .venv/bin/python -m unittest -v \
  test_fleet.FleetTests.test_cli_outputs_one_json_snapshot \
  test_connectivity.ConnectivityTests.test_bluetooth_cli_emits_inventory_list_or_explicit_failure
```

These are not needed for CI, do not validate Apply, and may send read-query packets to devices. Do not attach their raw output or private telemetry to public issues.

## QML checks

GitHub Actions has an opt-in `qml_check` input on manual runs. It installs real Qt 6 tools, parses each QML file with `qmlformat` without rewriting it, then runs advisory `qmllint`. Full type checking needs the actual Omarchy/Quickshell import modules on the target desktop. Missing imports are not fixed with synthetic mocks, and advisory lint is not proof the plugin loads. Check loading, settings, and lifecycle manually in a disposable desktop configuration before release.

## Before a pull request or release

- Add a failing regression test before changing behavior, then run all checks.
- Keep the canonical plugin ID `bart.steelseries` and display name `SteelSeries Devices`. Old IDs belong only in explicit migration/compatibility code, fixtures, and documentation. Device model names such as Arctis Nova 5 are valid, not old plugin identities.
- Keep writable descriptor, CLI-option and HID-command allowlists non-RGB and fail-closed. Update safety tests and audit checks deliberately when reviewing a protocol change.
- Run `python scripts/check-release.py /path/to/source` on the actual source/export to publish. It works independently of the current directory and does not access hardware. Its static checks are guardrails, not a security proof.
- Inspect the staged diff and release export manually for secrets, user paths, serials, addresses, logs, history databases, settings, profile data, screenshots and binaries. Ignored local venvs/caches are excluded from a filesystem audit, but tracked copies are rejected; `.gitignore` is not a privacy guarantee.
- Never enable automatic uploads of desktop screenshots, telemetry or logs. CI deliberately uploads none.

Do not publish package dependencies, virtualenvs, compiled helpers, or personal data. Report security concerns using [SECURITY.md](SECURITY.md).
