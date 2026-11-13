#!/usr/bin/env python3
"""Explicit, user-local dependency setup. Never run with sudo."""
import sys
sys.dont_write_bytecode = True  # --check/help must not leave plugin __pycache__ files.
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
import tarfile
import tempfile
import urllib.request

import runtime


def patch_headsetcontrol(source):
    """Apply one audited dependency patch, verifying input, patch and output bytes."""
    patch_file = Path(__file__).resolve().parent / 'patches/headsetcontrol-zero-padding.patch'
    header = Path(source) / 'lib/devices/hid_interface.hpp'
    if runtime.sha256_file(patch_file) != runtime.HEADSET_PATCH_SHA256:
        raise ValueError('HeadsetControl patch checksum mismatch')
    if runtime.sha256_file(header) != 'd8dfa8bb618c6d7c22f511c31344cd78be32197a1d4728b29a32e3092f9db545':
        raise ValueError('Unexpected HeadsetControl header; refusing patch/build')
    subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch_file)],
                   cwd=source, check=True, timeout=30)
    if runtime.sha256_file(header) != '66e9ae0ee9a6a27da9a05bc35bcbbcaa7b6e9da7bcced38a6027ec0cec9cd81e':
        raise ValueError('Patched HeadsetControl header checksum mismatch')
    return patch_file


def build_headsetcontrol():
    """Download verified immutable source; build only the CLI target, not tests.

    Keep the last valid installation intact until compilation has succeeded.
    No cmake install, backend invocation, or system permission changes occur.
    """
    root = runtime.headset_dir()
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.build-', dir=root.parent) as tmp:
        work = Path(tmp)
        archive = work / 'source.tar.gz'
        with urllib.request.urlopen(runtime.HEADSET_URL, timeout=60) as response, archive.open('wb') as out:
            shutil.copyfileobj(response, out)
        if runtime.sha256_file(archive) != runtime.HEADSET_ARCHIVE_SHA256:
            raise ValueError('HeadsetControl source archive SHA256 mismatch; refusing build')
        source_parent = work / 'source'
        source_parent.mkdir()
        with tarfile.open(archive) as tf:
            # Python's data filter rejects traversal/escaping links and special files.
            tf.extractall(source_parent, filter='data')
        sources = list(source_parent.iterdir())
        if len(sources) != 1 or not sources[0].is_dir():
            raise ValueError('Unexpected HeadsetControl archive layout')
        source = sources[0]
        patch_file = patch_headsetcontrol(source)
        build = work / 'build'
        subprocess.run(['cmake', '-S', str(source), '-B', str(build),
                        '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_UNIT_TESTS=OFF',
                        f'-DHEADSETCONTROL_VERSION=0.0.0-{runtime.HEADSET_COMMIT}'], check=True, timeout=120)
        subprocess.run(['cmake', '--build', str(build), '--target', 'headsetcontrol',
                        '--parallel', '2'], check=True, timeout=600)
        # Receipt is committed last; interrupted replacement fails closed for Apply.
        root.mkdir(parents=True, exist_ok=True)
        (root / 'receipt.json').unlink(missing_ok=True)
        (root / 'bin').mkdir(exist_ok=True)
        binary = root / 'bin/headsetcontrol'
        shutil.copy2(build / 'headsetcontrol', binary)
        shutil.copy2(archive, root / 'source.tar.gz')
        shutil.copy2(patch_file, root / patch_file.name)
        shutil.copy2(source / 'license', root / 'LICENSE')
        (root / 'NOTICE').write_text(
            'HeadsetControl is a separate external dependency by its upstream authors.\n'
            'Upstream: https://github.com/Sapd/HeadsetControl\n'
            f'Source commit: {runtime.HEADSET_COMMIT}\n'
            'License: GPL-3.0; see LICENSE and the retained complete source.tar.gz.\n'
            'Locally modified: explicit-size HID writes/feature reports zero-pad short commands.\n'
            'Reconstruct source: extract source.tar.gz, then patch -p1 < headsetcontrol-zero-padding.patch\n'
            f'Patch SHA256: {runtime.HEADSET_PATCH_SHA256}\n'
            'The plugin MIT license does not relicense HeadsetControl or this dependency patch.\n')
        receipt = dict(source_commit=runtime.HEADSET_COMMIT,
                       source_url=runtime.HEADSET_URL,
                       source_archive_sha256=runtime.HEADSET_ARCHIVE_SHA256,
                       patch_sha256=runtime.HEADSET_PATCH_SHA256,
                       binary_sha256=runtime.sha256_file(binary))
        pending = root / 'receipt.json.new'
        pending.write_text(json.dumps(receipt, indent=2) + '\n')
        pending.replace(root / 'receipt.json')
    print(f'Built pinned HeadsetControl: {binary}')
    return binary


