"""Localhost-only FFmpeg test for the top-level HTTP retry contract."""
import collections,http.server,pathlib,shutil,subprocess,tempfile,threading,time,unittest

OPTIONS=('reconnect_on_http_error','reconnect_streamed','reconnect_delay_max','reconnect_max_retries','reconnect_delay_total_max')
class State:
    def __init__(self,segment):self.segment=segment;self.counts=collections.Counter();self.lock=threading.Lock()
    def hit(self,path):
        with self.lock:self.counts[path]+=1;return self.counts[path]
class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def do_GET(self):
        n=self.server.state.hit(self.path)
        if self.path=='/transient.m3u8' and n<=2:return self.reply(403,b'')
        if self.path in ('/permanent.m3u8','/cancel.m3u8'):return self.reply(403,b'')
        if self.path=='/unauthorized.m3u8':return self.reply(401,b'')
        if self.path=='/missing.m3u8':return self.reply(404,b'')
        if self.path=='/transient.m3u8':
            return self.reply(200,b'#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:1\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:1.0,\nsegment.ts\n#EXT-X-ENDLIST\n','application/vnd.apple.mpegurl')
        if self.path=='/segment.ts':return self.reply(200,self.server.state.segment,'video/mp2t')
        self.reply(404,b'')
    def reply(self,status,body,kind='text/plain'):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers()
        if body:self.wfile.write(body)
    def log_message(self,*_args):pass
class Server(http.server.ThreadingHTTPServer):daemon_threads=True;allow_reuse_address=True

class RetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg=shutil.which('ffmpeg')
        if not cls.ffmpeg:raise unittest.SkipTest('ffmpeg absent')
        help_=subprocess.run([cls.ffmpeg,'-hide_banner','-h','protocol=http'],capture_output=True,text=True,timeout=10)
        missing=[x for x in OPTIONS if '-'+x not in help_.stdout+help_.stderr]
        if missing:raise unittest.SkipTest('ffmpeg lacks: '+','.join(missing))
        cls.temp=tempfile.TemporaryDirectory();segment=pathlib.Path(cls.temp.name)/'segment.ts'
        made=subprocess.run([cls.ffmpeg,'-hide_banner','-loglevel','error',
            '-f','lavfi','-i','testsrc2=s=160x90:r=25',
            '-f','lavfi','-i','sine=frequency=1000:sample_rate=48000',
            '-t','2','-c:v','mpeg2video','-g','12','-c:a','mp2','-muxdelay','0',
            '-f','mpegts',str(segment)],capture_output=True,timeout=15)
        if made.returncode:raise RuntimeError('TS fixture failed')
        cls.state=State(segment.read_bytes());cls.server=Server(('127.0.0.1',0),Handler);cls.server.state=cls.state
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,'server'):cls.server.shutdown();cls.server.server_close();cls.thread.join(3)
        if hasattr(cls,'temp'):cls.temp.cleanup()
    def command(self,path):
        return [self.ffmpeg,'-hide_banner','-loglevel','warning','-reconnect_on_http_error','403','-reconnect_max_retries','4','-reconnect_delay_max','7','-reconnect_delay_total_max','11','-reconnect_streamed','1','-i',self.url+path,'-map','0','-f','null','-']
    def run_case(self,path,timeout=20):
        start=time.monotonic();result=subprocess.run(self.command(path),capture_output=True,text=True,timeout=timeout);return result,time.monotonic()-start
    def test_transient_recovers(self):
        result,elapsed=self.run_case('/transient.m3u8');self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(self.state.counts['/transient.m3u8'],3);self.assertGreater(self.state.counts['/segment.ts'],0);self.assertLess(elapsed,15)
    def test_permanent_is_five_requests(self):
        result,elapsed=self.run_case('/permanent.m3u8');self.assertNotEqual(result.returncode,0);self.assertEqual(self.state.counts['/permanent.m3u8'],5);self.assertGreaterEqual(elapsed,10);self.assertLess(elapsed,15)
    def test_other_statuses_not_retried(self):
        for path in ('/unauthorized.m3u8','/missing.m3u8'):
            result,elapsed=self.run_case(path);self.assertNotEqual(result.returncode,0);self.assertEqual(self.state.counts[path],1);self.assertLess(elapsed,3)
    def test_termination_interrupts_retry_sleep(self):
        process=subprocess.Popen(self.command('/cancel.m3u8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+5
        while self.state.counts['/cancel.m3u8']<3 and time.monotonic()<deadline:time.sleep(.02)
        self.assertGreaterEqual(self.state.counts['/cancel.m3u8'],3);start=time.monotonic();process.terminate();process.communicate(timeout=2);self.assertLess(time.monotonic()-start,2)
if __name__=='__main__':unittest.main()
