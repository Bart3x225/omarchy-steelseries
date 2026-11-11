"""Read-only HeadsetControl adapter for the Nova 5 bar widget."""
import json
from pathlib import Path
import runtime
import subprocess
import time


def normalize(payload):
    result = dict(state='absent', battery=-1, charging=False, error='', chatmix=-1, sidetone=-1)
    for device in payload.get('devices', []):
        if device.get('id_vendor') != '0x1038' or device.get('id_product') != '0x2232':
            continue
        battery = device.get('battery', {})
        level = battery.get('level', -1)
        if battery.get('status') in ('BATTERY_AVAILABLE', 'BATTERY_CHARGING') and type(level) is int and 0 <= level <= 100:
            result.update(state='connected', battery=level, charging=battery['status'] == 'BATTERY_CHARGING')
        else:
            error = str(device.get('errors', {}).get('battery', 'Battery unavailable'))
            result.update(state='offline' if 'offline' in error.lower() else 'error', error=error[:240])
        for key, value in [('chatmix', device.get('chatmix')), ('sidetone', device.get('sidetone', {}).get('level'))]:
            if type(value) is int and 0 <= value <= 128:
                result[key] = value
        return result
    return result


if __name__ == '__main__':
    try:
        binary = runtime.headsetcontrol()
        if binary is None:
            raise FileNotFoundError('HeadsetControl unavailable; run setup.py --headsetcontrol')
        process = subprocess.run([str(binary), '-b', '-o', 'json'], capture_output=True, text=True, timeout=6)
        status = normalize(json.loads(process.stdout))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        status = dict(state='error', battery=-1, charging=False, error=type(error).__name__, chatmix=-1, sidetone=-1)
    status['updated'] = int(time.time())
    print(json.dumps(status, ensure_ascii=True))
