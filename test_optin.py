"""Publication safety: hardware writes are opt-in, not a default side effect."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import app
import prefs

class OptInTests(unittest.TestCase):
    def test_default_controls_off(self):
        self.assertIs(prefs.DEFAULTS.get('experimentalControls'), False)

    def test_disabled_apply_rejects_before_collect(self):
        calls=[]
        fakefleet=SimpleNamespace(collect_all=lambda:(calls.append('collect') or {'devices':[]}))
        with patch.object(prefs,'load_config',return_value={**prefs.DEFAULTS,'experimentalControls':False}),patch.dict('sys.modules',{'fleet':fakefleet}):
            with self.assertRaisesRegex(ValueError,'[Ee]xperimental'):
                app.execute_command('apply',['device','{"dpi":800}'])
        self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
