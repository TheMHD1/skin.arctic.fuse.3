import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('policy', Path(__file__).with_name('policy.py'))
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class PolicyTests(unittest.TestCase):
    def test_bands(self):
        for frequency in (5180, 5500, 5785, 5825):
            self.assertTrue(policy.is_5ghz(frequency))
        for frequency in (2412, 2462, 5925, 5975):
            self.assertFalse(policy.is_5ghz(frequency))

    def test_legal_channels_only(self):
        self.assertEqual(policy.allowed_frequencies('''
 * 2412.0 MHz [1] (20 dBm)
 * 5180.0 MHz [36] (20 dBm)
 * 5500.0 MHz [100] (20 dBm) (radar detection)
 * 5785.0 MHz [157] (disabled)
 * 5975.0 MHz [5] (20 dBm)
'''), [5180, 5500])

    def test_exact_ssid_and_strongest_5ghz(self):
        scan = '''BSS 02:00:00:00:00:01(on wlan0)
 freq: 2412
 signal: -20.00 dBm
 SSID: Example
BSS 02:00:00:00:00:02(on wlan0)
 freq: 5785
 signal: -45.00 dBm
 SSID: Example
BSS 02:00:00:00:00:03(on wlan0)
 freq: 5180
 signal: -30.00 dBm
 SSID: Example
BSS 02:00:00:00:00:04(on wlan0)
 freq: 5785
 signal: -10.00 dBm
 SSID: Example neighbour
'''
        self.assertEqual(policy.scan_candidates(scan, 'Example'),
                         [(-30.0, '02:00:00:00:00:03'), (-45.0, '02:00:00:00:00:02')])
        self.assertEqual(policy.scan_candidates(scan, 'Absent'), [])

    def test_incomplete_scans_are_not_candidates(self):
        self.assertEqual(policy.scan_candidates('BSS 02:00:00:00:00:01(on wlan0)\n SSID: Example\n', 'Example'), [])

    def test_stale_ap_is_not_roamed_to(self):
        scan = 'BSS 02:00:00:00:00:02(on wlan0)\n freq: 5785\n signal: -40.00 dBm\n SSID: Example\n last seen: 300000 ms ago\n'
        self.assertEqual(policy.scan_candidates(scan, 'Example'), [])

    def test_network_ssid_not_substring_or_secret(self):
        self.assertEqual(policy.network_ssid({'ssid': {'data': '"Example"'}, 'psk': {'data': 'secret'}}), 'Example')
        self.assertIsNone(policy.network_ssid({}))

    def test_property_changes_only_freq_list(self):
        with patch.object(policy, 'run') as run:
            policy.set_frequencies('/network', '5180 5785')
        self.assertEqual(run.call_args.args[-5:], ('a{sv}', '1', 'freq_list', 's', '5180 5785'))

    def exercise(self, frequency=2412, scan='', roam_fails=False, mac='02:00:00:00:00:01', state=None):
        calls = []
        props = {'ssid': {'data': '"Example"'}, 'freq_list': {'data': ''}}
        self.last_calls, self.last_properties = calls, props
        config = {'hostname': 'example-am9', 'interface': 'wlan0', 'mac': '02:00:00:00:00:01', 'country': 'CA', 'ssid': 'Example'}
        def read(path):
            return 'example-am9' if path.name == 'hostname' else mac
        def prop(path, interface, name):
            return {'Interfaces': ['/interface'], 'Ifname': 'wlan0', 'Country': 'CA',
                    'Networks': ['/network'], 'Properties': props, 'Scanning': False}[name]
        def run(*args):
            nonlocal frequency
            calls.append(args)
            if args[:3] == ('iw', 'phy', 'phy0'):
                return '* 5180.0 MHz [36] (20 dBm)\n* 5785.0 MHz [157] (20 dBm)'
            if args[-1] == 'link':
                return 'Connected\n SSID: Example\n freq: ' + str(frequency)
            if args[-1] == 'dump':
                return scan
            if 'freq_list' in args:
                props['freq_list']['data'] = args[-1]
            if 'Roam' in args:
                if roam_fails:
                    raise RuntimeError('driver rejected roam')
                frequency = 5785
            return ''
        with patch.object(Path, 'read_text', read), patch.object(Path, 'resolve', return_value=Path('phy0')), \
             patch.object(policy, 'prop', prop), patch.object(policy, 'run', run), patch.object(policy.time, 'sleep'):
            result = policy.apply(config, {} if state is None else state)
        return result, calls, props

    def test_missing_ap_preserves_remote_access(self):
        result, calls, props = self.exercise()
        self.assertIn('not-visible', result)
        self.assertFalse(any('Roam' in x or 'freq_list' in x for x in calls))
        self.assertEqual(props['freq_list']['data'], '')

    def test_active_5ghz_restricts_without_scan_or_disconnect(self):
        state = {}
        result, calls, props = self.exercise(frequency=5785, state=state)
        self.assertIn('5ghz-active', result)
        self.assertEqual(props['freq_list']['data'], '5180 5785')
        self.assertTrue(state['owns_restriction'])
        self.assertFalse(any('Scan' in x or 'Roam' in x or 'Reconnect' in x for x in calls))

    def test_roam_acceptance(self):
        scan = 'BSS 02:00:00:00:00:02(on wlan0)\n freq: 5785\n signal: -40.00 dBm\n SSID: Example\n'
        result, calls, props = self.exercise(scan=scan)
        self.assertEqual(result, '5ghz-roam-accepted')
        self.assertEqual(props['freq_list']['data'], '5180 5785')
        self.assertFalse(any('Reconnect' in x for x in calls))

    def test_roam_exception_restores_original_selection(self):
        scan = 'BSS 02:00:00:00:00:02(on wlan0)\n freq: 5785\n signal: -40.00 dBm\n SSID: Example\n'
        with self.assertRaises(RuntimeError):
            self.exercise(scan=scan, roam_fails=True)
        self.assertEqual(self.last_properties['freq_list']['data'], '')
        self.assertTrue(any('Reconnect' in x for x in self.last_calls))

    def test_foreign_radio_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.exercise(mac='02:00:00:00:00:09')

    def test_cooldown_avoids_repeat_scans(self):
        result, calls, props = self.exercise(state={'next_attempt': policy.time.monotonic() + 300})
        self.assertEqual(result, 'retry-cooldown')
        self.assertFalse(any('Scan' in x for x in calls))


if __name__ == '__main__':
    unittest.main()
