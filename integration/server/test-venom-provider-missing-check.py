import runpy
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

m=runpy.run_path(str(Path(__file__).with_name('venom-provider-missing-check.py')))

class MissingTests(unittest.TestCase):
    def test_fresh_absence_and_reappearance(self):
        now=1_000_000
        rows=[(1,now-10,0),(1,now,1),(2,now-40*3600,0),(3,now,0),(4,now,None),(5,now+1,0)]
        self.assertEqual(m['fresh_absences'](rows,now),[3])
    def test_idle_requires_authenticated_active_account_and_explicit_zero(self):
        good={'auth':1,'status':'Active','active_cons':'0'}
        self.assertTrue(m['provider_idle']({'user_info':good}))
        for change in ({'auth':0},{'status':'Expired'},{'active_cons':1},{'active_cons':None}):
            self.assertFalse(m['provider_idle']({'user_info':{**good,**change}}))
        self.assertFalse(m['provider_idle']({}))
    def test_only_origin_missing_status_qualifies(self):
        origin=('http','provider',8080)
        for code in (200,301,401,403,429,500,503):
            self.assertIsNone(m['missing_status'](code,origin,origin))
        self.assertEqual(m['missing_status'](404,origin,origin),404)
        self.assertEqual(m['missing_status'](410,origin,origin),410)
        self.assertIsNone(m['missing_status'](404,('http','cdn',8080),origin))
    def test_control_requires_successful_decoding(self):
        for code,frames,expected in ((0,0,False),(1,3,False),(0,3,True)):
            with patch.object(m['subprocess'],'run',return_value=SimpleNamespace(returncode=code,stdout='frame='+str(frames))):
                self.assertEqual(m['control_decodes']('http://unused'),expected)

if __name__=='__main__':unittest.main()
