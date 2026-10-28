import importlib.util, shutil, tempfile, unittest, zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('dependencies',HERE/'dependencies.py')
dependencies=importlib.util.module_from_spec(spec); spec.loader.exec_module(dependencies)

ADDON='''<addon id="plugin.video.themoviedb.helper" version="6.19.1"><requires>{}</requires></addon>'''

class TestDependencies(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)

    def artifact(self, requirements=dependencies.TMDB_REQUIREMENTS):
        path=Path(self.tmp.name)/'tmdb.zip'
        body=''.join(f'<import addon="{key}" version="{value}"/>' for key,value in requirements.items())
        with zipfile.ZipFile(path,'w') as archive: archive.writestr('plugin.video.themoviedb.helper/addon.xml',ADDON.format(body))
        return path

    def test_exact_reviewed_artifact_is_accepted(self):
        result=dependencies.review_tmdb_artifact(self.artifact())
        self.assertEqual(result['version'],'6.19.1')
        self.assertEqual(result['requirements'],dependencies.TMDB_REQUIREMENTS)

    def test_missing_dependency_or_wrong_version_fails_closed(self):
        requirements=dict(dependencies.TMDB_REQUIREMENTS); requirements.pop('script.module.qrcode')
        with self.assertRaises(ValueError): dependencies.review_tmdb_artifact(self.artifact(requirements))

    def test_archive_traversal_fails_closed(self):
        path=Path(self.tmp.name)/'unsafe.zip'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('../addon.xml','x')
            archive.writestr('plugin.video.themoviedb.helper/addon.xml',ADDON.format(''))
        with self.assertRaises(ValueError): dependencies.review_tmdb_artifact(path)

if __name__=='__main__': unittest.main()
