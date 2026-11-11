"""Local preferences only; saving never applies hardware settings."""
import json
import os
from pathlib import Path
import tempfile

DEFAULTS = dict(pollSeconds=5, lowThreshold=20, criticalThreshold=5,
                notifyLow=True, notifyCritical=True, notifyFull=True,
                notifyConnections=True, hiddenIds=[], historyDays=30, experimentalControls=False)


def _path(path):
    return Path(path) if path is not None else Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'omarchy/steelseries/settings.json'


def _validate(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError('Settings must be an object containing known keys only')
    result = {**DEFAULTS, 'hiddenIds': [], **values}
    for key, low, high in (('pollSeconds', 2, 300), ('lowThreshold', 1, 99),
                           ('criticalThreshold', 0, 99), ('historyDays', 30, 30)):
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError(f'{key} must be an integer in {low}..{high}')
    if result['criticalThreshold'] > result['lowThreshold']:
        raise ValueError('criticalThreshold must not exceed lowThreshold')
    for key in ('notifyLow', 'notifyCritical', 'notifyFull', 'notifyConnections', 'experimentalControls'):
        if type(result[key]) is not bool:
            raise ValueError(f'{key} must be a boolean')
    ids = result['hiddenIds']
    if not isinstance(ids, list) or len(ids) > 64 or any(
            not isinstance(value, str) or not 1 <= len(value) <= 256
            or any(ord(char) < 32 for char in value) for value in ids):
        raise ValueError('hiddenIds must contain at most 64 nonempty strings of at most 256 characters')
    result['hiddenIds'] = list(ids)
    return result


def load_config(*, path=None):
    try:
        return _validate(json.loads(_path(path).read_text(encoding='utf-8')))
    except (OSError, ValueError, UnicodeError):
        return _validate({})


def save_config(patch, *, path=None):
    if not isinstance(patch, dict) or set(patch) - set(DEFAULTS):
        raise ValueError('Settings patch must be an object containing known keys only')
    result = _validate({**load_config(path=path), **patch})
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.settings-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result
