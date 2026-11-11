#!/usr/bin/python
"""Explicit-Apply only. Import and capabilities never access hardware."""
from pathlib import Path
import json
import subprocess
import sys
import runtime


def _run(argv, *, timeout, input=None):
    import os
    import signal
    isolated = '--apply-worker' in argv
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, shell=False,
                         start_new_session=isolated)
    try:
        stdout, stderr = p.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            if isolated:
                os.killpg(p.pid, signal.SIGKILL)  # Include any in-flight HeadsetControl child.
            else:
                p.kill()
        except ProcessLookupError:
            pass
        p.communicate()
        raise
    return subprocess.CompletedProcess(argv, p.returncode, stdout, stderr)


def _result(ok, message):
    # None of the exposed settings has an independent hardware getter here.
    return dict(ok=ok, message=str(message)[:500], verified=False, readback={})


def _validate(device, values):
    descriptors = {d['key']: d for d in capabilities(device)}
    if not descriptors:
        raise ValueError('Unsupported device or unavailable backend')
    if type(values) is not dict or not values:
        raise ValueError('Apply requires a nonempty settings object')
    if device.get('control_identity_safe') is False:
        raise ValueError('Physical identity marked unsafe')
    for key, value in values.items():
        if key not in descriptors:
            raise ValueError(f'Unsupported control: {key}')
        d = descriptors[key]
        if type(value) is not int:
            raise ValueError(f'{key} must be an integer (not bool/string/float)')
        if not d['min'] <= value <= d['max'] or (value - d['min']) % d['step']:
            raise ValueError(f'{key} outside supported range/step')
        if d['type'] == 'choice' and value not in [c['value'] for c in d['choices']]:
            raise ValueError(f'{key} is not a supported choice')


def apply(device, values):
    """Call ONLY on an explicit user Apply, under the parent's polling lock.

    Validates the entire payload before starting a bounded isolated worker.
    There are no automatic restore, startup, polling or import writes.
    """
    try:
        _validate(device, values)
        interpreter = str(runtime.mouse_python()) if _pid(device) in MICE else '/usr/bin/python'
        p = _run([interpreter, '-B', str(Path(__file__).resolve()), '--apply-worker'],
                 input=json.dumps(dict(device=device, values=values)), timeout=8)
        if p.returncode:
            raise RuntimeError(p.stderr.strip() or 'Apply worker failed')
        result = json.loads(p.stdout)
        if (type(result) is not dict or type(result.get('ok')) is not bool
                or result.get('verified') is not False or result.get('readback') != {}
                or not isinstance(result.get('message'), str)):
            raise RuntimeError('Invalid backend result')
        return result
    except Exception as exc:
        return _result(False, f'Apply failed; settings may be partially applied: {exc}')


MICE = {'1854': False, '1852': True, '185e': False, '185c': True,
        '1862': False, '1860': True}
HEADSETS = {'2232', '2253'}


def _pid(device):
    if not isinstance(device, dict) or device.get('id_vendor') != '0x1038':
        return None
    value = device.get('id_product', '')
    if not isinstance(value, str) or len(value) != 6 or not value.startswith('0x'):
        return None
    return value[2:] if value[2:] in HEADSETS | MICE.keys() else None


def _integer(key, label, minimum, maximum, step=1, unit=None):
    descriptor = dict(key=key, label=label, type='int', min=minimum, max=maximum,
                      step=step, choices=[])
    if unit:
        descriptor['unit'] = unit
    return descriptor


def _choice(key, label, labels, values):
    return dict(key=key, label=label, type='choice', min=min(values), max=max(values),
                step=1, choices=[dict(label=l, value=v) for l, v in zip(labels, values)])


