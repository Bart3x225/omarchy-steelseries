import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe

class StatusTests(unittest.TestCase):
    def test_reports_battery_for_exact_device(self):
        result = probe.normalize({'devices': [
            {'id_vendor': '0x1038', 'id_product': '0x1854', 'battery': {'status': 'BATTERY_AVAILABLE', 'level': 99}},
            {'id_vendor': '0x1038', 'id_product': '0x2232', 'battery': {'status': 'BATTERY_AVAILABLE', 'level': 64}}
        ]})
        self.assertEqual(result['state'], 'connected')
        self.assertEqual(result['battery'], 64)
        self.assertFalse(result['charging'])

    def test_popup_uses_explicit_root_status(self):
        from pathlib import Path
        import re
        qml = Path(__file__).with_name('Panel.qml').read_text()
        self.assertIsNone(re.search(r'(?<![\w.])status\.', qml), 'Popup loader scope must not shadow headset status')

    def device(self, **fields):
        return {'devices': [dict(id_vendor='0x1038', id_product='0x2232', **fields)]}

    def test_absent(self):
        self.assertEqual(probe.normalize({'devices': []})['state'], 'absent')

    def test_offline_is_not_a_permission_error(self):
        self.assertEqual(probe.normalize(self.device(errors={'battery': 'Device is offline or not responding'}))['state'], 'offline')
        self.assertEqual(probe.normalize(self.device(errors={'battery': 'Could not open device'}))['state'], 'error')

    def test_charging_and_invalid_percent(self):
        status = probe.normalize(self.device(battery={'status': 'BATTERY_CHARGING', 'level': 0}))
        self.assertTrue(status['charging'])
        self.assertEqual(status['battery'], 0)
        for level in (-1, 101, True, '60'):
            self.assertEqual(probe.normalize(self.device(battery={'status': 'BATTERY_AVAILABLE', 'level': level}))['state'], 'error')

    def test_unavailable_is_never_connected(self):
        self.assertEqual(probe.normalize(self.device(battery={'status': 'BATTERY_UNAVAILABLE', 'level': 60}))['state'], 'error')

    def test_optional_values_validated(self):
        status = probe.normalize(self.device(battery={'status': 'BATTERY_AVAILABLE', 'level': 50}, chatmix=64, sidetone={'level': 27}))
        self.assertEqual(status['chatmix'], 64)
        self.assertEqual(status['sidetone'], 27)

if __name__ == '__main__':
    unittest.main()
