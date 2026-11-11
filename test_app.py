import unittest
import importlib.util
from pathlib import Path

class AppTests(unittest.TestCase):
    def test_unknown_command_has_no_hardware_side_effect(self):
        path=Path(__file__).with_name('app.py')
        self.assertTrue(path.exists(), 'Application command dispatcher missing')
        spec=importlib.util.spec_from_file_location('steelseries_app',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.validate_command('rgb'), False)
        self.assertEqual(module.validate_command('snapshot'), True)
        self.assertEqual(module.validate_command('apply'), True)

    def test_empty_apply_rejected_before_device_access(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        path=Path(__file__).with_name('app.py');spec=importlib.util.spec_from_file_location('steelseries_app',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        calls=[]
        fakefleet=SimpleNamespace(collect_all=lambda:(calls.append('read') or {'devices':[]}))
        with patch.dict('sys.modules',{'prefs':SimpleNamespace(),'fleet':fakefleet,'controls':SimpleNamespace()}):
            with self.assertRaises(ValueError): module.execute_command('apply',['device','{}'])
        self.assertEqual(calls, [], 'invalid Apply must not access hardware')

    def test_snapshot_rejects_extra_arguments(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        path=Path(__file__).with_name('app.py');spec=importlib.util.spec_from_file_location('steelseries_app',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        fakefleet=SimpleNamespace(collect_all=lambda:{'devices':[],'updated':1})
        with patch.dict('sys.modules',{'prefs':SimpleNamespace(load_config=lambda:{}),'fleet':fakefleet,'controls':SimpleNamespace(),'history':SimpleNamespace(record_and_summarize=lambda *a,**k:{})}):
            with self.assertRaises(ValueError): module.execute_command('snapshot',['unexpected'])

class ReleaseAuditTests(unittest.TestCase):
    """Exercise the publication gate against isolated source trees, never devices."""

    def setUp(self):
        import tempfile
        import json
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = {'id': 'bart.steelseries', 'name': 'SteelSeries Devices',
                         'version': '0.1.0-beta.1', 'entryPoints': {'barWidget': 'Panel.qml'}}
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))
        (self.root / 'README.md').write_text('# SteelSeries Devices\n')
        (self.root / 'Panel.qml').write_text('import QtQuick\nItem {}\n')
        (self.root / 'LICENSE').write_text(
            'MIT License\nCopyright (c) 2026 Example\n'
            'Permission is hereby granted, free of charge, to any person obtaining a copy\n'
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND\n')
        (self.root / 'controls.py').write_text(Path(__file__).with_name('controls.py').read_text())
        script = Path(__file__).parent / 'scripts' / 'check-release.py'
        spec = importlib.util.spec_from_file_location('release_check', script)
        self.audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.audit)

    def test_valid_source_and_device_model_name_pass(self):
        (self.root / 'README.md').write_text('Supported device: Arctis Nova 5\n')
        self.assertEqual(self.audit.audit(self.root), [])

    def test_wrong_identity_and_missing_license_fail(self):
        import json
        self.manifest['id'] = 'wrong.id'
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))
        (self.root / 'LICENSE').unlink()
        errors = '\n'.join(self.audit.audit(self.root))
        self.assertIn('manifest.json', errors)
        self.assertIn('LICENSE', errors)

    def test_private_data_secrets_binaries_and_absolute_paths_fail(self):
        cases = {
            'settings.json': '{}', 'history.sqlite3': 'private', '.env': 'TOKEN=private',
            'screenshot.png': 'private', 'session.log': 'private',
            'notes.md': 'private path: ' + '/home/' + 'example/.config/profile',
            'secret.txt': 'gh' + 'p_' + 'x' * 36,
            'headsetcontrol': '\x7fELF' + 'binary',
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                path = self.root / name
                path.write_text(text)
                self.assertTrue(self.audit.audit(self.root), name)
                path.unlink()

    def test_lighting_control_and_extra_hid_opcode_fail(self):
        path = self.root / 'controls.py'
        original = path.read_text()
        for old, new in [("_integer('dpi'", "_integer('rgb'"),
                         ('(0x2d, 0x2b, 0x29, 0x11)', '(0x2d, 0x2b, 0x29, 0x11, 0x61)')]:
            with self.subTest(change=new):
                self.assertIn(old, original)
                path.write_text(original.replace(old, new))
                self.assertTrue(self.audit.audit(self.root), new)
        path.write_text(original)

    def test_old_plugin_identity_in_qml_fails_but_migration_is_allowed(self):
        old_id = 'bart.' + 'nova5'
        (self.root / 'Panel.qml').write_text('Item { property string pluginId: "' + old_id + '" }')
        self.assertTrue(self.audit.audit(self.root))
        (self.root / 'Panel.qml').write_text('import QtQuick\nItem {}\n')
        (self.root / 'migrate.py').write_text('OLD_ID = "' + old_id + '"\n')
        self.assertEqual(self.audit.audit(self.root), [])

    def test_symlinks_are_rejected_without_following_target(self):
        (self.root / 'escape').symlink_to(Path(__file__).parent, target_is_directory=True)
        self.assertTrue(self.audit.audit(self.root))


if __name__=='__main__': unittest.main()