def capabilities(device):
    """Audited per-model writable subset; no subprocess, HID, or device query."""
    if isinstance(device,dict) and str(device.get('id','')).startswith('steelseries:bluetooth:'):
        return []
    pid = _pid(device)
    headset_ready = False
    if pid in HEADSETS:
        try:
            runtime.headsetcontrol(for_apply=True)  # File/receipt validation only; no device query.
            headset_ready = True
        except ValueError:
            pass
    if headset_ready:
        return [_integer('inactive_time', 'Auto-off (0 = never)', 0, 90, unit='min'),
                _choice('equalizer_preset', 'Equalizer preset', ['Flat', 'Bass', 'Focus', 'Smiley'], [0, 1, 2, 3]),
                _integer('sidetone', 'Microphone sidetone (0 = off)', 0, 128)]
    if pid in MICE and runtime.mouse_python().is_file():
        return [_integer('dpi', 'DPI (replaces all presets with one)', 100, 18000, 100, 'DPI'),
                _choice('polling_rate', 'Polling rate (Hz)', ['125', '250', '500', '1000'], [125, 250, 500, 1000]),
                _integer('sleep_timer', 'Sleep timer (0 = never)', 0, 20, unit='min')]
    return []


def _mouse_path(physical, hid_root=Path('/sys/class/hidraw')):
    physical = physical.resolve()
    matches = []
    for node in hid_root.glob('hidraw*'):
        target = (node / 'device').resolve()
        if physical not in target.parents:
            continue
        for parent in (target, *target.parents):
            if parent == physical:
                break
            if _read(parent / 'bInterfaceNumber') == '03':
                matches.append(str(Path('/dev') / node.name).encode())
                break
    if len(matches) != 1:
        raise ValueError('Expected exactly one HID interface 3 on the selected physical USB device')
    return matches[0]


class _MemorySettings:
    """Do not read/write rivalcfg's global VID/PID settings cache."""
    def set(self, *args):
        pass

    def save(self):
        pass


class _CheckedHID:
    """Defence in depth: only allow the three requested protocol commands + save."""
    def __init__(self, raw, wireless):
        self.raw = raw
        self.closed = False
        flag = 0x40 if wireless else 0
        self.allowed = {x | flag for x in (0x2d, 0x2b, 0x29, 0x11)}

    def write(self, data):
        if len(data) < 2 or data[0] != 0 or data[1] not in self.allowed:
            raise ValueError('Backend attempted an unapproved HID command')
        count = self.raw.write(data)
        if count != len(data):
            raise OSError('Short HID write')
        return count

    def read(self, length, timeout_ms=200):
        return self.raw.read(length, timeout_ms=min(timeout_ms, 200))

    def close(self):
        if not self.closed:
            self.closed = True
            self.raw.close()


def _apply_mouse(device, values, physical, hid_factory=None):
    from importlib.metadata import version
    from rivalcfg import devices
    from rivalcfg.mouse import Mouse
    from copy import deepcopy
    _validate(device, values)
    if version('rivalcfg') != '4.17.0':
        raise ValueError('Re-audit backend before using a different rivalcfg version')
    pid = _pid(device)
    if pid not in MICE:
        raise ValueError('Unsupported mouse')
    wireless = MICE[pid]
    profile = deepcopy(devices.get_profile(0x1038, int(pid, 16)))
    names = {'dpi': 'sensitivity', 'polling_rate': 'polling_rate', 'sleep_timer': 'sleep_timer'}
    commands = {'dpi': 0x2d, 'polling_rate': 0x2b, 'sleep_timer': 0x29}
    flag = 0x40 if wireless else 0
    if profile.get('endpoint') != 3 or profile['save_command']['command'] != [0x11 | flag, 0]:
        raise ValueError('Unexpected rivalcfg endpoint/save command')
    for key in values:
        if profile['settings'][names[key]]['command'] != [commands[key] | flag]:
            raise ValueError('Unexpected rivalcfg setting command')
    # Strip unrelated settings entirely: no reset/default/lighting APIs are used.
    profile['settings'] = {names[k]: profile['settings'][names[k]] for k in values}
    path = _mouse_path(physical)
    if hid_factory is None:
        import hid
        hid_factory = hid.device
    raw = hid_factory()
    checked = _CheckedHID(raw, wireless)
    try:
        raw.open_path(path)  # Never hid.open(VID, PID): multiple identical mice are safe.
        mouse = Mouse(checked, profile, _MemorySettings())
        for key, value in values.items():
            reply = getattr(mouse, 'set_' + names[key])(value)
            if wireless and not reply:
                raise OSError('No receiver response; mouse may be asleep/offline')
        reply = mouse.save()
        if wireless and not reply:
            raise OSError('No receiver response to save')
        return _result(True, 'Applied/unverified: writes completed; receiver responses are not independent setting readback')
    finally:
        checked.close()


