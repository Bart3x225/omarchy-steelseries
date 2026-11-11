#!/usr/bin/env python3
"""Explicit legacy-ID migration. Dry-run by default; never touches telemetry."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid

OLD='bart.nova5'
NEW='bart.steelseries'


def _replace(value):
    if isinstance(value,dict):return {k:_replace(v) for k,v in value.items()}
    if isinstance(value,list):return [_replace(v) for v in value]
    return NEW if value==OLD else value


def migrate(config_root=None, *, apply=False, backup_root=None):
    root=Path(config_root) if config_root is not None else Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')
    plugins=root/'omarchy/plugins';canonical=plugins/NEW;old=plugins/OLD;shell=root/'omarchy/shell.json'
    try:
        manifest=json.loads((canonical/'manifest.json').read_text())
    except (OSError,ValueError) as exc:raise ValueError('Install the canonical bart.steelseries plugin before migration') from exc
    if manifest.get('id')!=NEW:raise ValueError('Canonical plugin manifest ID mismatch')
    original=json.loads(shell.read_text()) if shell.exists() else {}
    if not isinstance(original,dict):raise ValueError('Shell config must be an object')
    replacement=_replace(original)
    changed=replacement!=original or old.exists()
    result={'changed':changed,'applied':bool(apply and changed),'old':str(old),'new':str(canonical)}
    if not apply or not changed:return result
    backups=Path(backup_root) if backup_root is not None else Path(os.environ.get('XDG_STATE_HOME') or Path.home()/'.local/state')/'omarchy/steelseries/migrations'
    backup=backups/(str(int(time.time()))+'-'+uuid.uuid4().hex[:8]);backup.mkdir(parents=True,mode=0o700)
    if shell.exists():shutil.copy2(shell,backup/'shell.json')
    else:(backup/'shell.json').write_text('{}\n')
    shell.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.steelseries-migrate-',dir=shell.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(replacement,stream,indent=2,ensure_ascii=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(name,shell)
    finally:
        if os.path.exists(name):os.unlink(name)
    if json.loads(shell.read_text())!=replacement:raise RuntimeError('Config readback failed')
    if old.exists():shutil.move(str(old),str(backup/OLD))
    result['backup']=str(backup)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--config-root',type=Path);parser.add_argument('--backup-root',type=Path)
    args=parser.parse_args()
    try:print(json.dumps(migrate(args.config_root,apply=args.apply,backup_root=args.backup_root),indent=2))
    except (OSError,ValueError,RuntimeError) as exc:parser.exit(1,str(exc)+'\n')

if __name__=='__main__':main()
