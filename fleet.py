#!/usr/bin/python
"""Read-only SteelSeries USB fleet discovery and battery telemetry."""
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import signal
import time
import re
import runtime

AEROX = {'1854': ('aerox5', False), '1852': ('aerox5', True),
         '185e': ('aerox5-destiny2', False), '185c': ('aerox5-destiny2', True),
         '1862': ('aerox5-diablo4', False), '1860': ('aerox5-diablo4', True)}


def bluetooth_devices(managed, upower=()):
    """Normalize only positively identified, paired SteelSeries BlueZ objects."""
    devices = []
    for path, interfaces in managed.items():
        props = interfaces.get('org.bluez.Device1', {})
        address = str(props.get('Address', ''))
        if not props.get('Paired') or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', address):
            continue
        name = str(props.get('Name') or props.get('Alias') or '')
        alias = str(props.get('Modalias', ''))
        manufacturer = props.get('ManufacturerData', {})
        vendor = any(int(key) == 0x1038 for key in manufacturer)
        vendor = vendor or bool(re.match(r'^(?:usb|bluetooth):v(?:0000)?1038(?:p|$)', alias, re.I))
        if not vendor and not re.search(r'\b(?:SteelSeries|Arctis|Aerox|Apex)\b', name, re.I):
            continue
        name = name or 'SteelSeries Bluetooth'
        lower = name.lower()
        kind = ('headset' if 'arctis' in lower else 'mouse' if 'aerox' in lower else
                'keyboard' if 'apex' in lower else 'device')
        connected = bool(props['Connected']) if 'Connected' in props else None
        battery_props = interfaces.get('org.bluez.Battery1')
        level = battery_props.get('Percentage') if battery_props is not None else None
        valid = isinstance(level, (int, float)) and not isinstance(level, bool) and 0 <= level <= 100
        matches = [u for u in upower if u.get('IsPresent') and not u.get('PowerSupply') and
                   (str(u.get('Serial', '')).lower() == address.lower() or u.get('NativePath') == path)]
        power = matches[0] if len(matches) == 1 else {}
        charging_known = connected is True and power.get('State') in (1, 2, 4)
        if not valid and power:
            level = power.get('Percentage')
            valid = isinstance(level, (int, float)) and not isinstance(level, bool) and 0 <= level <= 100
        pid = re.search(r'p(?:0000)?([0-9a-f]{4})(?:d|$)', alias, re.I)
        devices.append(dict(id='steelseries:bluetooth:' + address.lower(), name=name, kind=kind,
                            state='connected' if connected is True else 'offline' if connected is False else 'unknown',
                            battery=int(level) if valid and connected is True else -1,
                            charging=charging_known and power.get('State') == 1, wireless=True, transport='bluetooth',
                            battery_supported=battery_props is not None or bool(power),
                            battery_capability='supported' if battery_props is not None or power else 'unknown',
                            charging_known=charging_known, bluetooth_address=address.lower(),
                            error='' if valid or connected is False else 'Bluetooth battery unavailable',
                            id_vendor='0x1038', id_product='0x' + pid[1].lower() if pid else ''))
    return devices


def identity_tokens(device):
    tokens = set()
    for key in ('serial', 'bluetooth_address'):
        value = str(device.get(key, '')).strip()
        if not value or value.lower() in ('unknown', 'none', 'default', '0') or not value.strip('0:-'):
            continue
        if re.fullmatch(r'(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', value):
            tokens.add(('mac', value.lower().replace('-', ':')))
        elif key == 'serial':
            tokens.add(('serial', value))
    return tokens


def merge_devices(usb, bluetooth):
    """Conservative one-to-one merge: never match on model, PID or name."""
    result = [dict(device) for device in usb]
    usb_tokens = [identity_tokens(d) for d in usb]
    bt_tokens = [identity_tokens(d) for d in bluetooth]
    candidates = [[i for i, tokens in enumerate(usb_tokens) if tokens & bt]
                  for bt in bt_tokens]
    for index, device in enumerate(bluetooth):
        matches = candidates[index]
        if len(matches) != 1 or sum(matches[0] in other for other in candidates) != 1:
            result.append(dict(device))
            continue
        target = result[matches[0]]
        # Keep USB identity stable; select an actually connected telemetry source.
        if device['state'] == 'connected' and (target['state'] != 'connected' or
                                              (target['battery'] < 0 <= device['battery'])):
            for key in ('state', 'battery', 'charging', 'error', 'transport', 'charging_known'):
                if key in device:
                    target[key] = device[key]
        target['bluetooth_address'] = device['bluetooth_address']
        target['battery_supported'] = target['battery_supported'] or device['battery_supported']
        target['transports'] = list(dict.fromkeys([usb[matches[0]]['transport'], 'bluetooth']))
        target['transport_states'] = {usb[matches[0]]['transport']: usb[matches[0]]['state'],
                                      'bluetooth': device['state']}
    return result


