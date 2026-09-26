import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('firewall',Path(__file__).with_name('firewall.py'))
firewall=importlib.util.module_from_spec(spec);spec.loader.exec_module(firewall)
CONFIG={'hostname':'example-am9','wifi_mac':'02:00:00:00:00:01',
        'admin_ipv4':'100.64.0.10','media_ipv4':'100.64.0.20'}


class FirewallTests(unittest.TestCase):
    def test_exact_admin_and_media_ports_only(self):
        text=firewall.render(CONFIG,'')
        self.assertIn('-s 100.64.0.10/32 -p tcp --dport 22',text)
        self.assertIn('-d 100.64.0.20/32 -p tcp --dport 2049',text)
        self.assertEqual(text.count('--dport'),2)
        self.assertNotIn('100.64.0.0/10',text)
        self.assertIn('-A AM9TS_FWD -j DROP',text)
        self.assertNotIn(':INPUT',text)
        self.assertNotIn('-P ',text)
        self.assertNotIn('RELATED',text)
        for line in text.splitlines():
            if 'ESTABLISHED' in line:
                self.assertTrue('-s ' in line or '-d ' in line)
                self.assertTrue('--sport ' in line or '--dport ' in line)
        for line in text.splitlines():
            if line.startswith(('-I ','-D ')):self.assertIn('tailscale0',line)

    def test_reapply_replaces_only_own_jumps(self):
        old='-A INPUT -j EXISTING\n-A INPUT -i tailscale0 -j AM9TS_IN\n'
        text=firewall.render(CONFIG,old)
        self.assertEqual(text.count('-D INPUT -i tailscale0 -j AM9TS_IN'),1)
        self.assertNotIn('EXISTING',text)
        self.assertEqual(text.count('-I INPUT 1 -i tailscale0 -j AM9TS_IN'),1)

    def test_ipv6_has_no_new_connection_exceptions(self):
        text=firewall.render(CONFIG,'',True)
        self.assertNotIn('--dport',text)
        self.assertNotIn('echo-request',text)
        self.assertEqual(text.count('-j DROP'),5)

    def test_reject_ambiguous_or_public_peers(self):
        for value in ('8.8.8.8','192.168.1.10','100.64.0.0/10','100.64.0.10;echo x','::1'):
            with self.assertRaises(ValueError):firewall.render({**CONFIG,'admin_ipv4':value},'')
        with self.assertRaises(ValueError):firewall.render({**CONFIG,'media_ipv4':CONFIG['admin_ipv4']},'')
        with self.assertRaises(ValueError):firewall.render({**CONFIG,'extra':'anything'},'')


if __name__=='__main__':unittest.main()
