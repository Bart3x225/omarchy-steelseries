import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class RuntimeTests(unittest.TestCase):
    def test_xdg_paths_and_default_venv_compatibility(self):
        import runtime
        with patch.dict(os.environ, {'XDG_DATA_HOME': '/example/data'}):
            self.assertEqual(runtime.data_dir(), Path('/example/data/omarchy-steelseries'))
            self.assertEqual(runtime.mouse_python(), Path('/example/data/omarchy-steelseries/venv/bin/python'))
        with patch.dict(os.environ, {'XDG_DATA_HOME': ''}):
            self.assertEqual(runtime.mouse_python(), Path.home() / '.local/share/omarchy-steelseries/venv/bin/python')

    def test_apply_requires_receipt_and_checks_current_binary(self):
        import runtime
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp, 'PATH': ''}):
            binary = runtime.headset_dir() / 'bin/headsetcontrol'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'unit-test executable')
            binary.chmod(0o700)
            self.assertIsNone(runtime.headsetcontrol())
            with self.assertRaises(ValueError):
                runtime.headsetcontrol(for_apply=True)
            receipt = dict(source_commit=runtime.HEADSET_COMMIT,
                           source_archive_sha256=runtime.HEADSET_ARCHIVE_SHA256,
                           patch_sha256=runtime.HEADSET_PATCH_SHA256,
                           binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
            (runtime.headset_dir() / 'receipt.json').write_text(json.dumps(receipt))
            self.assertEqual(runtime.headsetcontrol(for_apply=True), binary)
            self.assertEqual(runtime.headsetcontrol(), binary)
            binary.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                runtime.headsetcontrol(for_apply=True)
            receipt['source_commit'] = 'unreviewed'
            (runtime.headset_dir() / 'receipt.json').write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):
                runtime.headsetcontrol(for_apply=True)

    def test_path_backend_is_never_trusted(self):
        import runtime
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}):
            binary = Path(tmp) / 'headsetcontrol'
            binary.write_text('#!/bin/sh\nexit 0\n')
            binary.chmod(0o700)
            with patch.dict(os.environ, {'PATH': tmp}):
                self.assertIsNone(runtime.headsetcontrol())
                with self.assertRaises(ValueError):
                    runtime.headsetcontrol(for_apply=True)
            binary.unlink()
            with patch.dict(os.environ, {'PATH': tmp}):
                self.assertIsNone(runtime.headsetcontrol())

    def test_controls_capabilities_are_pure_with_pinned_runtime(self):
        import controls
        import runtime
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}), patch('subprocess.Popen', side_effect=AssertionError('hardware query')):
            binary = runtime.headset_dir() / 'bin/headsetcontrol'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'unit test')
            binary.chmod(0o700)
            (runtime.headset_dir() / 'receipt.json').write_text(json.dumps(dict(
                source_commit=runtime.HEADSET_COMMIT,
                source_archive_sha256=runtime.HEADSET_ARCHIVE_SHA256,
                patch_sha256=runtime.HEADSET_PATCH_SHA256,
                binary_sha256=runtime.sha256_file(binary))))
            device = dict(id_vendor='0x1038', id_product='0x2232')
            self.assertEqual(len(controls.capabilities(device)), 3)
            binary.write_bytes(b'changed')
            self.assertEqual(controls.capabilities(device), [])

    def test_unpatched_receipt_is_rejected_for_polling_and_apply(self):
        import runtime
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp, 'PATH': ''}):
            binary = runtime.headset_dir() / 'bin/headsetcontrol'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'old backend')
            binary.chmod(0o700)
            receipt = dict(source_commit=runtime.HEADSET_COMMIT,
                           source_archive_sha256=runtime.HEADSET_ARCHIVE_SHA256,
                           binary_sha256=runtime.sha256_file(binary))
            (runtime.headset_dir() / 'receipt.json').write_text(json.dumps(receipt))
            self.assertIsNone(runtime.headsetcontrol())
            with self.assertRaises(ValueError):
                runtime.headsetcontrol(for_apply=True)

    def test_polling_adapters_use_runtime_backend(self):
        import fleet
        import subprocess
        with patch('runtime.headsetcontrol', return_value=Path('/test/backend')), patch('fleet.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"devices": []}', '')) as run:
            self.assertEqual(fleet.read_headsets(), {'devices': []})
            self.assertEqual(run.call_args.args[0][0], '/test/backend')


if __name__ == '__main__':
    unittest.main()
