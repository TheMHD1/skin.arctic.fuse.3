import runpy
import unittest
from pathlib import Path
extend=runpy.run_path(str(Path(__file__).with_name('venom-special-groups.py')))['extend']
priority=runpy.run_path(str(Path(__file__).with_name('venom-special-groups.py')))['priority']
class Tests(unittest.TestCase):
    def test_lebanon_candidates_and_working_publication(self):
        source={'categories':[dict(category_id='9',category_name='|AR| LEBANON لبنان')], 'channels':[dict(stream_id=i,name='MTV HD',category_id='9') for i in [1,2]]}
        staged=extend({'groups':[]},source,set(),{},True)
        self.assertEqual(len(staged['groups'][0]['channels']),2)
        published=extend({'groups':[]},source,{'1'},{})
        self.assertEqual(published['groups'][0]['id'],'ar-lebanon')
        self.assertEqual([c['stream_id'] for c in published['groups'][0]['channels']],[1])
    def test_6k_and_spaced_8k_resolution_order(self):
        rows=[{'name':n} for n in ['Station 4K','Station 6K','Station 8 K','Station 1440P','Station HDR HD']]
        self.assertEqual([c['name'] for c in sorted(rows,key=priority)],['Station HDR HD','Station 8 K','Station 6K','Station 4K','Station 1440P'])
    def test_hdr_first_then_resolution_and_duplicate_variants(self):
        rows=[{'name':s} for s in ['Station HD','Station 4K','Station 8K','Station FHD','Station 4K HDR','Station 8K HDR','Station FHD HDR']]
        self.assertEqual([r['name'] for r in sorted(rows,key=priority)],['Station 8K HDR','Station 4K HDR','Station FHD HDR','Station 8K','Station 4K','Station FHD','Station HD'])
        self.assertLess(priority({'name':'Provider 8K HDR','decoded_height':720,'decoded_hdr':False}),priority({'name':'Real FHD','decoded_height':1080,'decoded_hdr':False}))
    def test_label_order_and_hd_membership_survive_lower_measured_resolution(self):
        rows=[dict(stream_id=i,name=n) for i,n in enumerate(['Station 4K','Station 8K','Station 6K','Station HD'])]
        geometry={str(i):{'decoded_height':480,'decoded_width':720} for i in range(4)}
        result=extend({'groups':[dict(id='sport',name='Sport',channels=rows)]},{'categories':[],'channels':[]},set(),geometry)
        for group in result['groups']:
            self.assertEqual([c['stream_id'] for c in group['channels']],[1,2,0,3])
        self.assertEqual([g['id'] for g in result['groups']],['sport'])
        self.assertTrue(all(c['decoded_height']==480 for c in result['groups'][0]['channels']))
    def test_measured_quality_and_nonempty_lists(self):
        rows=[dict(stream_id=1,name='MBC 1 4K',category_id='5'),dict(stream_id=2,name='MBC 2 UHD',category_id='5')]
        source={'categories':[dict(category_id='5',category_name='|AR| MBC 4K')],'channels':rows}
        original={'groups':[dict(id='news',name='News',channels=rows)]}
        result=extend(original,source,{'1','2'},{'1':{'decoded_height':1080},'2':{'decoded_height':2160}})
        self.assertFalse(any(g.get('derived_quality') for g in result['groups']))
        self.assertEqual(len(next(g for g in result['groups'] if g['id']=='news')['channels']),2)
        self.assertEqual(result,extend(result,source,{'1','2'},{'1':{'decoded_height':1080},'2':{'decoded_height':2160}}))
        self.assertFalse(any(g['id']=='ar-syria' for g in result['groups']))
    def test_unprobed_candidates_not_published(self):
        source={'categories':[dict(category_id='8',category_name='|AR| SYRIA سوريا')],'channels':[dict(stream_id=3,name='SYRIA 4K',category_id='8')]}
        self.assertEqual(extend({'groups':[]},source,set(),{})['groups'],[])
        self.assertEqual(len(extend({'groups':[]},source,set(),{},True)['groups']),1)
if __name__=='__main__':unittest.main()
