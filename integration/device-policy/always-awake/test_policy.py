import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent


class AwakePolicyTests(unittest.TestCase):
    def test_global_idle_and_oled_values(self):
        values = json.loads((ROOT / 'kodi-settings.json').read_text())
        self.assertEqual(values, {
            'powermanagement.displaysoff': 0,
            'powermanagement.shutdowntime': 0,
            'screensaver.mode': 'screensaver.xbmc.builtin.black',
            'screensaver.time': 3,
            'screensaver.usedimonpause': False,
            'screensaver.disableforaudio': False,
        })

    def test_cec_independent_power_without_disabling_remote(self):
        root = ET.parse(ROOT / 'cec-settings.xml').getroot()
        self.assertEqual(root.tag, 'settings')
        values = {item.attrib['id']: item.attrib['value'] for item in root}
        self.assertEqual(len(values), len(root))
        self.assertEqual(values, {
            'enabled': '1',
            'standby_pc_on_tv_standby': '36028',
            'cec_standby_screensaver_mode': '231',
            'cec_wake_screensaver': '0',
            'wake_devices': '231',
            'activate_source': '0',
            'standby_devices': '231',
            'standby_tv_on_pc_standby': '0',
        })
        self.assertNotIn('physical_address', values)
        self.assertNotIn('volume_control', values)


if __name__ == '__main__':
    unittest.main()
