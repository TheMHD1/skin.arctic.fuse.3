import importlib.util, os, shutil, subprocess, tempfile, unittest, xml.etree.ElementTree as ET
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('overlay',HERE/'overlay.py'); overlay=importlib.util.module_from_spec(spec); spec.loader.exec_module(overlay)
class TestOverlay(unittest.TestCase):
    def setUp(self):
        source=Path(os.environ['ARCTIC_FUSE_3410_SOURCE'])
        if not source.is_dir(): raise RuntimeError('ARCTIC_FUSE_3410_SOURCE is not a checkout')
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()!=overlay.UPSTREAM_COMMIT:
            raise RuntimeError('ARCTIC_FUSE_3410_SOURCE is not the reviewed upstream commit')
        if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=source,text=True):
            raise RuntimeError('ARCTIC_FUSE_3410_SOURCE is not clean')
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'skin';shutil.copytree(source,self.root)
    def tearDown(self): self.tmp.cleanup()
    def test_xml_and_semantic_routes(self):
        overlay.transform(self.root)
        for f in self.root.rglob('*.xml'): ET.parse(f)
        s=(self.root/'1080i/Includes_Search.xml').read_text()
        self.assertLess(s.index('combined-selector-owned'),s.index('guid">discover'))
        self.assertLess(s.index('guid">discover'),s.index('combined-selector-venom'))
        self.assertIn('standard-selector-owned',s);self.assertIn('standard-selector-venom',s)
        self.assertIn('browser.py,live',(self.root/'1080i/Custom_1107_Hub.xml').read_text())
        self.assertIn('RunPlugin($INFO[ListItem.FolderPath])',(self.root/'shortcuts/generator/data/setup/widgets_row.xml').read_text())
    def test_second_apply_fails_closed(self):
        overlay.transform(self.root)
        with self.assertRaises(RuntimeError): overlay.transform(self.root)
if __name__=='__main__': unittest.main()
