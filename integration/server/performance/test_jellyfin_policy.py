import tempfile
from pathlib import Path
import unittest
import jellyfin_policy as p

class Tests(unittest.TestCase):
    def api(self):
        self.config={'TagCacheServerMode':True,'Ratings':True,'Requests':'unchanged'};self.writes=[]
        def request(method,path,data=None):
            if path=='System/Info/Public':return {'Version':p.SERVER}
            if path=='Plugins':return [{'Name':'Jellyfin Enhanced','Version':p.PLUGIN,'Status':'Active','Id':'fake'}]
            if method=='POST':self.writes.append(data);self.config=data
            return self.config
        return request
    def test_plan_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            journal=Path(d)/'journal';result=p.deploy(self.api(),journal)
            self.assertEqual(result['changes'],['TagCacheServerMode']);self.assertFalse(journal.exists());self.assertFalse(self.writes)
    def test_apply_preserves_all_other_fields_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            journal=Path(d)/'journal';api=self.api();p.deploy(api,journal,True)
            self.assertEqual(self.config,{'TagCacheServerMode':False,'Ratings':True,'Requests':'unchanged'})
            self.assertEqual(journal.stat().st_mode&0o777,0o600)
            self.assertEqual(p.deploy(api,journal,True)['changes'],[])
    def test_versions_fail_closed(self):
        def wrong(method,path,data=None):return {'Version':'future'}
        with self.assertRaises(ValueError):p.deploy(wrong,Path('/unused'))
    def test_unknown_policy_shape(self):
        for value in ({},{'TagCacheServerMode':'true'}):
            with self.assertRaises(ValueError):p.proposed(value)

if __name__=='__main__':unittest.main()