def install_mouse_controls():
    """No global pip, dependency resolution, or privileged installation."""
    python = runtime.mouse_python()
    python.parent.parent.parent.mkdir(parents=True, exist_ok=True)
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(python.parent.parent)], check=True, timeout=120)
    subprocess.run([str(python), '-m', 'pip', '--isolated', 'install',
                    '--require-virtualenv', '--no-deps', '-r',
                    str(Path(__file__).resolve().parent / 'requirements-controls.txt')],
                   check=True, timeout=300)


def stage_udev_rules():
    """Stage uaccess for audited USB products only. Never modify /etc or reload."""
    directory = runtime.data_dir() / 'udev'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / '70-omarchy-steelseries.rules'
    lines = ['# Review before manual installation; active local seat access only.']
    for pid in ('2232', '2253', '1854', '1852', '185e', '185c', '1862', '1860'):
        lines.append('SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1038", '
                     f'ATTRS{{idProduct}}=="{pid}", TAG+="uaccess"')
    target.write_text('\n'.join(lines) + '\n')
    return target


def check():
    """Inspect files/import availability; never run a HID/backend executable."""
    try:
        pinned = str(runtime.headsetcontrol(for_apply=True))
    except ValueError as exc:
        pinned = str(exc)
    mouse = runtime.mouse_python()
    versions = {}
    if mouse.is_file():
        try:
            p = subprocess.run([str(mouse), '-B', '-c',
                'import json; from importlib.metadata import version; '
                'print(json.dumps({k:version(k) for k in ("rivalcfg","hidapi")}))'],
                capture_output=True, text=True, timeout=10, check=True,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            versions = json.loads(p.stdout)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    report = dict(data_dir=str(runtime.data_dir()),
                  headsetcontrol_polling=str(runtime.headsetcontrol() or ''),
                  headsetcontrol_apply=pinned, mouse_python=str(mouse), mouse_versions=versions,
                  system_python=sys.executable,
                  system_hid=importlib.util.find_spec('hid') is not None,
                  system_dbus=importlib.util.find_spec('dbus') is not None,
                  build_tools={name: shutil.which(name) for name in ('cmake', 'c++', 'patch', 'pkg-config')})
    print(json.dumps(report, indent=2))
    return 0 if (pinned == str(runtime.headset_dir() / 'bin/headsetcontrol')
                 and versions == {'rivalcfg': '4.17.0', 'hidapi': '0.15.0'}
                 and report['system_dbus'] and (report['system_hid'] or mouse.is_file())) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='read-only dependency report (exit 1 if incomplete)')
    parser.add_argument('--headsetcontrol', action='store_true', help='build the pinned external headset backend')
    parser.add_argument('--mouse-controls', action='store_true', help='install mouse dependencies in an isolated venv')
    parser.add_argument('--all', action='store_true', help='build headset and install mouse dependencies')
    parser.add_argument('--udev-rules', action='store_true', help='stage a scoped rule file for manual review; never install it')
    args = parser.parse_args(argv)
    actions = args.headsetcontrol or args.mouse_controls or args.all or args.udev_rules
    if args.check and actions:
        parser.error('--check cannot be combined with installation/staging options')
    if args.check:
        return check()
    if not actions:
        parser.print_help()
        return 0
    if os.geteuid() == 0:
        parser.error('Run as your ordinary user, never root/sudo')
    try:
        if args.headsetcontrol or args.all:
            build_headsetcontrol()
        if args.mouse_controls or args.all:
            install_mouse_controls()
        if args.udev_rules:
            print(stage_udev_rules())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Setup failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
