import json,unittest
from rpc_stream import read_response
class Socket:
    def __init__(self,chunks):self.chunks=iter(chunks)
    def recv(self,size):return next(self.chunks,b'')
class Tests(unittest.TestCase):
    def test_announcement_and_response_coalesced_or_split(self):
        raw=b'{"method":"Player.OnStop","params":{}} {"id":1,"result":"OK"}'
        for chunks in ([raw],[raw[:7],raw[7:43],raw[43:]], [bytes([b]) for b in raw]):
            self.assertEqual(read_response(Socket(chunks)),{'id':1,'result':'OK'})
    def test_arabic_utf8_split_in_multibyte_characters(self):
        response={'id':1,'result':{'label':'أخبار عربية'}};raw=json.dumps(response,ensure_ascii=False).encode()
        self.assertEqual(read_response(Socket([bytes([b]) for b in raw])),response)
    def test_unrelated_id_is_ignored_and_rpc_error_is_returned(self):
        self.assertEqual(read_response(Socket([b'{"id":2,"result":"other"}{"id":1,"error":{"code":-1}}'])),
                         {'id':1,'error':{'code':-1}})
    def test_eof_and_byte_limit_fail_bounded(self):
        with self.assertRaisesRegex(RuntimeError,'Incomplete'):read_response(Socket([b'{"id":1']))
        with self.assertRaisesRegex(RuntimeError,'byte limit'):read_response(Socket([b' '*11]),max_bytes=10)
if __name__=='__main__':unittest.main()
