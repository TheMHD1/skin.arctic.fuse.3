import runpy
from pathlib import Path
import unittest

m=runpy.run_path(str(Path(__file__).with_name('venom-name-guide-refresh.py')))

class RefreshTests(unittest.TestCase):
    def test_only_idle_changed_and_outside_cooldown(self):
        f=m['should_refresh'];now=100000
        self.assertTrue(f('Idle','new',{},now))
        for state in ('Running','Cancelling','Unknown'):
            self.assertFalse(f(state,'new',{},now))
        self.assertFalse(f('Idle','same',{'fingerprint':'same'},now))
        self.assertFalse(f('Idle','new',{'fingerprint':'old','requested_at':now-100},now))
        self.assertTrue(f('Idle','new',{'fingerprint':'old','requested_at':now-21600},now))

if __name__=='__main__':unittest.main()
