# Security policy

## Scope and supported versions

This project is beta software. Security fixes target the latest published release and current default branch. There is no promise of support for older snapshots. Hardware Apply can change peripheral behavior; experimental controls are disabled by default and must be enabled deliberately.

## Reporting a vulnerability

Use the repository's **Security → Report a vulnerability** private reporting feature if it is enabled. If that option is unavailable, open a minimal issue asking the maintainer for a private reporting channel; do not post exploit details or sensitive attachments while arranging contact. Do not assume a public issue or email address is private.

Include the affected release, expected and observed behavior, and a minimal reproduction using fake devices/transports whenever possible. Redact serial numbers, Bluetooth addresses, USB topology, usernames, home directories and tokens. Never post history databases, settings/profile exports, screenshots, raw desktop logs or authentication material. No response-time SLA is offered.

## Safety boundaries

- Hardware writes require explicit user opt-in and Apply. No startup restore, polling writes, RGB/lighting controls, or automatic settings application.
- Control and telemetry tests use injected fake transports; CI must not access attached devices or the system bus. Live read smoke tests are separate and opt-in.
- Device selection must match an exact physical identity; ambiguous selections must fail closed.
- Apply results must not claim independent verification without a real getter. Accepted packets are not setting readback.
- Dependency versions and per-device command allowlists are audited together. A version bump needs protocol review, packet tests and regression checks.
- Runtime dependencies belong in isolated local installations, not in public source releases.

`check-release.py` checks common source-publication mistakes and non-RGB allowlists. It cannot prove that all secrets have been found, validate a dependency's provenance, or certify hardware safety. Review source and release contents before publishing. If a secret is exposed, revoke/rotate it first; removing a file from a new commit does not remove copies from history or forks.
