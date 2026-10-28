import configparser
from pathlib import Path
import unittest


class ReconciliationUnitTests(unittest.TestCase):
    def test_oneshot_has_bounded_readiness_race_retries_without_guard_bypass(self):
        path = Path(__file__).parent / 'systemd/am9-nfs-forward.service'
        unit = configparser.ConfigParser(interpolation=None)
        unit.read(path)
        self.assertEqual(unit['Service']['Type'], 'oneshot')
        self.assertEqual(unit['Service']['Restart'], 'on-failure')
        self.assertEqual(unit['Service']['RestartSec'], '3s')
        self.assertEqual(unit['Service']['TimeoutStartSec'], '30s')
        self.assertEqual(unit['Unit']['StartLimitBurst'], '8')
        self.assertEqual(unit['Unit']['StartLimitIntervalSec'], '10min')
        self.assertIn('tailscaled.service', unit['Unit']['After'].split())
        command = unit['Service']['ExecStart']
        self.assertIn('--reconcile', command)
        self.assertIn('--config /etc/am9-nfs-forward/profile.json', command)
        self.assertNotIn('--apply-nat', command)
        self.assertNotIn('||', command)
        self.assertFalse(command.startswith('-'))


if __name__ == '__main__':
    unittest.main()