def collect_all(usb_reader=None, bluetooth_reader=None):
    """USB and known Bluetooth inventory, concurrently, with bounded workers.

    Reader injection is for offline tests; production uses killed subprocesses,
    keeping hung HID, sysfs or system bus operations outside the parent process.
    """
    errors = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        usb_future = executor.submit(usb_reader or query_usb)
        bt_future = executor.submit(bluetooth_reader or read_bluetooth)
        try:
            usb = usb_future.result()['devices']
        except Exception as exc:
            errors['usb'] = f'{type(exc).__name__}: {exc}'[:240]
            usb = []
        try:
            bluetooth = bt_future.result()
        except Exception as exc:
            errors['bluetooth'] = f'{type(exc).__name__}: {exc}'[:240]
            bluetooth = []
    collect_all.last_errors = errors
    return dict(devices=merge_devices(usb, bluetooth), updated=int(time.time()))


collect_all.last_errors = {}


def system_bluetooth():
    """Read BlueZ and identity-checked UPower properties, never discover/connect."""
    import dbus
    bus = dbus.SystemBus(private=True)
    deadline = time.monotonic() + 1.0
    try:
        manager = dbus.Interface(bus.get_object('org.bluez', '/', introspect=False),
                                 'org.freedesktop.DBus.ObjectManager')
        for attempt in range(2):
            try:
                managed = manager.GetManagedObjects(timeout=0.35)
                break
            except Exception as exc:
                name = getattr(exc, 'get_dbus_name', lambda: '')()
                if attempt or name not in ('org.freedesktop.DBus.Error.NoReply',
                                           'org.freedesktop.DBus.Error.Timeout',
                                           'org.freedesktop.DBus.Error.Disconnected'):
                    raise
        # Do not even query UPower if there is no relevant paired hardware.
        devices = bluetooth_devices(managed)
        if not devices:
            return []
        powers = []
        try:
            upower = dbus.Interface(bus.get_object('org.freedesktop.UPower',
                                    '/org/freedesktop/UPower', introspect=False), 'org.freedesktop.UPower')
            paths = upower.EnumerateDevices(timeout=min(0.2, max(0.001, deadline - time.monotonic())))
            for path in paths:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    props = dbus.Interface(bus.get_object('org.freedesktop.UPower', path, introspect=False),
                                           'org.freedesktop.DBus.Properties')
                    powers.append(props.GetAll('org.freedesktop.UPower.Device', timeout=min(0.15, remaining)))
                except Exception:
                    continue
        except Exception:
            pass  # UPower is optional; BlueZ's connection/battery evidence remains valid.
        return bluetooth_devices(managed, powers)
    finally:
        bus.close()


def query_usb():
    process = subprocess.run(['/usr/bin/python', '-B', str(Path(__file__).resolve()), '--usb-all'],
                             capture_output=True, text=True, timeout=3.8)
    if process.returncode:
        raise RuntimeError(process.stderr.strip()[:240] or 'USB inventory worker failed')
    return json.loads(process.stdout)


def read_bluetooth():
    process = subprocess.run(['/usr/bin/python', '-B', str(Path(__file__).resolve()), '--bluetooth'],
                             capture_output=True, text=True, timeout=1.5)
    if process.returncode:
        raise RuntimeError(process.stderr.strip()[:240] or 'Bluetooth inventory worker failed')
    return json.loads(process.stdout)


def failure(message):
    return dict(state='error', battery=-1, charging=False, error=str(message)[:240])


