#!/usr/bin/python
"""Serialized application API. Hardware changes exist only in explicit apply."""
import json
import os
from pathlib import Path
import sys
import fcntl


def validate_command(command):
    return command in ('snapshot','save-settings','apply')


def execute_command(command, arguments):
    if not validate_command(command):
        raise ValueError('Unknown command')
    import prefs
    if command=='save-settings':
        if len(arguments)!=1: raise ValueError('One settings object required')
        patch=json.loads(arguments[0])
        if not isinstance(patch,dict): raise ValueError('Settings must be an object')
        return dict(ok=True,config=prefs.save_config(patch))
    if command=='snapshot' and arguments:
        raise ValueError('Snapshot takes no arguments')
    values=None
    if command=='apply':
        if len(arguments)!=2: raise ValueError('Device ID and values required')
        values=json.loads(arguments[1])
        if not isinstance(values,dict) or not values or len(values)>20: raise ValueError('Nonempty control values required')
        if not prefs.load_config().get('experimentalControls',False): raise ValueError('Experimental hardware controls are disabled; opt in through Settings first')
    import fleet
    snapshot=fleet.collect_all()
    snapshot['source_errors']=dict(getattr(fleet.collect_all,'last_errors',{}))
    import controls
    if command=='apply':
        devices=[d for d in snapshot['devices'] if d['id']==arguments[0]]
        if len(devices)!=1: raise ValueError('Device is no longer uniquely available')
        if devices[0]['state']!='connected': raise ValueError('Device is not connected')
        return controls.apply(devices[0],values)
    import history
    snapshot['config']=prefs.load_config()
    histories=history.record_and_summarize(snapshot['devices'],now=snapshot['updated'])
    for device in snapshot['devices']:
        device['history']=histories.get(device['id'],dict(points=[],estimateMinutes=-1,estimateSamples=0))
        device['controls']=controls.capabilities(device) if snapshot['config'].get('experimentalControls',False) else []
    return snapshot


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    try:
        if not args or not validate_command(args[0]): raise ValueError('Unknown command')
        if sum(len(a) for a in args)>16384: raise ValueError('Request too large')
        runtime=Path(os.environ.get('XDG_RUNTIME_DIR',str(Path.home()/'.cache')))/'omarchy-steelseries'
        runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
        with (runtime/'device.lock').open('a') as lock:
            os.chmod(runtime/'device.lock',0o600)
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=execute_command(args[0],args[1:])
    except BlockingIOError:
        result=dict(ok=False,error='Device operation already running')
    except Exception as exc:
        result=dict(ok=False,error=str(exc)[:400])
    print(json.dumps(result,ensure_ascii=True,separators=(',',':')))

if __name__=='__main__': main()
