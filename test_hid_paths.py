"""hidraw/libusb path compatibility must preserve exact physical targeting."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import runtime

class HidPathTests(unittest.TestCase):
    def test_maps_only_exact_interface(self):
        self.assertTrue(hasattr(runtime,'compatible_hid_path'),'HID backend path compatibility missing')
        with tempfile.TemporaryDirectory() as tmp:
            physical=Path(tmp)/'7-1.3';interface=physical/'7-1.3:1.3';interface.mkdir(parents=True);(interface/'bInterfaceNumber').write_text('03')
            for expected in [b'/dev/hidraw6',b'7-1.3:1.3']:
                module=SimpleNamespace(enumerate=lambda vid,pid:[{'path':b'7-1.4:1.3','interface_number':3},{'path':expected,'interface_number':3}])
                self.assertEqual(runtime.compatible_hid_path(physical,0x1852,b'/dev/hidraw6',hid_module=module),expected)
            with self.assertRaises(OSError):
                runtime.compatible_hid_path(physical,0x1852,b'/dev/hidraw6',hid_module=SimpleNamespace(enumerate=lambda *a:[{'path':b'7-1.4:1.3','interface_number':3}]))

if __name__=='__main__':unittest.main()