def collect(root=Path('/sys/bus/usb/devices'), headset_reader=None, mouse_reader=None, *, include_identity=False):
    devices = discover(root)
    if not devices:
        return dict(devices=[], updated=int(time.time()))
    pid_counts = Counter(d['_pid'] for d in devices)
    serial_counts = Counter((AEROX.get(d['_pid'], (d['_pid'],))[0], d['_serial']) for d in devices if d['_serial'])
    for d in devices:
        family = AEROX.get(d['_pid'], (d['_pid'],))[0]
        identity = ('serial:' + d['_serial'] if d['_serial'] and serial_counts[family, d['_serial']] == 1
                    else 'port:' + Path(d['_path']).name)
        d['id'] = f'steelseries:{family}:{identity}'
        if include_identity and d['_serial'] and serial_counts[family, d['_serial']] == 1:
            d['serial'] = d['_serial']
        if d['_pid'] in AEROX:
            d.update(kind='mouse', wireless=True, battery_supported=True,
                     transport='wireless' if AEROX[d['_pid']][1] else 'usb')
        elif d['_pid'] == '2232':
            d.update(wireless=True, transport='wireless', battery_supported=True)
    with ThreadPoolExecutor(max_workers=max(1, len(devices) + 1)) as executor:
        headset_future = executor.submit(headset_reader or read_headsets)
        mice = {d['id']: executor.submit(mouse_reader or query_mouse, d) for d in devices if d['_pid'] in AEROX}
        try:
            payload = headset_future.result()
            entries = payload.get('devices', [])
        except Exception as exc:
            entries = []
            for d in devices:
                if d['kind'] == 'headset':
                    d.update(failure(f'HeadsetControl: {exc}'))
        for d in devices:
            if d['id'] in mice:
                try:
                    d.update(mice[d['id']].result())
                except Exception as exc:
                    d.update(failure(exc))
                continue
            matches = [e for e in entries if str(e.get('id_vendor', '')).lower() == '0x1038'
                       and str(e.get('id_product', '')).lower() == '0x' + d['_pid']]
            if not matches:
                if d['battery_supported'] and d['state'] != 'error':
                    d.update(failure('HeadsetControl did not report this attached battery-capable device'))
                continue
            entry = matches[0]
            supported = 'CAP_BATTERY_STATUS' in entry.get('capabilities', []) or 'battery' in entry
            d.update(kind='headset', battery_supported=supported)
            if not supported:
                continue
            if pid_counts[d['_pid']] > 1 or len(matches) > 1:
                d.update(failure('Ambiguous identical headsets: HeadsetControl exposes no physical USB path'))
                continue
            battery = entry.get('battery', {})
            level, status = battery.get('level'), battery.get('status')
            if status in ('BATTERY_AVAILABLE', 'BATTERY_CHARGING') and type(level) is int and 0 <= level <= 100:
                d.update(state='connected', battery=level, charging=status == 'BATTERY_CHARGING', error='')
            else:
                error = str(entry.get('errors', {}).get('battery', status or 'Battery unavailable'))
                d.update(failure(error))
                if re.match(r'^device is offline\b', error.strip(), re.I):
                    d['state'] = 'offline'
    return dict(devices=[{k: v for k, v in d.items() if not k.startswith('_')} for d in devices], updated=int(time.time()))



def read_headsets():
    binary = runtime.headsetcontrol()
    if binary is None:
        raise FileNotFoundError('HeadsetControl unavailable; run setup.py --headsetcontrol')
    for attempt in range(2):
        try:
            process = subprocess.run([str(binary), '-b', '-o', 'json'],
                                     capture_output=True, text=True, timeout=1.2)
            # Nonzero may still contain useful per-device offline/error JSON.
            return json.loads(process.stdout)
        except subprocess.TimeoutExpired:
            if attempt:
                raise


def mouse_hid_path(physical, hid_root=Path('/sys/class/hidraw')):
    physical = Path(physical).resolve()
    paths = []
    for node in Path(hid_root).glob('hidraw*'):
        target = (node / 'device').resolve()
        if physical not in target.parents:
            continue
        for parent in (target, *target.parents):
            if parent == physical:
                break
            if read_text(parent / 'bInterfaceNumber') == '03':
                paths.append(str(Path('/dev') / node.name).encode())
                break
    if len(paths) != 1:
        raise OSError(f'Expected one Aerox interface 3, found {len(paths)}')
    return paths[0]


