import importlib.util,shlex,unittest
from pathlib import Path

path=Path(__file__).with_name('profile_update.py');spec=importlib.util.spec_from_file_location('profile_update',path)
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)

class ProfileTests(unittest.TestCase):
    def test_change_is_one_bounded_input_only_retry_set(self):
        self.assertEqual(profile.NEW.count(profile.OPTIONS),1)
        self.assertEqual(profile.NEW.replace(' '+profile.OPTIONS,''),profile.OLD)
        values=shlex.split(profile.NEW)
        self.assertEqual(values[values.index('-reconnect_on_http_error')+1],'403')
        self.assertEqual(values[values.index('-reconnect_max_retries')+1],'4')
        self.assertEqual(values[values.index('-reconnect_delay_max')+1],'7')
        self.assertEqual(values[values.index('-reconnect_delay_total_max')+1],'11')
        self.assertEqual(values[-6:],['-map','0:v:0?','-map','0:a?','-c','copy','-f','mpegts','pipe:1'][-6:])
    def test_no_embedded_secret(self):
        source=path.read_text();self.assertNotIn('admin_password":',source);self.assertIn('/data/venom-credentials.json',source)
if __name__=='__main__':unittest.main()
