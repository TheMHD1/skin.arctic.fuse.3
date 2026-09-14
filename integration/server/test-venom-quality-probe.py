import runpy
import unittest
from pathlib import Path
m=runpy.run_path(str(Path(__file__).with_name('venom-quality-probe.py')))
class Tests(unittest.TestCase):
    def test_sample_statistics_are_explicit_estimates(self):
        frames=[{'media_type':'video','stream_index':0,'best_effort_timestamp_time':str(i/25),'pkt_size':'1000'} for i in range(126)]
        r=m['summarize']({'frames':frames},{})
        self.assertEqual(r['video_sample_statistics'][0]['observed_frame_rate'],25)
        self.assertEqual(r['video_sample_statistics'][0]['encoded_video_bitrate_estimate_bps'],200000)
    def test_hdr_requires_transfer_not_ten_bit(self):
        for transfer,want in [('smpte2084','hdr'),('arib-std-b67','hdr'),('bt709','sdr'),('unknown','unknown_transfer')]:
            f={'media_type':'video','width':1920,'height':1080,'pix_fmt':'yuv420p10le','color_transfer':transfer}
            r=m['summarize']({'frames':[f]*3}, {})
            self.assertEqual(r['classification'],want)
            self.assertEqual(len(r['decoded_frame_variants']),1)
    def test_no_frames_is_not_verified(self):
        r=m['summarize']({'streams':[{'codec_type':'video','color_transfer':'smpte2084'}]}, {})
        self.assertEqual(r['classification'],'inconclusive_playback')
    def test_side_data_and_no_urls(self):
        rows=[{'side_data_type':'DOVI configuration record','el_present_flag':1,'dv_profile':7,'url':'http://secret'}, {'side_data_type':'User Data Unregistered','text':'secret'}]
        self.assertEqual(m['side_data'](rows),[{'side_data_type':'DOVI configuration record','el_present_flag':1,'dv_profile':7}])
    def test_pixel_depth_from_descriptor(self):
        r=m['summarize']({'streams':[{'pix_fmt':'yuv420p','codec_type':'video'}]}, {'yuv420p':{'components':[{'bit_depth':8}]*3,'flags':{'rgb':0},'log2_chroma_w':1,'log2_chroma_h':1}})
        self.assertEqual(r['streams'][0]['component_bit_depths'],[8,8,8])
        self.assertEqual(r['streams'][0]['chroma_subsampling'],'4:2:0')
if __name__=='__main__':unittest.main()