def query_mouse(device):
    # Repeat only a timed-out/no-response telemetry read, never permissions or
    # malformed protocol replies. Each attempt has its own hard process bound.
    for attempt in range(2):
        try:
            interpreter = str(runtime.mouse_python()) if runtime.mouse_python().is_file() else '/usr/bin/python'
            process = subprocess.run([interpreter, '-B', str(Path(__file__).resolve()), '--aerox',
                                      device['_path'], device['_pid']],
                                     capture_output=True, text=True, timeout=0.9)
            if process.returncode:
                raise RuntimeError(process.stderr.strip()[:240] or 'Aerox worker failed')
            result = json.loads(process.stdout)
            if attempt == 0 and result.get('state') == 'unknown':
                continue
            return result
        except subprocess.TimeoutExpired:
            if attempt:
                raise


def read_text(path):
    # USB string-descriptor sysfs reads may block on the hub lock during hotplug.
    # Discovery and mouse worker discovery both run on their process main thread.
    def expired(signum, frame):
        raise TimeoutError('USB sysfs attribute read timed out')
    previous = signal.signal(signal.SIGALRM, expired)
    timer = signal.setitimer(signal.ITIMER_REAL, 0.1)
    started = time.monotonic()
    try:
        return path.read_text().strip()
    except OSError:
        return ''
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(0.000001, timer[0] - (time.monotonic() - started)), timer[1])


def discover(root=Path('/sys/bus/usb/devices')):
    devices = []
    for path in sorted(Path(root).iterdir()):
        if ':' in path.name or read_text(path / 'idVendor').lower() != '1038':
            continue
        pid = read_text(path / 'idProduct').lower()
        fallback = {'1620': 'SteelSeries Apex 9 Mini', '150d': 'SteelSeries QCK Prism Cloth',
                    '2232': 'SteelSeries Arctis Nova 5'}
        if pid in AEROX:
            fallback[pid] = 'SteelSeries Aerox 5 Wireless'
        name = read_text(path / 'product') or fallback.get(pid, f'SteelSeries USB {pid}')
        lower = name.lower()
        kind = ('mousepad' if 'qck' in lower or 'mousepad' in lower else
                'keyboard' if 'apex' in lower else
                'headset' if 'arctis' in lower else
                'mouse' if any(s in lower for s in ('aerox', 'rival', 'sensei', 'prime')) else 'device')
        devices.append(dict(id=f'steelseries:{pid}:port:{path.name}', name=name,
                            kind=kind, state='connected', battery=-1, charging=False,
                            wireless=False, battery_supported=False, transport='usb', error='',
                            id_vendor='0x1038', id_product='0x' + pid,
                            _pid=pid, _path=str(path.resolve()), _serial=read_text(path / 'serial')))
    return devices


def decode_aerox(data):
    # Rivalcfg aerox5_wireless_wired.py: charging bit 7; 5% steps, offset 1.
    result = dict(state='error', battery=-1, charging=False, error='Invalid Aerox battery response')
    if not data:
        result.update(state='unknown', error='Aerox battery query timed out (asleep/offline or no response; unconfirmed)')
    elif len(data) == 2 and data[0] in (0x92, 0xd2):
        level = ((data[1] & 0x7f) - 1) * 5
        if 0 <= level <= 100:
            result.update(state='connected', battery=level, charging=bool(data[1] & 0x80), error='')
    return result


def read_aerox(path, wireless=False, factory=None):
    if factory is None:
        import hid
        factory = hid.device
    device = factory()
    try:
        device.open_path(path)
        command = bytes([0, 0xd2 if wireless else 0x92])
        if device.write(command) != len(command):
            raise OSError('Short HID battery-query write')
        import time
        time.sleep(0.05)  # Match rivalcfg minimum command settling delay.
        return decode_aerox(device.read(2, timeout_ms=200))
    finally:
        device.close()


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--aerox':
        try:
            result = read_aerox(mouse_hid_path(sys.argv[2]), AEROX[sys.argv[3]][1])
        except Exception as exc:
            result = failure(f'{type(exc).__name__}: {exc}')
    elif sys.argv[1:] == ['--bluetooth']:
        try:
            result = system_bluetooth()
        except Exception as exc:
            print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
            sys.exit(1)
    elif sys.argv[1:] == ['--usb-all']:
        result = collect(include_identity=True)
    elif sys.argv[1:] == ['--all']:
        result = collect_all()
    else:
        result = collect()
    print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
