import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import build
import generated
import install


def sha(data):return hashlib.sha256(data).hexdigest()


def selector(name):
    items=''.join('<item><label>{0}</label><property name="guid">guid-{1}</property><property name="widget_id">$NUMBER[{1}]</property></item>'.format(label,item_id)
                  for item_id,label in [('502','Movies'),('503','Shows'),('504','Venom Movies — Not HD'),('505','Venom Shows — Not HD')])
    return '<include name="{}">{}</include>'.format(name,items)


class OverlayTests(unittest.TestCase):
    def test_standalone_installer_loads_its_own_builder_and_kodi_profile_helper(self):
        code=("import runpy; m=runpy.run_path(%r,run_name='search_priority_probe'); "
              "assert len(m['build'].OUTPUTS)==7; assert callable(m['kodi_release'].load_profile)" % str(HERE/'install.py'))
        subprocess.run([sys.executable,'-c',code],check=True)

    def fixtures(self):
        return {
            install.SEARCH:b'''<includes><include name="Search_Switcher_Items">\n        <item><property name="guid">discover</property></item>\n        <include>skinvariables-searchwidgets-selector</include></include><include name="Search_Switcher_Wall_Items">\n        <item><property name="guid">discover</property></item>\n        <include>skinvariables-searchwidgets-wall-selector</include></include></includes>''',
            install.GENERATED:('<?xml version="1.0"?><includes>'+selector('skinvariables-searchwidgets-selector')+selector('skinvariables-searchwidgets-wall-selector')+'</includes>').encode(),
            install.LABELS:b'''<includes>\n    <variable name="Label_MediaList_Details_LeftLabel"><value>x</value></variable></includes>''',
            install.OBJECTS:b'''<includes>\n    <include name="Object_AlphabetLetter_Label"></include><include name="Object_Indicator"><definition><control type="group">\n                <nested />\n                <centerbottom>0</centerbottom>\n                <right>25</right></control></definition></include></includes>''',
            install.LAYOUTS:b'''<includes><include name="Layout_Poster"><definition><control type="group"><control type="group">                    <include condition="!$PARAM[selected] + $PARAM[indicator]" content="Object_Indicator">\n                        <param name="affix">$PARAM[affix]</param>\n                        <param name="listitem">$PARAM[listitem]</param>\n                    </include>                    <include content="Object_SelectBox" condition="$PARAM[selected]">\n                        <param name="focusbounce">true</param>\n                    </include>\n                </control>\n\n            </control>\n\n        </definition>\n    </include>\n\n    <include name="Layout_Reviews"></include></includes>''',
        }

    def test_visible_order_guid_identity_and_rating_priority(self):
        data=self.fixtures()
        search=ET.fromstring(generated.transform_search(data[install.SEARCH]))
        normal=next(node for node in search.findall('include') if node.get('name')=='Search_Switcher_Items')
        wall=next(node for node in search.findall('include') if node.get('name')=='Search_Switcher_Wall_Items')
        self.assertEqual([(node.text or node.findtext("property[@name='guid']")).strip() for node in normal],
                         ['skinvariables-searchwidgets-selector-owned','discover','skinvariables-searchwidgets-selector-venom'])
        self.assertEqual([(node.text or node.findtext("property[@name='guid']")).strip() for node in wall],
                         ['skinvariables-searchwidgets-wall-selector-owned','discover','skinvariables-searchwidgets-wall-selector-venom'])
        output=ET.fromstring(generated.transform_generated(data[install.GENERATED]))
        rows={node.get('name'):[(item.findtext('label'),item.findtext("property[@name='guid']"),item.findtext("property[@name='widget_id']")) for item in node]
              for node in output.findall('include')}
        self.assertEqual(rows['skinvariables-searchwidgets-selector-owned'],
                         [('Movies','guid-502','$NUMBER[502]'),('Shows','guid-503','$NUMBER[503]')])
        self.assertEqual([row[0] for row in rows['skinvariables-searchwidgets-selector-venom']],
                         ['Venom Movies — Not HD','Venom Shows — Not HD'])
        labels=generated.transform_labels(data[install.LABELS]).decode()
        self.assertLess(labels.index('Habibi.Rating.IMDb'),labels.index('Rating(tmdb)'))
        self.assertLess(labels.index('Rating(tmdb)'),labels.index('Habibi.Rating.Community'))
        self.assertNotIn('IMDb $INFO[ListItem.Property(Habibi.Rating.Community)',labels)
        for name,fn in ((install.OBJECTS,generated.transform_objects),(install.LAYOUTS,generated.transform_layouts)):
            ET.fromstring(fn(data[name]))

    def test_exact_cohort_plan_reapply_and_drift_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            temp=Path(directory);root=temp/'root';stage=temp/'payload';root.mkdir()
            build.build(stage,check_clean=False)
            fixtures=self.fixtures()
            baselines={}
            paths=set(install.BASE_HASHES)|{install.TARGETS['skin/search_selector_venom.xml'],install.TARGETS['skin/search_selector_wall_venom.xml']}
            for relative in paths:
                if relative in (install.TARGETS['skin/search_selector_venom.xml'],install.TARGETS['skin/search_selector_wall_venom.xml']):continue
                data=fixtures.get(relative,('baseline:'+relative).encode())
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);baselines[relative]=sha(data)
            for name,version in install.VERSIONS.items():
                path=root/'addons'/name/'addon.xml';path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('<addon id="{}" version="{}"/>'.format(name,version))
            record={'versions':dict(install.VERSIONS),'files':{relative:digest for relative,digest in baselines.items()
                    if relative in (install.TARGETS['home/client.py'],install.TARGETS['home/default.py'],install.SEARCH,install.GENERATED)}}
            manifest=root/'addons/plugin.video.habibi.resume/verified-build.json'
            manifest.parent.mkdir(parents=True,exist_ok=True);manifest.write_text(json.dumps(record,indent=2)+'\n')
            transforms={name:(sha(fn(fixtures[name])),fn) for name,(_digest,fn) in install.OUTPUT_TRANSFORMS.items()}
            with mock.patch.object(install,'BASE_HASHES',baselines),mock.patch.object(install,'BASE_MANIFEST_HASH',sha(manifest.read_bytes())),mock.patch.object(install,'OUTPUT_TRANSFORMS',transforms):
                plan=install.build_changes(root,stage,{'variant':'local'})
                self.assertTrue(plan)
                for path,data in plan.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                self.assertFalse(install.build_changes(root,stage,{'variant':'local'}))
                generated_path=root/install.GENERATED
                rebuilt=generated_path.read_bytes().replace(b'</includes>',b'    \n</includes>')
                self.assertNotEqual(sha(rebuilt),transforms[install.GENERATED][0])
                generated_path.write_bytes(rebuilt)
                with mock.patch.object(install,'REBUILT_GENERATED_HASH',sha(rebuilt)):
                    reconciliation=install.build_changes(root,stage,{'variant':'local'})
                    self.assertEqual(list(reconciliation),[manifest])
                    for path,data in reconciliation.items():path.write_bytes(data)
                    self.assertFalse(install.build_changes(root,stage,{'variant':'local'}))
                    # Even a structurally harmless extra newline is not a
                    # reviewed whole-file hash and must remain fail-closed.
                    generated_path.write_bytes(rebuilt+b'\n')
                    with self.assertRaisesRegex(RuntimeError,'Unreviewed or partial'):
                        install.build_changes(root,stage,{'variant':'local'})


if __name__=='__main__':unittest.main()
