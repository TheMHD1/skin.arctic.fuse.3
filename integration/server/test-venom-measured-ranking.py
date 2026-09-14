import runpy,unittest
from pathlib import Path
m=runpy.run_path(str(Path(__file__).with_name('venom-measured-ranking.py')))
def record(height,depth=8,transfer=None):
    return {'time':100,'result':'working','decoded_frame_variants':[{'height':height,'component_bit_depths':[depth]*3,'color_transfer':transfer,'color_primaries':'bt2020' if transfer else None}],'video_sample_statistics':[{'observed_frame_rate':50}]}
class Tests(unittest.TestCase):
    def test_real_quality_not_label(self):
        a,_=m['measure']({'stream_id':1,'name':'FAKE 8K'},record(720),101)
        b,_=m['measure']({'stream_id':2,'name':'Actual HD'},record(1080),101)
        self.assertLess(b,a)
    def test_unknown_and_8bit_hlg_no_hdr_bonus(self):
        for transfer in [None,'arib-std-b67']:
            _,r=m['measure']({'stream_id':1,'name':'HDR'},record(720,8,transfer),101)
            self.assertEqual(r['colour_tier'],0)
        _,r=m['measure']({'stream_id':1,'name':'HDR'},record(1080,10,'smpte2084'),101)
        self.assertEqual(r['colour_tier'],3)
    def test_groups_bounded_conserved_and_repeatable(self):
        rows=[{'stream_id':i,'name':'BEIN SPORTS '+str(i)} for i in range(230)]+[{'stream_id':999,'name':'SKY GOLF HD'}]
        source={'groups':[{'id':'ar-sport','name':'Sports','channels':rows}]};audit={'channels':{str(c['stream_id']):record(1080) for c in rows}}
        out,_=m['apply'](source,audit,101);again,_=m['apply'](out,audit,101)
        self.assertEqual(out,again)
        self.assertEqual(out['unique_channels'],231)
        self.assertLessEqual(max(len(g['channels']) for g in out['groups']),100)
        self.assertTrue(any(g['id']=='sport-golf' for g in out['groups']))
if __name__=='__main__':unittest.main()
