"""Offline installer tests: no device or system installation operations."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import setup
import runtime
import hashlib
import io as binary_io
import tarfile
import subprocess


class SetupTests(unittest.TestCase):
    def test_help_and_check_do_not_create_data_tree(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(setup.main([]), 0)
                self.assertIn(setup.main(['--check']), (0, 1))
            self.assertEqual(list(Path(tmp).iterdir()), [])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                setup.main(['--check', '--all'])

    def test_pinned_build_checks_archive_and_records_local_binary(self):
        def archive(name='HeadsetControl-test/license'):
            stream = binary_io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w:gz') as tf:
                info = tarfile.TarInfo(name)
                info.size = 7
                tf.addfile(info, binary_io.BytesIO(b'GPLv3\n\n'))
            return stream.getvalue()
        payload = archive()
        commands = []
        def run(argv, **kwargs):
            commands.append(argv)
            if '--build' in argv:
                binary = Path(argv[2]) / 'headsetcontrol'
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b'test build')
                binary.chmod(0o700)
            return subprocess.CompletedProcess(argv, 0)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}):
            with patch('setup.urllib.request.urlopen', side_effect=lambda *a, **kw: binary_io.BytesIO(payload)), patch('setup.subprocess.run', side_effect=run):
                with self.assertRaises(ValueError):
                    setup.build_headsetcontrol()
                with patch.object(runtime, 'HEADSET_ARCHIVE_SHA256', hashlib.sha256(payload).hexdigest()):
                    binary = setup.build_headsetcontrol()
                    self.assertEqual(runtime.headsetcontrol(for_apply=True), binary)
                    self.assertTrue((runtime.headset_dir() / 'LICENSE').is_file())
                    self.assertTrue((runtime.headset_dir() / 'source.tar.gz').is_file())
            self.assertEqual(len(commands), 2)
            self.assertIn('--target', commands[1])
            self.assertIn('headsetcontrol', commands[1])

    def test_udev_only_stages_scoped_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}):
            path = setup.stage_udev_rules()
            self.assertTrue(path.is_relative_to(Path(tmp)))
            text = path.read_text()
            self.assertIn('SUBSYSTEM=="hidraw"', text)
            self.assertIn('TAG+="uaccess"', text)
            self.assertNotIn('0666', text)
            self.assertNotIn('RUN', text)
            self.assertEqual(text.count('ATTRS{idProduct}'), 8)

    def test_mouse_install_is_venv_only_and_pinned(self):
        commands = []
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}), patch('setup.subprocess.run', side_effect=lambda argv, **kw: commands.append(argv)):
            setup.install_mouse_controls()
            self.assertEqual(commands[0][-3:-1], ['-m', 'venv'])
            self.assertEqual(commands[1][0], str(runtime.mouse_python()))
            self.assertIn('--require-virtualenv', commands[1])
            self.assertIn('--no-deps', commands[1])
            requirements = Path(commands[1][-1]).read_text()
            self.assertIn('rivalcfg==4.17.0', requirements)
            self.assertIn('hidapi==0.15.0', requirements)

    def test_root_install_is_rejected_without_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}), patch('os.geteuid', return_value=0), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                setup.main(['--all'])
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_extract_rejects_archive_traversal(self):
        payload = binary_io.BytesIO()
        with tarfile.open(fileobj=payload, mode='w:gz') as tf:
            entry = tarfile.TarInfo('../escape')
            entry.size = 1
            tf.addfile(entry, binary_io.BytesIO(b'x'))
        content = payload.getvalue()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}), patch.object(runtime, 'HEADSET_ARCHIVE_SHA256', hashlib.sha256(content).hexdigest()), patch('setup.urllib.request.urlopen', return_value=binary_io.BytesIO(content)), patch('setup.subprocess.run', side_effect=AssertionError('must not build')):
            with self.assertRaises(tarfile.TarError):
                setup.build_headsetcontrol()
            self.assertFalse((Path(tmp) / 'escape').exists())


if __name__ == '__main__':
    unittest.main()
