import runpy
from pathlib import Path
import unittest
from unittest.mock import patch
import types

m=runpy.run_path(str(Path(__file__).with_name('venom-channel-checker.py')))

class CheckerTests(unittest.TestCase):
    def test_long_retry_is_not_cut_off_by_twenty_second_read_timeout(self):
        with patch.object(m['subprocess'],'run',return_value=types.SimpleNamespace(returncode=0,stdout='frame=3\n',stderr='')) as call:
            for seconds in (22,55):
                m['probe']('http://unused',seconds)
                argv=call.call_args[0][0]
                self.assertEqual(argv[argv.index('-rw_timeout')+1],str(seconds*1000000))
                self.assertEqual(argv[argv.index('--kill-after=3')+1],str(seconds))
                self.assertEqual(call.call_args.kwargs['timeout'],seconds+8)
    def test_geometry_comes_from_decoded_pre_scale_frames(self):
        log='Input http://secret/3840x2160\n[Parsed_showinfo_0 @ 0x123] n:   0 pts: 42 fmt:yuv420p sar:1/1 s:1920x1080 i:P\nOutput 16x16'
        self.assertEqual(m['decoded_geometry'](log),{'decoded_width':1920,'decoded_height':1080})
        self.assertEqual(m['decoded_geometry']('Video: 3840x2160 http://secret'),{})
        self.assertEqual(m['decoded_geometry']('[Parsed_showinfo_1 @ 0x1] n:0 s:16x16'),{})
        self.assertEqual(m['decoded_geometry']('[Parsed_showinfo_0 @ 0x1] n:0 s:999999x1080'),{})
    def empty(self):return {'live':{'channels':[],'count':0},'vod':{'vod_connections':[],'total_connections':0},'catchup':{'timeshift_sessions':[],'total_connections':0}}
    def test_requires_known_idle_shape(self):
        self.assertFalse(m['occupied'](self.empty()))
        self.assertTrue(m['occupied']({}))
        for section in ('live','vod','catchup'):
            stats=self.empty();stats[section]={}
            self.assertTrue(m['occupied'](stats))
    def test_each_playback_type_blocks_probe(self):
        for section,key in [('live','count'),('vod','total_connections'),('catchup','total_connections')]:
            stats=self.empty();stats[section][key]=1
            self.assertTrue(m['occupied'](stats))
    def test_http_success_without_frames_not_working(self):
        with patch.object(m['subprocess'],'run',return_value=types.SimpleNamespace(returncode=0,stdout='frame=0\n',stderr='')):
            self.assertEqual(m['probe']('http://unused',22)['result'],'inconclusive_playback')
    def test_real_decoding_required_and_urls_not_returned(self):
        with patch.object(m['subprocess'],'run',return_value=types.SimpleNamespace(returncode=0,stdout='frame=3\n',stderr='secret')) as call:
            result=m['probe']('http://unused/secret',22)
            self.assertEqual(result['result'],'working');self.assertNotIn('secret',str(result))
            self.assertIn('timeout',call.call_args[0][0])

if __name__=='__main__':unittest.main()