def _read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def _resolve_physical(device, root=Path('/sys/bus/usb/devices')):
    """Re-enumerate USB devices immediately before opening; never trust a PID alone."""
    pid = _pid(device)
    if pid is None or device.get('control_identity_safe') is False:
        raise ValueError('Unsupported or unsafe physical identity')
    candidates = [p.resolve() for p in root.iterdir() if ':' not in p.name
                  and _read(p / 'idVendor') == '1038' and _read(p / 'idProduct') == pid]
    if pid in HEADSETS and len(candidates) != 1:
        raise ValueError('Ambiguous/missing headset: CLI selects only VID:PID, not physical path')
    identity = device.get('id', '')
    if not isinstance(identity, str):
        raise ValueError('Missing fleet identity')
    fields = identity.split(':', 3)
    if len(fields) != 4 or fields[0] != 'steelseries' or not fields[3]:
        raise ValueError('Missing exact fleet serial/port identity')
    if fields[2] == 'port':
        matches = [p for p in candidates if p.name == fields[3]]
    elif fields[2] == 'serial':
        matches = [p for p in candidates if _read(p / 'serial') == fields[3]]
    else:
        matches = []
    if len(matches) != 1:
        raise ValueError('Selected physical USB device disappeared or is ambiguous')
    if device.get('_path') and Path(device['_path']).resolve() != matches[0]:
        raise ValueError('USB path disagrees with selected identity')
    return matches[0]


def _execute(device, values):
    """Worker implementation; tests inject resolver and transports, never hardware."""
    try:
        _validate(device, values)
        physical = _resolve_physical(device)
        pid = _pid(device)
        if pid in MICE:
            return _apply_mouse(device, values, physical)
        binary = runtime.headsetcontrol(for_apply=True)
        argv = [str(binary), '--device', f'1038:{pid}', '--timeout', '700', '--output', 'json']
        options = {'inactive_time': ('--inactive-time', 'CAP_INACTIVE_TIME'),
                   'equalizer_preset': ('--equalizer-preset', 'CAP_EQUALIZER_PRESET'),
                   'sidetone': ('--sidetone', 'CAP_SIDETONE')}
        for key, value in values.items():
            argv.extend([options[key][0], str(value)])
        p = _run(argv, timeout=4)
        if p.returncode:
            raise RuntimeError(p.stderr.strip() or 'HeadsetControl failed')
        payload = json.loads(p.stdout)
        entries = payload.get('devices', [])
        if len(entries) != 1:
            raise RuntimeError('HeadsetControl returned missing/ambiguous device')
        entry = entries[0]
        if (entry.get('id_vendor') != '0x1038' or entry.get('id_product') != '0x' + pid
                or entry.get('status') != 'success' or entry.get('errors')):
            raise RuntimeError('HeadsetControl target/status mismatch')
        for key in values:
            actions = [a for a in payload.get('actions', []) if a.get('capability') == options[key][1]]
            if len(actions) != 1 or actions[0].get('status') != 'success':
                raise RuntimeError(f'No successful action reported for {key}')
        return _result(True, 'Applied/unverified: backend accepted settings; no independent setting readback is available')
    except Exception as exc:
        return _result(False, f'Apply failed; settings may be partially applied: {exc}')


if __name__ == '__main__':
    if sys.argv[1:] != ['--apply-worker']:
        print(json.dumps(_result(False, 'Only the explicit Apply worker is supported')))
        sys.exit(2)
    try:
        request = json.loads(sys.stdin.read(16384))
        result = _execute(request['device'], request['values'])
    except Exception as exc:
        result = _result(False, f'Apply failed: {exc}')
    print(json.dumps(result))
