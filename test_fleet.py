"""Offline regression tests; python -m unittest -v test_fleet."""
from pathlib import Path
import tempfile
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fleet


class FleetTests(unittest.TestCase):
    def usb(self, root, port, pid, name, serial=''):
        p = root / port
        p.mkdir()
        for key, val in dict(idVendor='1038', idProduct=pid, product=name, serial=serial).items():
            (p / key).write_text(val)
        return p

    def test_discover_physical_not_interfaces_retains_identical(self):
        self.assertTrue(hasattr(fleet, 'discover'), 'physical discovery is missing')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.usb(root, '1-1', '1620', 'SteelSeries Apex 9 Mini')
            self.usb(root, '1-2', '1620', 'SteelSeries Apex 9 Mini')
            self.usb(root, '1-3', 'ffff', 'Unknown SteelSeries')
            self.usb(root, '1-1:1.0', '1620', 'SteelSeries Apex 9 Mini')
            devices = fleet.discover(root)
            self.assertEqual(len(devices), 3)
            self.assertEqual(len({d['id'] for d in devices}), 3)
            self.assertEqual([d['kind'] for d in devices], ['keyboard', 'keyboard', 'device'])
            for d in devices:
                self.assertEqual(d['battery'], -1)
                self.assertFalse(d['battery_supported'])
                self.assertEqual(d['state'], 'connected')

    def test_aerox_battery_query_is_only_read_command(self):
        self.assertTrue(hasattr(fleet, 'read_aerox'), 'Aerox telemetry missing')
        class HidDevice:
            def __init__(self):
                self.writes = []
                self.closed = False
            def open_path(self, path):
                self.path = path
            def write(self, data):
                self.writes.append(bytes(data))
                return len(data)
            def read(self, length, timeout_ms):
                self.request = (length, timeout_ms)
                return [0x92, 0x80 | 15]
            def close(self):
                self.closed = True
        for wireless in (False, True):
            hid = HidDevice()
            result = fleet.read_aerox(b'/dev/test', wireless, lambda: hid)
            self.assertEqual(result, dict(state='connected', battery=70, charging=True, error=''))
            self.assertEqual(hid.writes, [bytes([0, 0xd2 if wireless else 0x92])])
            self.assertEqual(hid.request, (2, 200))
            self.assertTrue(hid.closed)

    def test_aerox_rejects_empty_invalid_and_wrong_responses(self):
        self.assertTrue(hasattr(fleet, 'decode_aerox'), 'Aerox decoder missing')
        for data in ([], [0x92], [0x92, 0], [0x92, 127], [0x20, 15]):
            self.assertEqual(fleet.decode_aerox(data)['battery'], -1)
        self.assertEqual(fleet.decode_aerox([0x92, 1])['battery'], 0)
        self.assertEqual(fleet.decode_aerox([0x92, 21])['battery'], 100)

    def test_fleet_collects_telemetry_without_leaking_private_fields(self):
        self.assertTrue(hasattr(fleet, 'collect'), 'fleet collection missing')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.usb(root, '1-1', '1854', 'SteelSeries Aerox 5 Wireless', 'mouse-serial')
            self.usb(root, '1-2', '2232', 'SteelSeries Arctis Nova 5')
            self.usb(root, '1-3', '150d', 'SteelSeries QCK Prism Cloth')
            def mouse(device):
                return dict(state='connected', battery=100, charging=True, error='')
            payload = {'devices': [{'id_vendor': '0x1038', 'id_product': '0x2232',
                        'capabilities': ['CAP_BATTERY_STATUS'],
                        'battery': {'status': 'BATTERY_AVAILABLE', 'level': 47}}]}
            result = fleet.collect(root, lambda: payload, mouse)
            self.assertIsInstance(result['updated'], int)
            mouse_d, headset, pad = result['devices']
            self.assertEqual((mouse_d['battery'], mouse_d['charging'], mouse_d['transport']), (100, True, 'usb'))
            self.assertTrue(mouse_d['battery_supported'])
            self.assertTrue(mouse_d['wireless'])  # capability, not active transport
            self.assertEqual(headset['battery'], 47)
            self.assertEqual(headset['kind'], 'headset')
            self.assertFalse(pad['battery_supported'])
            fields = {'id','name','kind','state','battery','charging','wireless','battery_supported','transport','error','id_vendor','id_product'}
            self.assertIn('id_product', mouse_d, 'USB diagnostics missing')
            self.assertEqual(mouse_d['id_product'], '0x1854')
            self.assertEqual(mouse_d['id_vendor'], '0x1038')
            for device in result['devices']:
                self.assertEqual(set(device), fields)
            old_id = mouse_d['id']
            (root / '1-1' / 'idProduct').write_text('1852')
            moved = fleet.collect(root, lambda: payload, mouse)['devices'][0]
            self.assertEqual(moved['id'], old_id)
            self.assertEqual(moved['transport'], 'wireless')

    def test_headset_offline_and_duplicate_not_assigned_guessed_battery(self):
        self.assertTrue(hasattr(fleet, 'collect'), 'fleet collection missing')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.usb(root, '1-1', '2232', 'SteelSeries Arctis Nova 5')
            payload = {'devices': [{'id_vendor': '0x1038', 'id_product': '0x2232',
                'capabilities': ['CAP_BATTERY_STATUS'], 'battery': {'status': 'BATTERY_UNAVAILABLE'},
                'errors': {'battery': 'Device is offline'}}]}
            self.assertEqual(fleet.collect(root, lambda: payload)['devices'][0]['state'], 'offline')
            self.usb(root, '1-2', '2232', 'SteelSeries Arctis Nova 5')
            for d in fleet.collect(root, lambda: payload)['devices']:
                self.assertEqual(d['battery'], -1)
                self.assertEqual(d['state'], 'error')
                self.assertIn('ambiguous', d['error'].lower())

    def test_hid_selection_belongs_to_physical_device_and_interface_three(self):
        self.assertTrue(hasattr(fleet, 'mouse_hid_path'), 'physical HID selection missing')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            usb = root / 'usb' / '1-1'
            hidclass = root / 'hidraw'
            hidclass.mkdir()
            for number, interface in [(1, 0), (2, 3)]:
                target = usb / f'1-1:1.{interface}'
                target.mkdir(parents=True)
                (target / 'bInterfaceNumber').write_text(f'{interface:02x}')
                node = hidclass / f'hidraw{number}'
                node.mkdir()
                (node / 'device').symlink_to(target, target_is_directory=True)
            self.assertEqual(fleet.mouse_hid_path(str(usb), hidclass), b'/dev/hidraw2')
            with self.assertRaises(OSError):
                fleet.mouse_hid_path(str(root / 'other'), hidclass)

    @patch.object(
        fleet.runtime, "headsetcontrol", return_value=Path("/fake/runtime/headsetcontrol"))
    def test_subprocess_queries_have_short_timeouts(self, _backend):
        self.assertTrue(hasattr(fleet, 'read_headsets'), 'bounded headset reader missing')
        self.assertTrue(hasattr(fleet, 'query_mouse'), 'bounded mouse reader missing')
        from unittest.mock import patch
        import subprocess
        with patch.object(fleet.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"devices":[]}')) as run:
            self.assertEqual(fleet.read_headsets(), {'devices': []})
            self.assertLessEqual(run.call_args.kwargs['timeout'], 3)
            self.assertEqual(run.call_args.args[0][-3:], ['-b', '-o', 'json'])
        with patch.object(fleet.subprocess, 'run', side_effect=subprocess.TimeoutExpired('mouse', 1)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                fleet.query_mouse({'_path': '/fake', '_pid': '1854'})
            self.assertLessEqual(run.call_args.kwargs['timeout'], 1)

    @unittest.skipUnless(os.environ.get("STEELSERIES_HARDWARE_TESTS") == "1",
                         "opt-in live read smoke: STEELSERIES_HARDWARE_TESTS=1")
    def test_cli_outputs_one_json_snapshot(self):
        import json
        import subprocess
        process = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('fleet.py'))],
                                 capture_output=True, text=True, timeout=4)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(len(process.stdout.splitlines()), 1, 'CLI must output one JSON line')
        payload = json.loads(process.stdout)
        self.assertEqual(set(payload), {'devices', 'updated'})
        self.assertEqual(process.stderr, '')
        self.assertIsInstance(payload['devices'], list)

    def test_duplicate_mice_and_query_errors_keep_all_physical_devices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.usb(root, '1-1', '1854', 'SteelSeries Aerox 5 Wireless', 'duplicate')
            self.usb(root, '1-2', '1854', 'SteelSeries Aerox 5 Wireless', 'duplicate')
            def denied(device):
                raise PermissionError('hidraw access denied')
            result = fleet.collect(root, lambda: {'devices': []}, denied)
            self.assertEqual(len(result['devices']), 2)
            self.assertEqual(len({d['id'] for d in result['devices']}), 2)
            for d in result['devices']:
                self.assertTrue(d['battery_supported'])
                self.assertEqual((d['state'], d['battery']), ('error', -1))
                self.assertIn('access denied', d['error'])
            (root / '1-1' / 'serial').write_text('')
            (root / '1-2' / 'serial').write_text('')
            before = fleet.collect(root, lambda: {'devices': []}, denied)['devices'][0]['id']
            (root / '1-1' / 'idProduct').write_text('1852')
            after = fleet.collect(root, lambda: {'devices': []}, denied)['devices'][0]['id']
            self.assertEqual(before, after)

    def test_empty_fleet_and_headset_failure_do_not_invent_devices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(fleet.collect(root)['devices'], [])
            self.usb(root, '1-1', '2232', 'SteelSeries Arctis Nova 5')
            self.usb(root, '1-2', 'ffff', 'SteelSeries mystery')
            def broken():
                raise TimeoutError('bounded query expired')
            result = fleet.collect(root, broken)['devices']
            self.assertEqual(result[0]['state'], 'error')
            self.assertIn('expired', result[0]['error'])
            self.assertEqual(result[1]['state'], 'connected')
            self.assertEqual(result[1]['battery'], -1)
            self.assertFalse(result[1]['battery_supported'])

    def test_stalled_sysfs_attribute_read_is_bounded(self):
        import subprocess
        code = "import fleet,os,tempfile,time; from pathlib import Path; " \
               "t=tempfile.TemporaryDirectory(); " \
               "p=Path(t.name)/'product'; os.mkfifo(p); " \
               "start=time.monotonic(); assert fleet.read_text(p)==''; " \
               "assert time.monotonic()-start<0.5"
        try:
            process = subprocess.run([sys.executable, '-B', '-c', code], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=0.7)
        except subprocess.TimeoutExpired:
            self.fail('sysfs reads can stall discovery indefinitely')
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_missing_headset_report_is_not_healthy_and_known_name_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.usb(root, '1-1', '2232', '')
            d = fleet.collect(root, lambda: {'devices': []})['devices'][0]
            self.assertEqual(d['kind'], 'headset')
            self.assertEqual(d['state'], 'error')
            self.assertEqual(d['battery'], -1)
            self.assertIn('Nova 5', d['name'])
            self.assertTrue(d['error'])


if __name__ == '__main__':
    unittest.main()
