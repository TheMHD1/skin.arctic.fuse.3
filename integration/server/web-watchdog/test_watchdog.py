import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class WatchdogTests(unittest.TestCase):
    def execute(self, web='200', api='200', last=None, url='http://192.0.2.10:8096'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / 'bin'
            bindir.mkdir()
            state = root / 'state'
            state.mkdir()
            if last is not None:
                (state / 'last_restart').write_text(last)
            (bindir / 'curl').write_text('''#!/bin/sh
for argument; do target=$argument; done
printf '%s\\n' "$target" >> "$CALLS"
case "$target" in */health) printf '%s' "$API";; *) printf '%s' "$WEB";; esac
''')
            (bindir / 'docker').write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$RESTARTS"
''')
            for item in bindir.iterdir():
                item.chmod(0o755)
            env = dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH'],
                       JELLYFIN_WATCHDOG_URL=url, JELLYFIN_WATCHDOG_STATE=str(state),
                       JELLYFIN_WATCHDOG_LOG=str(root / 'log'), WEB=web, API=api,
                       CALLS=str(root / 'calls'), RESTARTS=str(root / 'restarts'))
            result = subprocess.run(['bash', str(HERE / 'watchdog.sh')], env=env,
                                    text=True, capture_output=True, timeout=5)
            return result, (root / 'calls').read_text() if (root / 'calls').exists() else '', \
                (root / 'restarts').read_text() if (root / 'restarts').exists() else ''

    def test_configured_listener_and_healthy_never_restart(self):
        result, calls, restarts = self.execute()
        self.assertEqual(result.returncode, 0)
        self.assertIn('http://192.0.2.10:8096/web/index.html', calls)
        self.assertIn('http://192.0.2.10:8096/health', calls)
        self.assertEqual(restarts, '')

    def test_connection_failure_or_non_5xx_never_restart(self):
        for web, api in [('000', '000'), ('500', '000'), ('401', '200'), ('404', '200')]:
            with self.subTest(web=web, api=api):
                self.assertEqual(self.execute(web, api)[2], '')

    def test_persistent_web_only_5xx_rechecks_and_restarts_one_container(self):
        result, calls, restarts = self.execute('500', '200')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(calls.splitlines()), 4)
        self.assertEqual(restarts, 'restart jellyfin\n')

    def test_cooldown_future_or_malformed_clock_data_fail_safe(self):
        for last in ['9999999999', 'malformed']:
            self.assertEqual(self.execute('500', '200', last=last)[2], '')

    def test_credential_or_query_url_is_rejected_before_probe(self):
        for url in ['http://user:password@192.0.2.10', 'http://192.0.2.10?token=fake']:
            result, calls, restarts = self.execute(url=url)
            self.assertEqual(result.returncode, 64)
            self.assertEqual(calls, '')
            self.assertEqual(restarts, '')


if __name__ == '__main__':
    unittest.main()
