import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('media_forward', Path(__file__).with_name('media_forward.py'))
media_forward = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media_forward)

CONFIG = {'bridge_hostname': 'example-bridge', 'client_ipv4': '100.64.0.10',
          'overlay_ipv4': '100.64.0.20', 'backend_ipv4': '192.168.42.10'}


class MediaForwardTests(unittest.TestCase):
    def test_nat_is_exact_tcp_tuple_and_preserves_source(self):
        text = media_forward.render_nat(CONFIG, '')
        self.assertIn('-s 100.64.0.10/32 -d 100.64.0.20/32 -i tailscale0 -p tcp -m tcp --dport 2049', text)
        self.assertIn('DNAT --to-destination 192.168.42.10:2049', text)
        self.assertNotIn('SNAT', text)
        self.assertNotIn('MASQUERADE', text)
        self.assertNotIn(':PREROUTING', text)

    def test_filter_requires_post_nat_and_original_destination(self):
        text = media_forward.render_filter(CONFIG, '')
        self.assertIn('-s 100.64.0.10/32 -d 192.168.42.10/32 -p tcp -m tcp --dport 2049', text)
        self.assertIn('--ctorigdst 100.64.0.20 --ctorigdstport 2049', text)
        self.assertIn('--ctstate NEW,ESTABLISHED -j ACCEPT', text)
        self.assertEqual(text.count('-I INPUT 1 '), 2)
        self.assertIn('-p udp -m udp --dport 2049 -j AM9NFS_INPUT', text)
        self.assertTrue(text.rstrip().endswith('COMMIT'))

    def test_ipv6_denies_nfs_without_exception(self):
        text = media_forward.render_filter(CONFIG, '', ipv6=True)
        self.assertNotIn('100.64', text)
        self.assertNotIn('--ctorigdst', text)
        self.assertNotIn('-j ACCEPT', text)
        self.assertEqual(text.count('-I INPUT 1 '), 2)
        self.assertIn('-A AM9NFS_INPUT -j DROP', text)

    def test_emergency_block_removes_authorized_exception(self):
        text = media_forward.render_filter(CONFIG, '', block_all=True)
        self.assertNotIn('-j ACCEPT', text)
        self.assertIn('-A AM9NFS_INPUT -j DROP', text)

    def test_reapply_deletes_only_own_duplicate_hooks(self):
        old = ('-A INPUT -j ts-input\n'
               '-A INPUT -i tailscale0 -p tcp -m tcp --dport 2049 -j AM9NFS_INPUT\n'
               '-A INPUT -i tailscale0 -p tcp -m tcp --dport 2049 -j AM9NFS_INPUT\n')
        text = media_forward.render_filter(CONFIG, old)
        self.assertEqual(text.count('-D INPUT -i tailscale0 -p tcp -m tcp --dport 2049 -j AM9NFS_INPUT'), 2)
        self.assertNotIn('-D INPUT -j ts-input', text)

    def test_nat_reconcile_matches_actual_legacy_save_order(self):
        hook = '-s 100.64.0.10/32 -d 100.64.0.20/32 -i tailscale0 -p tcp -m tcp --dport 2049 -j AM9NFS_DNAT'
        existing = ('-A PREROUTING '+hook+'\n')*5+'-A PREROUTING -j DOCKER\n'
        plan = media_forward.render_nat(CONFIG, existing)
        self.assertEqual(plan.count('-D PREROUTING '+hook),5)
        self.assertEqual(plan.count('-I PREROUTING 1 '+hook),1)
        self.assertNotIn('-D PREROUTING -j DOCKER',plan)
        rollback = media_forward.render_remove(existing,'nat',media_forward.NAT_CHAIN,media_forward.nat_hooks(CONFIG))
        self.assertEqual(rollback.count('-D PREROUTING '+hook),5)

    def test_removal_keeps_unrelated_rules(self):
        old = (':AM9NFS_INPUT - [0:0]\n-A INPUT -j ts-input\n'
               '-A INPUT -i tailscale0 -p udp -m udp --dport 2049 -j AM9NFS_INPUT\n')
        text = media_forward.render_remove(old, 'filter', media_forward.FILTER_CHAIN,
                                           media_forward.filter_hooks())
        self.assertIn('-F AM9NFS_INPUT', text)
        self.assertIn('-X AM9NFS_INPUT', text)
        self.assertNotIn('ts-input', text)

    def test_rejects_broad_or_ambiguous_profile(self):
        for value in ('8.8.8.8', '192.168.1.10', '100.64.0.0/10', '100.64.0.10;id', '::1'):
            with self.assertRaises(ValueError):
                media_forward.validate({**CONFIG, 'client_ipv4': value})
        with self.assertRaises(ValueError):
            media_forward.validate({**CONFIG, 'backend_ipv4': '100.64.0.30'})
        with self.assertRaises(ValueError):
            media_forward.validate({**CONFIG, 'extra': 'no'})

    def test_ready_requires_exact_chain_and_pre_tailscale_order(self):
        ready = ('-A INPUT -i tailscale0 -p udp -m udp --dport 2049 -j AM9NFS_INPUT\n'
                 '-A INPUT -i tailscale0 -p tcp -m tcp --dport 2049 -j AM9NFS_INPUT\n'
                 '-A INPUT -j ts-input\n'
                 '-A AM9NFS_INPUT -s 100.64.0.10/32 -d 192.168.42.10/32 -p tcp -m tcp --dport 2049 '
                 '-m conntrack --ctorigdst 100.64.0.20 --ctorigdstport 2049 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT\n'
                 '-A AM9NFS_INPUT -j DROP\n')
        self.assertTrue(media_forward.filter_ready(CONFIG, ready))
        wrong_order = ('-A INPUT -j ts-input\n' + ready.replace('-A INPUT -j ts-input\n', '', 1))
        self.assertFalse(media_forward.filter_ready(CONFIG, wrong_order))
        self.assertFalse(media_forward.filter_ready(CONFIG, ready.replace('--ctorigdst 100.64.0.20', '--ctorigdst 100.64.0.21')))


if __name__ == '__main__':
    unittest.main()
