#!/usr/bin/env python3
"""Offline source/publication audit. No imports of application or hardware modules.

This is a conservative gate, not proof that a tree contains no sensitive material.
Review the staged diff and export separately before publishing.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys


LOCAL_ONLY = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
PRIVATE_DIRS = {'.hermes', '.ssh', '.gnupg', '.config', '.local', 'profiles', 'memories', 'sessions',
                'vault', 'telemetry', 'screenshots', 'logs', 'node_modules'}
PRIVATE_NAMES = {'settings.json', 'history.sqlite3', 'credentials', 'credentials.json', 'id_rsa', 'id_ed25519',
                 'Login Data', 'Cookies', 'Web Data', 'Preferences', 'Local State'}
BINARY_SUFFIXES = {'.so', '.dll', '.exe', '.pyc', '.pyo', '.o', '.a', '.deb', '.rpm', '.zip', '.tar', '.gz'}
PRIVATE_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.log', '.pem', '.key', '.png', '.jpg', '.jpeg', '.webp'}
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|sk-(?:proj-)?[A-Za-z0-9_-]{24,})')
USER_PATH = re.compile(r'(?:/(?:home|Users)/[A-Za-z0-9_.-]+(?:/|\b)|[A-Za-z]:\\Users\\[^\\\s]+)')
CONTROL_KEYS = {'inactive_time', 'equalizer_preset', 'sidetone', 'dpi', 'polling_rate', 'sleep_timer'}


def control_errors(path):
    """Check writable descriptors and the packet/CLI allowlists without executing code."""
    errors = []
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        descriptors = set()
        for node in ast.walk(functions['capabilities']):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in {'_integer', '_choice'}):
                descriptors.add(ast.literal_eval(node.args[0]))
        if descriptors != CONTROL_KEYS:
            errors.append('controls.py: writable descriptors differ from audited non-RGB allowlist')
        expected = {
            ('_execute', 'options'): {'inactive_time': ('--inactive-time', 'CAP_INACTIVE_TIME'),
                                     'equalizer_preset': ('--equalizer-preset', 'CAP_EQUALIZER_PRESET'),
                                     'sidetone': ('--sidetone', 'CAP_SIDETONE')},
            ('_apply_mouse', 'names'): {'dpi': 'sensitivity', 'polling_rate': 'polling_rate', 'sleep_timer': 'sleep_timer'},
            ('_apply_mouse', 'commands'): {'dpi': 0x2d, 'polling_rate': 0x2b, 'sleep_timer': 0x29},
        }
        for (function, variable), value in expected.items():
            matches = [n.value for n in ast.walk(functions[function]) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == variable for t in n.targets)]
            if len(matches) != 1 or ast.literal_eval(matches[0]) != value:
                errors.append(f'controls.py: {function}.{variable} changed; re-audit non-RGB write boundary')
        checked = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_CheckedHID')
        allowed = [n.value for n in ast.walk(checked) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Attribute) and t.attr == 'allowed' for t in n.targets)]
        if (len(allowed) != 1 or not isinstance(allowed[0], ast.SetComp)
                or ast.literal_eval(allowed[0].generators[0].iter) != (0x2d, 0x2b, 0x29, 0x11)):
            errors.append('controls.py: HID opcode allowlist changed; lighting/RGB writes must remain excluded')
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ''
                if re.search(r'(?:rgb|lighting|set_light|set_color|factory_reset|reset_settings)', name, re.I):
                    errors.append(f'controls.py:{node.lineno}: prohibited lighting/reset call {name}')
    except (OSError, SyntaxError, ValueError, TypeError, KeyError, StopIteration, IndexError) as exc:
        errors.append(f'controls.py: cannot audit write allowlists ({type(exc).__name__}: {exc})')
    return errors


def audit(root):
    root = Path(root).resolve()
    if not root.is_dir():
        return ['repository root is not a directory']
    errors = []
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('id') != 'bart.steelseries' or manifest.get('name') != 'SteelSeries Devices':
            errors.append('manifest.json: expected id bart.steelseries and name SteelSeries Devices')
        if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', str(manifest.get('version', ''))):
            errors.append('manifest.json: version must be a release or prerelease version')
        entries = manifest.get('entryPoints', {})
        if not entries or not isinstance(entries, dict):
            errors.append('manifest.json: entryPoints must name existing local source files')
        else:
            for value in entries.values():
                if (not isinstance(value, str) or Path(value).is_absolute() or '..' in Path(value).parts
                        or not (root / value).is_file()):
                    errors.append('manifest.json: invalid or missing entry point')
    except (OSError, ValueError, AttributeError) as exc:
        errors.append(f'manifest.json: unreadable or invalid ({exc})')
    for name in ('LICENSE', 'README.md'):
        try:
            text = (root / name).read_text(encoding='utf-8')
            if not text.strip():
                errors.append(f'{name}: must not be empty')
            if name == 'LICENSE' and not all(marker in text for marker in (
                    'MIT License', 'Permission is hereby granted, free of charge',
                    'THE SOFTWARE IS PROVIDED "AS IS"')):
                errors.append('LICENSE: expected MIT license grant and disclaimer')
        except OSError:
            errors.append(f'{name}: required release file missing')
    paths = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in list(dirs):
            path = parent / name
            if path.is_symlink():
                paths.add(path)
                dirs.remove(name)
            elif name in LOCAL_ONLY:
                dirs.remove(name)
            elif name in PRIVATE_DIRS or name == 'bin':
                errors.append(f'{path.relative_to(root)}: private/generated/bundled directory is not publishable')
                dirs.remove(name)
        paths.update(parent / name for name in files)
    # Ignored local caches are fine; accidentally tracked caches/venvs are not.
    if (root / '.git').exists():
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True, timeout=10)
        if result.returncode:
            errors.append('cannot inspect tracked release files')
        else:
            for name in result.stdout.decode('utf-8').split('\0'):
                if name:
                    path = root / name
                    paths.add(path)
                    if any(p in LOCAL_ONLY | PRIVATE_DIRS | {'bin'} for p in Path(name).parts):
                        errors.append(f'{name}: tracked local/private/generated artifact')
    for path in sorted(paths):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            errors.append(f'{rel}: symlinks are not allowed in release sources')
            continue
        if (path.name in PRIVATE_NAMES or path.name == '.env' or path.name.startswith('.env.')
                or path.suffix.lower() in BINARY_SUFFIXES | PRIVATE_SUFFIXES):
            errors.append(f'{rel}: private data, secret, image or compiled/archive artifact')
        try:
            data = path.read_bytes()
            if data.startswith((b'\x7fELF', b'MZ', b'\xfe\xed\xfa', b'\xcf\xfa\xed\xfe')) or b'\0' in data:
                errors.append(f'{rel}: binary content is not publishable')
                continue
            text = data.decode('utf-8')
        except (OSError, UnicodeError) as exc:
            errors.append(f'{rel}: unreadable/non-text release content ({type(exc).__name__})')
            continue
        production = path.suffix.lower() in {'.qml', '.js', '.py'} or path.name == 'qmldir'
        compatibility = path.name == 'migrate.py' or path.name.startswith('test_')
        if production and not compatibility and 'bart.' + 'nova5' in text:
            errors.append(f'{rel}: old plugin ID is only allowed in explicit migration/compatibility code')
        if path.name == 'qmldir':
            if not re.search(r'^singleton SteelSeriesService\s+\S+\s+SteelSeriesService\.qml\s*$', text, re.M):
                errors.append(f'{rel}: expected SteelSeriesService singleton and source file')
            modules = re.findall(r'^module\s+(\S+)', text, re.M)
            if modules and modules != ['SteelSeries']:
                errors.append(f'{rel}: named module must use the SteelSeries namespace')
        for lineno, line in enumerate(text.splitlines(), 1):
            if USER_PATH.search(line):
                errors.append(f'{rel}:{lineno}: absolute user path; use HOME/XDG/TMPDIR instead')
            if SECRET.search(line):
                errors.append(f'{rel}:{lineno}: possible secret (value intentionally not printed)')
    errors.extend(control_errors(root / 'controls.py'))
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1],
                        help='source repository root (default: parent of scripts directory)')
    args = parser.parse_args()
    errors = audit(args.root)
    if errors:
        print('Release audit failed:', file=sys.stderr)
        for error in errors:
            print(f'  - {error}', file=sys.stderr)
        return 1
    print('Release audit passed: metadata, source privacy and non-RGB write allowlists')
    return 0


if __name__ == '__main__':
    sys.exit(main())
