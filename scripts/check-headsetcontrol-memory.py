#!/usr/bin/env python3
"""Test real dependency HID overloads with ASan/UBSan and a no-hardware HIDAPI stub.

The caller supplies the checksum-pinned archive; this script never downloads,
opens a device, links HIDAPI or invokes a backend. --prove-regression requires
an expected assertion failure on original source, then a clean patched run.
"""
import argparse
import os
from pathlib import Path
import resource
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runtime
import setup


def compile_and_run(source, binary):
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++23', '-O1', '-g',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    '-I' + str(ROOT / 'tests/dependency-security'), '-I' + str(source),
                    str(ROOT / 'tests/dependency-security/zero_padding.cpp'),
                    str(source / 'lib/result_types.cpp'),
                    '-o', str(binary)], check=True, timeout=120)
    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=30,
                          env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=0',
                               'UBSAN_OPTIONS': 'halt_on_error=1'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--unpatched', action='store_true', help='diagnostic: expect a failing exit status')
    modes.add_argument('--prove-regression', action='store_true')
    args = parser.parse_args()
    if runtime.sha256_file(args.archive) != runtime.HEADSET_ARCHIVE_SHA256:
        parser.error('Source archive checksum mismatch')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with tempfile.TemporaryDirectory(prefix='steelseries-memory-') as tmp:
        work = Path(tmp)
        with tarfile.open(args.archive) as archive:
            archive.extractall(work, filter='data')
        source = work / ('HeadsetControl-' + runtime.HEADSET_COMMIT)
        binary = work / 'zero-padding-test'
        if args.prove_regression:
            baseline = compile_and_run(source, binary)
            if baseline.returncode == 0 or 'packet[i] == 0' not in baseline.stderr:
                print(baseline.stdout + baseline.stderr, file=sys.stderr)
                raise RuntimeError('Expected original-source padding assertion, not a compile/runtime error')
            print('RED confirmed: original production overload fails zero-padding assertion', flush=True)
        if not args.unpatched:
            setup.patch_headsetcontrol(source)
        result = compile_and_run(source, binary)
        print(result.stdout, end='', flush=True)
        if result.returncode:
            print(result.stderr, end='', file=sys.stderr)
            print('FAIL: real dependency HID regression (no hardware accessed)', flush=True)
            return 1
        print('PASS: AddressSanitizer + UndefinedBehaviorSanitizer; production dependency header', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
