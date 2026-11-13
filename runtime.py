"""Dependency locations and provenance; importing never installs or queries hardware."""
import os
import hashlib
import json
from pathlib import Path

HEADSET_COMMIT = '0c8a76fa019cd02263a1c69e00e18e229b16d87f'
HEADSET_ARCHIVE_SHA256 = '4215cef92588422eb326390be11e1f5308e98b35a551e187f17c3eed1c199402'
HEADSET_URL = f'https://codeload.github.com/Sapd/HeadsetControl/tar.gz/{HEADSET_COMMIT}'
HEADSET_PATCH_SHA256 = 'f4f3064a677fbaa205bf62e28440a3f999e3b77fa43d5928b3d1d3227c4b7151'
HEADSET_BUILD_REVISION = HEADSET_COMMIT + '-zero-padding-v1'


def data_dir():
    value = os.environ.get('XDG_DATA_HOME', '')
    base = Path(value) if value and Path(value).is_absolute() else Path.home() / '.local/share'
    return base / 'omarchy-steelseries'


def headset_dir():
    return data_dir() / 'headsetcontrol' / HEADSET_BUILD_REVISION


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def headsetcontrol(*, for_apply=False):
    """Use only this user's checksum-receipted, patched build, including polling.

    Older cached executables and unverified PATH tools are never fallback choices.
    This detects accidental replacement, not tampering by the owning user (who
    controls both executable and receipt). It is not a signature scheme.
    """
    binary = headset_dir() / 'bin/headsetcontrol'
    try:
        receipt = json.loads((headset_dir() / 'receipt.json').read_text())
        if (not binary.is_file() or not os.access(binary, os.X_OK)
                or receipt['source_commit'] != HEADSET_COMMIT
                or receipt['source_archive_sha256'] != HEADSET_ARCHIVE_SHA256
                or receipt['patch_sha256'] != HEADSET_PATCH_SHA256
                or receipt['binary_sha256'] != sha256_file(binary)):
            raise ValueError('Patched HeadsetControl receipt/checksum mismatch')
    except (OSError, KeyError, TypeError, ValueError) as exc:
        if for_apply:
            raise ValueError('Run setup.py --headsetcontrol: patched build receipt required for Apply') from exc
        return None
    return binary


def compatible_hid_path(physical, product_id, hidraw_path, *, hid_module=None):
    """Resolve this exact interface in either Linux hidraw or libusb HIDAPI.

    PyPI wheels can use libusb paths such as 7-1.3:1.3, while the system
    binding uses /dev/hidrawN. Never substitute the first matching VID/PID.
    """
    if hid_module is None:
        import hid as hid_module
    physical=Path(physical).resolve()
    allowed={hidraw_path if isinstance(hidraw_path,bytes) else os.fsencode(hidraw_path)}
    for interface in physical.iterdir():
        try:
            if interface.is_dir() and interface.parent.resolve()==physical and (interface/'bInterfaceNumber').read_text().strip()=='03':
                allowed.add(os.fsencode(interface.name))
        except OSError:
            continue
    matches=[entry['path'] for entry in hid_module.enumerate(0x1038,product_id)
             if entry.get('interface_number')==3 and entry.get('path') in allowed]
    if len(matches)!=1:
        raise OSError('No unique HIDAPI path for the exact physical Aerox interface')
    return matches[0]


def mouse_python():
    return data_dir() / 'venv/bin/python'
