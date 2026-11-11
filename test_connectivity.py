"""Read-only connectivity regression tests, no Bluetooth/HID hardware needed."""
import sys
import os
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet


MAC = 'AA:BB:CC:DD:EE:01'
PATH = '/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01'


def objects(**props):
    values = dict(Address=MAC, Paired=True, Connected=True, Name='SteelSeries Aerox 5')
    values.update(props)
    return {PATH: {'org.bluez.Device1': values}}


class ConnectivityTests(unittest.TestCase):
    def test_bluetooth_inventory_filters_and_uses_stable_address(self):
        self.assertTrue(hasattr(fleet, 'bluetooth_devices'), 'Bluetooth inventory missing')
        data = objects()
        data[PATH]['org.bluez.Battery1'] = {'Percentage': 64}
        data['/other'] = {'org.bluez.Device1': dict(Address='AA:BB:CC:DD:EE:02',
                          Paired=True, Connected=True, Name='Other keyboard')}
        data['/unpaired'] = {'org.bluez.Device1': dict(Address='AA:BB:CC:DD:EE:03',
                             Name='SteelSeries Aerox', Paired=False)}
        device, = fleet.bluetooth_devices(data)
        self.assertEqual(device['id'], 'steelseries:bluetooth:' + MAC.lower())
        self.assertEqual((device['battery'], device['transport'], device['state']),
                         (64, 'bluetooth', 'connected'))
        data[PATH]['org.bluez.Device1']['Alias'] = 'Renamed peripheral'
        self.assertEqual(fleet.bluetooth_devices(data)[0]['id'], device['id'])

    def test_upower_requires_exact_identity_and_no_stale_offline_battery(self):
        data = objects()
        other = dict(Serial='AA:BB:CC:DD:EE:09', Percentage=91, State=1, IsPresent=True)
        exact = dict(Serial=MAC.lower(), Percentage=42, State=1, IsPresent=True)
        self.assertEqual(fleet.bluetooth_devices(data, [other])[0]['battery'], -1)
        device, = fleet.bluetooth_devices(data, [exact])
        self.assertEqual((device['battery'], device['charging'], device['charging_known']), (42, True, True))
        data[PATH]['org.bluez.Device1']['Connected'] = False
        device, = fleet.bluetooth_devices(data, [exact])
        self.assertEqual((device['state'], device['battery'], device['charging']), ('offline', -1, False))

    def test_collect_all_merges_only_unique_exact_identity(self):
        self.assertTrue(hasattr(fleet, 'collect_all'), 'aggregate API missing')
        bt = fleet.bluetooth_devices(objects())[0]
        usb = dict(bt, id='steelseries:aerox5:serial:other', transport='wireless',
                   serial='other', battery=55, state='connected')
        usb.pop('bluetooth_address')
        def run(devices):
            return fleet.collect_all(usb_reader=lambda: {'devices': devices}, bluetooth_reader=lambda: [bt])
        self.assertEqual(len(run([usb])['devices']), 2, 'same model must never imply same hardware')
        usb['serial'] = MAC.lower()
        merged, = run([usb])['devices']
        self.assertEqual(merged['id'], usb['id'])
        self.assertEqual(merged['transports'], ['wireless', 'bluetooth'])
        self.assertEqual(merged['bluetooth_address'], MAC.lower())
        self.assertEqual(len(run([usb, dict(usb, id='duplicate')])['devices']), 3)
        usb['serial'] = 'not-a-mac'
        usb['name'] = bt['name']
        self.assertEqual(len(run([usb])['devices']), 2)

    def test_read_workers_are_bounded_and_usb_exports_serial_only_opt_in(self):
        self.assertTrue(hasattr(fleet, 'query_usb'), 'bounded USB worker missing')
        import subprocess
        with patch.object(fleet.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"devices":[]}')) as run:
            self.assertEqual(fleet.query_usb(), {'devices': []})
            self.assertLessEqual(run.call_args.kwargs['timeout'], 4)
            self.assertIn('--usb-all', run.call_args.args[0])
        with patch.object(fleet.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '[]')) as run:
            self.assertEqual(fleet.read_bluetooth(), [])
            self.assertLessEqual(run.call_args.kwargs['timeout'], 1.5)
            self.assertIn('--bluetooth', run.call_args.args[0])
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            node = Path(tmp) / '1-1'
            node.mkdir()
            for key, value in dict(idVendor='1038', idProduct='1620', product='Apex', serial=MAC).items():
                (node / key).write_text(value)
            reader = lambda: {'devices': []}
            self.assertNotIn('serial', fleet.collect(Path(tmp), reader)['devices'][0])
            self.assertEqual(fleet.collect(Path(tmp), reader, include_identity=True)['devices'][0]['serial'], MAC)

    def test_system_bluetooth_uses_only_bounded_read_methods(self):
        self.assertTrue(hasattr(fleet, 'system_bluetooth'), 'system bus reader missing')
        from unittest.mock import Mock
        import types
        bluez = Mock()
        bluez.GetManagedObjects.return_value = objects()
        upower = Mock()
        upower.EnumerateDevices.return_value = ['/org/freedesktop/UPower/devices/mouse']
        properties = Mock()
        properties.GetAll.return_value = dict(Serial=MAC, Percentage=33, IsPresent=True, State=2)
        bus = Mock()
        bus.get_object.side_effect = lambda service, path, **kw: (
            bluez if service == 'org.bluez' else upower if path == '/org/freedesktop/UPower' else properties)
        module = types.SimpleNamespace(SystemBus=lambda **kw: bus, Interface=lambda obj, interface: obj)
        with patch.dict('sys.modules', dbus=module):
            device, = fleet.system_bluetooth()
        self.assertEqual(device['battery'], 33)
        for obj in (bluez, upower, properties):
            for call in obj.method_calls:
                self.assertIn(call[0], ('GetManagedObjects', 'EnumerateDevices', 'GetAll'))
                self.assertLessEqual(call.kwargs['timeout'], 0.35)
        bus.close.assert_called_once()

    @unittest.skipUnless(os.environ.get("STEELSERIES_HARDWARE_TESTS") == "1",
                         "opt-in live read smoke: STEELSERIES_HARDWARE_TESTS=1")
    def test_bluetooth_cli_emits_inventory_list_or_explicit_failure(self):
        import json
        import subprocess
        process = subprocess.run([sys.executable, '-B', fleet.__file__, '--bluetooth'],
                                 capture_output=True, text=True, timeout=2)
        if process.returncode:
            self.assertEqual(process.stdout, '')
            self.assertTrue(process.stderr.strip())
        else:
            self.assertIsInstance(json.loads(process.stdout), list)
            self.assertEqual(process.stderr, '')

    def test_mouse_no_response_unknown_and_transient_read_retries_once(self):
        self.assertEqual(fleet.decode_aerox([])['state'], 'unknown', 'no response is not confirmed radio offline')
        import json
        import subprocess
        empty = subprocess.CompletedProcess([], 0, json.dumps(fleet.decode_aerox([])))
        success = subprocess.CompletedProcess([], 0, json.dumps(fleet.decode_aerox([0xd2, 20])))
        with patch.object(fleet.subprocess, 'run', side_effect=[empty, success]) as run:
            self.assertEqual(fleet.query_mouse({'_path': '/fake', '_pid': '1852'})['battery'], 95)
            self.assertEqual(run.call_count, 2)
        with patch.object(fleet.subprocess, 'run', return_value=empty) as run:
            self.assertEqual(fleet.query_mouse({'_path': '/fake', '_pid': '1852'})['state'], 'unknown')
            self.assertEqual(run.call_count, 2)
        for message in ('PermissionError: hidraw access denied', 'Invalid Aerox battery response'):
            error = subprocess.CompletedProcess([], 0, json.dumps(fleet.failure(message)))
            with patch.object(fleet.subprocess, 'run', return_value=error) as run:
                self.assertEqual(fleet.query_mouse({'_path': '/fake', '_pid': '1852'})['state'], 'error')
                self.assertEqual(run.call_count, 1)

    @patch.object(
        fleet.runtime, "headsetcontrol", return_value=Path("/fake/runtime/headsetcontrol"))
    def test_headset_timeout_retries_once_with_total_budget(self, _backend):
        import subprocess
        success = subprocess.CompletedProcess([], 0, '{"devices":[]}')
        with patch.object(fleet.subprocess, 'run', side_effect=[subprocess.TimeoutExpired('headset', 1), success]) as run:
            self.assertEqual(fleet.read_headsets(), {'devices': []})
            self.assertEqual(run.call_count, 2)
            self.assertLessEqual(sum(call.kwargs['timeout'] for call in run.call_args_list), 2.5)
        with patch.object(fleet.subprocess, 'run', side_effect=subprocess.TimeoutExpired('headset', 1)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                fleet.read_headsets()
            self.assertEqual(run.call_count, 2)

    def test_source_failure_retains_other_inventory_and_reports_not_offline(self):
        usb = fleet.bluetooth_devices(objects())[0]
        def broken():
            raise PermissionError('BlueZ denied')
        result = fleet.collect_all(usb_reader=lambda: {'devices': [usb]}, bluetooth_reader=broken)
        self.assertEqual(result['devices'], [usb])
        self.assertEqual(set(result), {'devices', 'updated'})
        self.assertTrue(hasattr(fleet.collect_all, 'last_errors'), 'failed source must not silently mean disconnection')
        self.assertIn('bluetooth', fleet.collect_all.last_errors)
        self.assertIn('denied', fleet.collect_all.last_errors['bluetooth'])
        fleet.collect_all(usb_reader=lambda: {'devices': []}, bluetooth_reader=lambda: [])
        self.assertEqual(fleet.collect_all.last_errors, {})

    def test_modalias_is_exact_vendor_not_prefix_and_pid_width_validated(self):
        self.assertEqual(fleet.bluetooth_devices(objects(Name='Unrelated', Modalias='usb:v10380p1852')), [])
        for alias in ('usb:v1038p1852d0100', 'bluetooth:v00001038p00001852d00000001'):
            device, = fleet.bluetooth_devices(objects(Name='Known vendor peripheral', Modalias=alias))
            self.assertEqual(device['id_product'], '0x1852')
        device, = fleet.bluetooth_devices(objects(Name='Vendor peripheral', ManufacturerData={0x1038: b''}))
        self.assertEqual(device['battery'], -1)
        self.assertFalse(device['battery_supported'])
        self.assertEqual(device['battery_capability'], 'unknown')

    def test_bluez_transient_timeout_retries_once_but_permissions_do_not(self):
        from unittest.mock import Mock
        import types
        class BusError(Exception):
            def __init__(self, name):
                self.name = name
            def get_dbus_name(self):
                return self.name
        for name, expected in (('org.freedesktop.DBus.Error.NoReply', 2),
                               ('org.freedesktop.DBus.Error.AccessDenied', 1)):
            manager = Mock()
            manager.GetManagedObjects.side_effect = BusError(name)
            bus = Mock()
            bus.get_object.return_value = manager
            module = types.SimpleNamespace(SystemBus=lambda **kw: bus, Interface=lambda obj, interface: obj)
            with patch.dict('sys.modules', dbus=module):
                with self.assertRaises(BusError):
                    fleet.system_bluetooth()
            self.assertEqual(manager.GetManagedObjects.call_count, expected)
            bus.close.assert_called_once()

    def test_hung_workers_aggregate_deadline_under_five_seconds(self):
        import tempfile
        import time
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            worker = Path(tmp) / 'fleet.py'
            worker.write_text('import time; time.sleep(30)\n')
            start = time.monotonic()
            with patch.object(fleet, '__file__', str(worker)):
                result = fleet.collect_all()
            self.assertLess(time.monotonic() - start, 4.8)
            self.assertEqual(result['devices'], [])
            self.assertEqual(set(fleet.collect_all.last_errors), {'usb', 'bluetooth'})

    def test_bluetooth_invalid_battery_unknown_connection_and_missing_identity(self):
        self.assertEqual(fleet.bluetooth_devices(objects(Address='')), [])
        data = objects()
        for level in (True, '70', -1, 101, float('nan')):
            data[PATH]['org.bluez.Battery1'] = {'Percentage': level}
            device, = fleet.bluetooth_devices(data)
            self.assertEqual(device['battery'], -1)
            self.assertEqual(device['state'], 'connected')
            self.assertTrue(device['error'])
        del data[PATH]['org.bluez.Device1']['Connected']
        self.assertEqual(fleet.bluetooth_devices(data)[0]['state'], 'unknown')
        power = dict(Name='SteelSeries Aerox 5', Percentage=75, State=2, IsPresent=True)
        self.assertEqual(fleet.bluetooth_devices(objects(), [power])[0]['battery'], -1)
        bt = fleet.bluetooth_devices(objects())[0]
        usb = dict(bt, id='usb:unique', serial=MAC, transport='usb')
        usb.pop('bluetooth_address')
        self.assertEqual(len(fleet.merge_devices([usb], [bt, dict(bt, id='bt:second-adapter')])), 3)

    def test_unnamed_device_cannot_become_steelseries_from_our_fallback(self):
        self.assertEqual(fleet.bluetooth_devices(objects(Name='', Alias='')), [])
        device, = fleet.bluetooth_devices(objects(Name='', Alias='', ManufacturerData={0x1038: b''}))
        self.assertEqual(device['name'], 'SteelSeries Bluetooth')

    def test_headset_permission_diagnostic_is_not_explicit_offline(self):
        device = dict(fleet.bluetooth_devices(objects())[0], _pid='2232', _path='/usb/1-1',
                      _serial='', kind='headset', battery_supported=True)
        payload = {'devices': [dict(id_vendor='0x1038', id_product='0x2232',
                   capabilities=['CAP_BATTERY_STATUS'], battery={'status': 'BATTERY_UNAVAILABLE'},
                   errors={'battery': 'Could not open device: permission denied (offline?)'})]}
        with patch.object(fleet, 'discover', return_value=[device]):
            result, = fleet.collect(headset_reader=lambda: payload)['devices']
        self.assertEqual(result['state'], 'error')
        self.assertIn('permission denied', result['error'])


if __name__ == '__main__':
    unittest.main()
