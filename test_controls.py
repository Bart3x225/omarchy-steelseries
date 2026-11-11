"""Safe controls tests: all Apply operations use injected transports."""
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import controls

NOVA = dict(id='steelseries:2232:port:1-2', id_vendor='0x1038', id_product='0x2232')
MOUSE = dict(id='steelseries:aerox5:port:1-3', id_vendor='0x1038', id_product='0x1852')


class ControlsTests(unittest.TestCase):
    def setUp(self):
        # Runtime discovery/provenance has its own real-file tests. Here provide
        # only dependency locations; all execution/HID paths remain injected.
        for target, name, kwargs in [
                (controls.runtime, 'headsetcontrol', {'return_value': Path('/fake/runtime/headsetcontrol')}),
                (controls.runtime, 'mouse_python', {'return_value': Path(sys.executable)}),
                (controls.subprocess, 'Popen', {'side_effect': AssertionError('uninjected control subprocess')})]:
            patcher = patch.object(target, name, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_capabilities_are_pure_and_model_scoped(self):
        with patch('subprocess.Popen', side_effect=AssertionError('unexpected subprocess')):
            nova = controls.capabilities(NOVA)
            self.assertEqual([d['key'] for d in nova], ['inactive_time', 'equalizer_preset', 'sidetone'])
            self.assertEqual(controls.capabilities(dict(NOVA, id_product='0x9999')), [])
            self.assertEqual(controls.capabilities(dict(NOVA, id_vendor='0xffff')), [])
            self.assertEqual(controls.capabilities(None), [])
            self.assertEqual(controls.capabilities(dict(NOVA,id='steelseries:bluetooth:aa:bb:cc:dd:ee:ff',transport='bluetooth')), [])
            self.assertEqual(nova[1]['choices'][1], {'label': 'Bass', 'value': 1})
            self.assertEqual(nova[2]['max'], 128)
            self.assertFalse(any('light' in d['key'] or 'rgb' in d['key'] for d in nova))

    def test_validation_rejects_entire_payload_before_starting_worker(self):
        bad = [{}, None, [], {'sidetone': 129}, {'inactive_time': True}, {'inactive_time': '2'},
               {'inactive_time': 91}, {'equalizer_preset': 4}, {'inactive_time': 2, 'light': 1}]
        with patch.object(controls, '_run', side_effect=AssertionError('must not execute')):
            for values in bad:
                result = controls.apply(NOVA, values)
                self.assertFalse(result['ok'], values)
                self.assertFalse(result['verified'])
                self.assertEqual(result['readback'], {})
            for values in [{'dpi': 150}, {'dpi': 0}, {'polling_rate': 200}, {'sleep_timer': 21}]:
                self.assertFalse(controls.apply(MOUSE, values)['ok'])
            self.assertFalse(controls.apply(dict(NOVA, id_product='0x9999'), {'inactive_time': 1})['ok'])

    def test_apply_uses_bounded_worker_and_does_not_invent_readback(self):
        import json
        from types import SimpleNamespace
        response = dict(ok=True, message='Applied/unverified', verified=False, readback={})
        with patch.object(controls, '_run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr='')) as run:
            self.assertEqual(controls.apply(NOVA, {'inactive_time': 5}), response)
            args, kwargs = run.call_args
            self.assertIn('--apply-worker', args[0])
            self.assertEqual(kwargs['timeout'], 8)
            self.assertEqual(json.loads(kwargs['input'])['values'], {'inactive_time': 5})

    def test_identity_matches_exact_serial_or_usb_port_and_blocks_duplicate_headsets(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for port, pid, serial in [('1-2', '2232', 'nova'), ('1-3', '1852', 'mouse')]:
                p = root / port
                p.mkdir()
                for name, text in [('idVendor', '1038'), ('idProduct', pid), ('serial', serial)]:
                    (p / name).write_text(text)
            self.assertEqual(controls._resolve_physical(NOVA, root), root / '1-2')
            serial_device = dict(MOUSE, id='steelseries:aerox5:serial:mouse')
            self.assertEqual(controls._resolve_physical(serial_device, root), root / '1-3')
            with self.assertRaises(ValueError):
                controls._resolve_physical(dict(MOUSE, id='steelseries:aerox5:port:1-4'), root)
            p = root / '1-5'
            p.mkdir()
            (p / 'idVendor').write_text('1038')
            (p / 'idProduct').write_text('2232')
            with self.assertRaises(ValueError):
                controls._resolve_physical(NOVA, root)

    def test_headset_exact_selector_action_checks_and_no_fake_verification(self):
        from pathlib import Path
        from types import SimpleNamespace
        import json
        actions = [dict(capability='CAP_INACTIVE_TIME', status='success'),
                   dict(capability='CAP_EQUALIZER_PRESET', status='success')]
        entry = dict(id_vendor='0x1038', id_product='0x2232', status='success')
        with patch.object(controls, '_resolve_physical', return_value=Path('/sys/devices/1-2')), patch.object(controls, '_run') as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps({'actions': actions, 'devices': [entry]}), stderr='')
            result = controls._execute(NOVA, {'inactive_time': 5, 'equalizer_preset': 1})
            self.assertTrue(result['ok'])
            self.assertFalse(result['verified'])
            self.assertEqual(result['readback'], {})
            argv = run.call_args.args[0]
            self.assertEqual(argv[1:3], ['--device', '1038:2232'])
            self.assertIn('--inactive-time', argv)
            self.assertNotIn('--sidetone', argv)
            actions[0]['status'] = 'failure'
            run.return_value.stdout = json.dumps({'actions': actions, 'devices': [entry]})
            self.assertFalse(controls._execute(NOVA, {'inactive_time': 5})['ok'])
            run.return_value.stdout = json.dumps({'devices': []})
            self.assertFalse(controls._execute(NOVA, {'inactive_time': 5})['ok'])

    def test_exact_mouse_hid_interface_selection(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            usb = root / '1-3'
            iface = usb / '1-3:1.3'
            target = iface / 'hid-device'
            target.mkdir(parents=True)
            (iface / 'bInterfaceNumber').write_text('03')
            hidroot = root / 'hidraw'
            node = hidroot / 'hidraw7'
            node.mkdir(parents=True)
            (node / 'device').symlink_to(target)
            self.assertEqual(controls._mouse_path(usb, hidroot), b'/dev/hidraw7')
            (iface / 'bInterfaceNumber').write_text('02')
            with self.assertRaises(ValueError):
                controls._mouse_path(usb, hidroot)

    def test_mouse_real_rivalcfg_encodes_only_allowed_packets(self):
        try:
            import rivalcfg
        except ImportError:
            self.skipTest('Run this test with isolated rivalcfg venv interpreter')
        from pathlib import Path
        class FakeHID:
            def __init__(self):
                self.packets = []
                self.path = None
                self.closed = False
            def open_path(self, path):
                self.path = path
            def write(self, data):
                self.packets.append(bytes(data))
                return len(data)
            def read(self, length, timeout_ms):
                return [0] * length  # transport response, NOT hardware setting verification
            def close(self):
                self.closed = True
        fake = FakeHID()
        with patch.object(controls, '_mouse_path', return_value=b'/dev/hidraw7'):
            result = controls._apply_mouse(MOUSE, {'dpi': 800, 'polling_rate': 500, 'sleep_timer': 5}, Path('/sys/usb/1-3'), hid_factory=lambda: fake)
        self.assertTrue(result['ok'])
        self.assertFalse(result['verified'])
        self.assertEqual(result['readback'], {})
        self.assertEqual(fake.path, b'/dev/hidraw7')
        self.assertEqual(fake.packets, [b'\x00\x6d\x01\x00\x09', b'\x00\x6b\x01', b'\x00\x69\xe0\x93\x04', b'\x00\x51\x00'])
        self.assertTrue(fake.closed)

    def test_transport_rejects_unapproved_commands_and_short_writes(self):
        from unittest.mock import Mock
        raw = Mock()
        transport = controls._CheckedHID(raw, True)
        with self.assertRaises(ValueError):
            transport.write(b'\x00\x61\x01')
        raw.write.assert_not_called()
        raw.write.return_value = 0
        with self.assertRaises(OSError):
            transport.write(b'\x00\x6b\x01')
        transport.close()
        transport.close()
        raw.close.assert_called_once()

    def test_apply_reports_timeout_and_invalid_worker_response(self):
        import subprocess
        for response in ['not-json', '{}', '{"ok":true,"verified":true,"readback":{},"message":"bad"}']:
            from types import SimpleNamespace
            with patch.object(controls, '_run', return_value=SimpleNamespace(returncode=0, stdout=response, stderr='')):
                self.assertFalse(controls.apply(NOVA, {'inactive_time': 1})['ok'])
        with patch.object(controls, '_run', side_effect=subprocess.TimeoutExpired('worker', 8)):
            self.assertFalse(controls.apply(NOVA, {'inactive_time': 1})['ok'])
        with patch.object(controls, '_run', side_effect=AssertionError('unsafe target must not run')):
            self.assertFalse(controls.apply(dict(NOVA, control_identity_safe=False), {'inactive_time': 1})['ok'])

    def test_bounded_runner_kills_entire_worker_process_group(self):
        import subprocess
        from unittest.mock import Mock
        fake = Mock()
        fake.communicate.side_effect = [subprocess.TimeoutExpired('worker', 0.01), ('', '')]
        fake.pid = 12345
        with patch('subprocess.Popen', return_value=fake) as popen, patch('os.killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                controls._run([sys.executable, '--apply-worker'], timeout=0.01)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            self.assertFalse(popen.call_args.kwargs['shell'])
            kill.assert_called_once()


    def test_sidetone_exact_action_without_physical_writes(self):
        from pathlib import Path
        from types import SimpleNamespace
        import json
        payload={'actions':[{'capability':'CAP_SIDETONE','status':'success'}], 'devices':[{'id_vendor':'0x1038','id_product':'0x2232','status':'success'}]}
        with patch.object(controls,'_resolve_physical',return_value=Path('/sys/devices/1-2')),patch.object(controls,'_run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(payload),stderr='')) as run:
            result=controls._execute(NOVA,{'sidetone':27})
            self.assertTrue(result['ok']);self.assertFalse(result['verified'])
            self.assertEqual(run.call_args.args[0][-2:],['--sidetone','27'])

if __name__ == '__main__':
    unittest.main()
