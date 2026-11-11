"""Persistence tests: real isolated files/SQLite, no hardware access."""
import importlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'settings.json'
        self.db = self.root / 'history.sqlite3'

    def test_config_defaults_atomic_save_and_isolated_lists(self):
        prefs = importlib.import_module('prefs')
        defaults = prefs.load_config(path=self.config)
        self.assertEqual(defaults, dict(pollSeconds=5, lowThreshold=20, criticalThreshold=5,
            notifyLow=True, notifyCritical=True, notifyFull=True, notifyConnections=True,
            hiddenIds=[], historyDays=30, experimentalControls=False))
        defaults['hiddenIds'].append('not-persisted')
        self.assertEqual(prefs.load_config(path=self.config)['hiddenIds'], [])
        saved = prefs.save_config({'pollSeconds': 12, 'hiddenIds': ['mouse']}, path=self.config)
        self.assertEqual(prefs.load_config(path=self.config), saved)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.iterdir()), [self.config])

    def test_config_validation_is_strict_and_rejects_without_write(self):
        prefs = importlib.import_module('prefs')
        prefs.save_config({}, path=self.config)
        original = self.config.read_bytes()
        for bad in ({'unknown': 1}, {'pollSeconds': True}, {'pollSeconds': 1},
                    {'pollSeconds': 301}, {'lowThreshold': 0}, {'lowThreshold': 100},
                    {'criticalThreshold': -1}, {'criticalThreshold': 21},
                    {'notifyLow': 1}, {'notifyCritical': 'yes'}, {'notifyFull': None},
                    {'notifyConnections': 0}, {'historyDays': 29}, {'historyDays': 30.0},
                    {'hiddenIds': 'mouse'}, {'hiddenIds': [2]}, {'hiddenIds': ['x'] * 65},
                    {'hiddenIds': ['x' * 257]}, {'hiddenIds': ['']}, []):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                prefs.save_config(bad, path=self.config)
            self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(prefs.save_config({'lowThreshold': 1, 'criticalThreshold': 0,
            'pollSeconds': 300}, path=self.config)['criticalThreshold'], 0)

    def test_config_bad_disk_content_falls_back_and_xdg_path(self):
        prefs = importlib.import_module('prefs')
        for text in ('invalid json', '[]', '{"pollSeconds":true}', '{"alien":1}'):
            self.config.write_text(text)
            self.assertEqual(prefs.load_config(path=self.config), prefs.DEFAULTS)
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(self.root)):
            prefs.save_config({'pollSeconds': 2})
            self.assertEqual(prefs.load_config()['pollSeconds'], 2)
            self.assertTrue((self.root / 'omarchy/steelseries/settings.json').exists())

    def device(self, battery=80, **changes):
        return dict(id='mouse', state='connected', battery=battery, charging=False,
                    battery_supported=True, error='', **changes)

    def record(self, devices, now):
        return importlib.import_module('history').record_and_summarize(devices, now=now, db_path=self.db)

    def test_history_stores_real_samples_only_and_throttles(self):
        first = self.record([self.device()], 1000)['mouse']
        self.assertEqual(first, {'points': [{'ts': 1000, 'battery': 80, 'charging': False}],
                                'estimateMinutes': -1, 'estimateSamples': 0})
        self.assertEqual(self.record([self.device()], 1005)['mouse'], first)
        self.assertEqual(len(self.record([self.device()], 1300)['mouse']['points']), 2)
        self.assertEqual(len(self.record([self.device(79)], 1305)['mouse']['points']), 3)
        charging = self.device(79)
        charging['charging'] = True
        self.assertTrue(self.record([charging], 1310)['mouse']['points'][-1]['charging'])
        for battery in (-1, 101, True, 15.5, '50', None):
            self.assertEqual(len(self.record([self.device(battery)], 1320)['mouse']['points']), 4)
        bad = self.device(70)
        bad['state'] = 'error'
        self.assertEqual(len(self.record([bad], 1400)['mouse']['points']), 4)
        self.assertEqual(self.record([bad], 1400)['mouse']['estimateMinutes'], -1)

    def test_history_retention_bounded_output_and_xdg(self):
        self.record([self.device()], 1000)
        for index in range(220):
            self.record([self.device(80 - index % 2)], 2000 + index * 300)
        points = self.record([self.device(80)], 68000)['mouse']['points']
        self.assertLessEqual(len(points), 200)
        self.assertEqual(points[0]['ts'], 1000)
        self.assertEqual(points[-1]['ts'], 68000)
        later = 68000 + 30 * 86400 + 1
        self.assertEqual(self.record([self.device(79)], later)['mouse']['points'],
                         [{'ts': later, 'battery': 79, 'charging': False}])
        from contextlib import closing
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0], 1)
        with patch.dict(os.environ, XDG_STATE_HOME=str(self.root)):
            importlib.import_module('history').record_and_summarize([], now=1000)
            self.assertTrue((self.root / 'omarchy/steelseries/history.sqlite3').exists())

    def discharge(self, start=1000):
        self.record([self.device(80)], start)
        self.record([self.device(77)], start + 900)
        return self.record([self.device(74)], start + 1800)['mouse']

    def test_history_estimate_requires_actual_sustained_discharge(self):
        summary = self.discharge()
        self.assertEqual(summary['estimateMinutes'], 370)
        self.assertEqual(summary['estimateSamples'], 3)
        self.assertEqual(self.record([self.device(74)], 2805)['mouse']['estimateMinutes'], 370)
        rise = self.record([self.device(75)], 2810)['mouse']
        self.assertEqual(rise['estimateMinutes'], -1)
        self.assertEqual(rise['estimateSamples'], 0)

    def test_history_estimate_resets_on_charge_reconnect_error_and_gap(self):
        for reset in ('charge', 'offline', 'absent', 'error', 'invalid', 'gap'):
            with self.subTest(reset=reset):
                self.db = self.root / (reset + '.sqlite3')
                self.assertGreater(self.discharge()['estimateMinutes'], 0)
                device = self.device(74)
                if reset == 'charge':
                    device['charging'] = True
                elif reset in ('offline', 'error'):
                    device['state'] = reset
                elif reset == 'invalid':
                    device['battery'] = -1
                self.record([] if reset == 'absent' else [device], 2810)
                result = self.record([self.device(73)], 4000 if reset == 'gap' else 2820)['mouse']
                self.assertEqual(result['estimateMinutes'], -1)
                self.assertEqual(result['estimateSamples'], 0)

    def test_history_no_estimate_for_short_flat_or_two_sample_segment(self):
        for index, readings in enumerate(([(1000, 80), (1100, 70), (1200, 60)],
                                         [(1000, 80), (1900, 79), (2800, 78)],
                                         [(1000, 80), (2800, 60)])):
            with self.subTest(readings=readings):
                self.db = self.root / ('case' + str(index) + '.sqlite3')
                for timestamp, battery in readings:
                    summary = self.record([self.device(battery)], timestamp)['mouse']
                self.assertEqual(summary['estimateMinutes'], -1)
                self.assertEqual(summary['estimateSamples'], 0)

    def test_config_failed_replace_preserves_old_file_and_cleans_temp(self):
        prefs = importlib.import_module('prefs')
        prefs.save_config({}, path=self.config)
        original = self.config.read_bytes()
        with patch.object(prefs.os, 'replace', side_effect=OSError('simulated storage failure')):
            with self.assertRaises(OSError):
                prefs.save_config({'pollSeconds': 8}, path=self.config)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [self.config])

    def test_history_identical_polls_do_not_modify_sqlite(self):
        self.record([self.device()], 1000)
        original = self.db.read_bytes()
        modified = self.db.stat().st_mtime_ns
        for timestamp in range(1005, 1030, 5):
            self.record([self.device()], timestamp)
        self.assertEqual(self.db.read_bytes(), original)
        self.assertEqual(self.db.stat().st_mtime_ns, modified)
        self.record([], 1030)
        original = self.db.read_bytes()
        self.record([], 1035)
        self.assertEqual(self.db.read_bytes(), original)
        points = self.record([self.device()], 1040)['mouse']['points']
        self.assertEqual([p['ts'] for p in points], [1000, 1040])

    def test_history_devices_are_isolated_and_bad_telemetry_is_not_saved(self):
        other = self.device(40)
        other['id'] = 'headset'
        self.record([self.device(), other, {}, None], 1000)
        other['charging'] = 'yes'
        summary = self.record([other], 1300)
        self.assertEqual(set(summary), {'headset'})
        self.assertEqual(len(summary['headset']['points']), 1)
        other['charging'] = False
        other['battery_supported'] = False
        self.assertEqual(len(self.record([other], 1600)['headset']['points']), 1)
        other['battery_supported'] = True
        other['error'] = 'permission denied'
        self.assertEqual(len(self.record([other], 1900)['headset']['points']), 1)
        self.assertEqual(len(self.record([self.device()], 2000)['mouse']['points']), 2)

    def test_config_mode_is_exactly_0600_even_with_restrictive_umask(self):
        prefs = importlib.import_module('prefs')
        old_mask = os.umask(0o777)
        try:
            prefs.save_config({}, path=self.config)
        finally:
            os.umask(old_mask)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
