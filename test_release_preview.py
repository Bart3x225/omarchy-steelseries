"""Regression coverage for the narrowly scoped marketplace PNG exception."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('release_audit', ROOT / 'scripts/check-release.py')
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class PreviewAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('manifest.json', 'LICENSE', 'README.md', 'controls.py', 'Panel.qml'):
            shutil.copyfile(ROOT / name, self.root / name)
        self.png = (ROOT / 'preview.png').read_bytes()

    def test_root_preview_is_publishable(self):
        (self.root / 'preview.png').write_bytes(self.png)
        self.assertEqual(AUDIT.audit(self.root), [])

    def test_other_images_remain_blocked(self):
        for name in ('image.png', 'docs/preview.png'):
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(self.png)
                self.assertTrue(any(name in error for error in AUDIT.audit(self.root)))
                path.unlink()

    def test_executable_disguised_as_preview_is_blocked(self):
        (self.root / 'preview.png').write_bytes(b'\x7fELF\0not a PNG')
        self.assertTrue(AUDIT.audit(self.root))

    def test_preview_dimension_limits(self):
        for width, height in ((0, 1), (1, 0), (10000, 10000)):
            with self.subTest(width=width, height=height):
                header = self.png[:16] + width.to_bytes(4, 'big') + height.to_bytes(4, 'big')
                (self.root / 'preview.png').write_bytes(header)
                self.assertTrue(any('dimensions' in error for error in AUDIT.audit(self.root)))

    def test_oversized_preview_is_blocked(self):
        with (self.root / 'preview.png').open('wb') as image:
            image.write(self.png)
            image.truncate(50_000_001)
        self.assertTrue(any('50 MB' in error for error in AUDIT.audit(self.root)))

    def test_symlink_preview_remains_blocked(self):
        (self.root / 'preview.png').symlink_to(self.root / 'LICENSE')
        self.assertTrue(any('symlinks' in error for error in AUDIT.audit(self.root)))


if __name__ == '__main__':
    unittest.main()
