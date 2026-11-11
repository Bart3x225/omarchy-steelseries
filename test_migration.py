import json
from pathlib import Path
import tempfile
import unittest

class MigrationTests(unittest.TestCase):
    def fixture(self,root):
        import migrate
        config=root/'config';plugins=config/'omarchy/plugins';new=plugins/'bart.steelseries';old=plugins/'bart.nova5'
        new.mkdir(parents=True);old.mkdir();(new/'manifest.json').write_text(json.dumps({'id':'bart.steelseries'}));(old/'marker').write_text('keep')
        shell=config/'omarchy/shell.json';data={'bar':{'layout':{'right':[{'id':'omarchy.audio'},{'id':'bart.nova5','custom':True}]}},'disabledPlugins':['unrelated']};shell.write_text(json.dumps(data));return config,shell,old,data

    def test_dry_run_and_apply_preserve_layout(self):
        self.assertTrue(Path(__file__).with_name('migrate.py').exists(),'Migration implementation missing')
        import migrate
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config,shell,old,before=self.fixture(root);backup=root/'backups'
            plan=migrate.migrate(config,apply=False,backup_root=backup)
            self.assertTrue(plan['changed']);self.assertTrue(old.exists());self.assertEqual(json.loads(shell.read_text()),before);self.assertFalse(backup.exists())
            result=migrate.migrate(config,apply=True,backup_root=backup)
            after=json.loads(shell.read_text());self.assertEqual(after['bar']['layout']['right'][1],{'id':'bart.steelseries','custom':True});self.assertFalse(old.exists());self.assertEqual((Path(result['backup'])/'bart.nova5/marker').read_text(),'keep');self.assertEqual(json.loads((Path(result['backup'])/'shell.json').read_text()),before)
            self.assertFalse(migrate.migrate(config,apply=True,backup_root=backup)['changed'])

    def test_refuses_missing_canonical_installation(self):
        self.assertTrue(Path(__file__).with_name('migrate.py').exists(),'Migration implementation missing')
        import migrate
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):migrate.migrate(Path(tmp),apply=True)

if __name__=='__main__':unittest.main()
