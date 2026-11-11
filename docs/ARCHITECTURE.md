# Architecture

SteelSeriesService.qml is one shared singleton for all monitor bars. It starts bounded snapshot requests, maintains notification debounce/latches, and serializes explicit preference/hardware operations. Panel.qml and its lazy tabs display plain text for device-originated values.

app.py is the application dispatcher. A user-session flock prevents overlapping acquisition and hardware Apply. fleet.py isolates USB and Bluetooth collection in timeout-bounded workers, exports partial-source errors, and never changes user hardware settings. Battery-query packets are telemetry requests, not configuration writes.

prefs.py validates and atomically writes preference JSON with mode 0600. history.py records valid telemetry in SQLite, prunes 30-day retention and derives estimates from actual discharge segments. runtime.py and setup.py separate optional dependencies/provenance from published plugin source.

controls.py performs only explicit, opted-in Apply requests. Capability inspection has no hardware writes. Payloads are validated before a bounded worker, identities are rechecked before opening the physical device, duplicate headset targets fail closed, and unsupported commands are rejected. No firmware flashing, RGB commands or automatic restore exists.

There is no runtime network access for monitoring. setup.py may access the network only when the operator explicitly requests dependency installation. Plugins are unsandboxed desktop code: this design reduces accidental side effects, not the permissions of the owning user.

Default persistent paths respect XDG configuration/data/state locations. Device history and preferences remain outside the plugin Git checkout, so upgrades do not overwrite them. Do not attach raw history, MAC addresses or device serials to public bug reports.
