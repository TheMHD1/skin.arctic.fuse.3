import runpy
import unittest
from pathlib import Path
stage=runpy.run_path(str(Path(__file__).with_name('venom-stage-high-quality.py')))['stage']
class Tests(unittest.TestCase):
    def test_additive_idempotent_and_includes_mashhad(self):
        current={'groups':[{'id':'ar-news','name':'News','channels':[{'stream_id':99,'name':'User existing station'}]}]}
        source={'categories':[{'category_id':9,'category_name':'|AR| LEBANON'}],
                'channels':[{'stream_id':1,'category_id':9,'name':'LB : AL MASHHAD 8K'}]}
        result,added=stage(current,source)
        self.assertEqual([c['stream_id'] for c in result['groups'][0]['channels']],[99,1])
        self.assertEqual(len(added),1)
        again,added=stage(result,source)
        self.assertEqual(result,again)
        self.assertEqual(added,[])
if __name__=='__main__':unittest.main()
