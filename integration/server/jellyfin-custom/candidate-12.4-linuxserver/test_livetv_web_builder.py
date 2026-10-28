import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
BUILDER = HERE / 'build-livetv-web-12.4-candidate.sh'
WEB_REVISION = '0a580ce8df89282dfd120b6d5efb8e106da23bd5'


class LiveTvWebBuilderTests(unittest.TestCase):
    def test_optional_package_output_matches_dist_without_self_hashing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            web = root / 'web'
            output = root / 'plugin-web'
            tools = root / 'tools'
            tools.mkdir()
            web.mkdir()
            self._tool(tools / 'git', f'''#!/bin/sh
if [ "${{3:-}}" = rev-parse ]; then
  printf '%s\\n' '{WEB_REVISION}'
fi
exit 0
''')
            self._tool(tools / 'npm', '''#!/bin/sh
if [ "${1:-}" = run ] && [ "${2:-}" = build:production ]; then
  mkdir -p dist/assets
  printf '<!doctype html>' > dist/index.html
  printf 'bundle' > dist/assets/app.js
fi
exit 0
''')
            self._tool(tools / 'npx', '#!/bin/sh\nexit 0\n')
            environment = {**os.environ, 'PATH': f'{tools}:/usr/bin:/bin'}
            subprocess.run([str(BUILDER), str(web), str(output)], cwd=HERE,
                           env=environment, check=True, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            dist_manifest = (output / '.dist-sha256').read_text()
            package_manifest = (output / '.package-sha256').read_text()
            self.assertEqual(package_manifest, dist_manifest)
            self.assertNotIn('.dist-sha256', package_manifest)
            self.assertNotIn('.package-sha256', package_manifest)
            self.assertEqual((output / 'index.html').read_text(), '<!doctype html>')
            self.assertEqual((output / 'assets/app.js').read_text(), 'bundle')

    @staticmethod
    def _tool(path: Path, source: str) -> None:
        path.write_text(source)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == '__main__':
    unittest.main()
