"""Guard artwork-only timeout tuning against accidentally shortening playback."""
from pathlib import Path
import re
import unittest

CONFIG=Path(__file__).with_name('dispatcharr-nginx.conf').read_text()

class ArtworkConfigTests(unittest.TestCase):
    def test_only_artwork_gets_short_timeout(self):
        blocks=re.findall(r'location ([^\n]+)\{\n(.*?)\n    }',CONFIG,re.S)
        short=[]
        for route,body in blocks:
            if 'proxy_read_timeout 5s;' in body:
                short.append(route)
                self.assertIn('proxy_cache ',body)
                self.assertIn('proxy_connect_timeout 2s;',body)
                self.assertIn('http_502 http_503 http_504',body)
                self.assertTrue(any(part in route for part in ('/logos/','/vodlogos/','/image/','/poster/')))
        self.assertEqual(len(short),4)
        self.assertIn('proxy_read_timeout 300;',CONFIG)
    def test_no_new_auth_bypass_or_placeholder(self):
        self.assertNotIn('proxy_ignore_headers',CONFIG)
        self.assertNotIn('error_page 404 =200',CONFIG)

if __name__=='__main__':unittest.main()
