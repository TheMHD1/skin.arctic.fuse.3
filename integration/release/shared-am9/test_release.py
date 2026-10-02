import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import install
import inventory
import report


class Tests(unittest.TestCase):
    def test_both_browser_outputs_match_one_release_pins(self):
        common = HERE.parents[1]/'plugin.video.venom.tv'
        name = 'addons/plugin.video.venom.tv/browser.py'
        self.assertEqual(install.sha(install.local_overlay.transform(name,(common/'browser.py').read_bytes())),
                         install.LOCAL_AFTER[name])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);shutil.copytree(common,root/'addon')
            subprocess.run(['git','apply',str(HERE.parents[1]/'patches/venom-remote-performance.patch')],cwd=root/'addon',check=True)
            raw=(root/'addon/browser.py').read_bytes()
            r2=install.local_overlay.ui.transform(name,raw)
            output=install.local_overlay.focus.transform(r2)
            self.assertEqual(install.sha(output),report.REMOTE_TARGETS['.kodi/'+name])

    def fixture(self, root):
        (root/'.cache').mkdir(); (root/'.cache/hostname').write_text('fixture-box\n')
        account = root/'.kodi/userdata/addon_data/plugin.video.jellyfin'; account.mkdir(parents=True)
        (account/'data.json').write_text(json.dumps({'Servers': [{'UserId': 'owner', 'address': 'https://example.invalid', 'AccessToken': 'private-token'}]}))
        (account/'settings.xml').write_text('<settings><setting id="useDirectPaths">1</setting></settings>')
        paths = {}
        for name in install.local_overlay.BEFORE:
            path = root/'.kodi'/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('before:'+name).encode()); paths[name] = install.sha(path.read_bytes())
        worker = root/install.LOCAL_BACKUP; worker.parent.mkdir(parents=True)
        worker.write_bytes(b'private-worker')
        manifest = root/install.MANIFEST; manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'files': paths}, indent=2, sort_keys=True)+'\n')
        updated = json.loads(manifest.read_bytes())
        updated['files'].update({k:install.sha(('after:'+k).encode()) for k in paths})
        updated.update(shared_am9=install.RELEASE,local_backup_sha256=install.sha(b'repaired-worker'))
        profile = {'hostname': 'fixture-box', 'wlan_mac': 'fixture', 'cohort': 'local',
                   'jellyfin_user_id': 'owner', 'jellyfin_address': 'https://example.invalid'}
        return profile, manifest, updated

    def test_paired_local_idempotency_identity_drift_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); profile, manifest, updated = self.fixture(root)
            with patch.object(install,'LOCAL_BASE',install.sha(manifest.read_bytes())), \
                 patch.object(install,'LOCAL_FINAL',install.sha((json.dumps(updated,indent=2,sort_keys=True)+'\n').encode())), \
                 patch.object(install,'LOCAL_AFTER',updated['files']), \
                 patch.object(install.local_overlay,'transform',side_effect=lambda n,d:('after:'+n).encode()), \
                 patch.object(install.backup,'transform',return_value=b'repaired-worker'):
                for bad in ({**profile,'hostname':'other'}, {**profile,'jellyfin_user_id':'other'},
                            {**profile,'jellyfin_address':'https://other.invalid'}, {**profile,'cohort':'remote'}):
                    with self.assertRaises(ValueError):install.plan(root,bad)
                changes = install.plan(root,profile)
                self.assertEqual(len(changes),7)
                self.assertFalse(any('/userdata/' in str(p) or '/.cache/' in str(p) for p in changes))
                for path,data in changes.items():path.write_bytes(data)
                self.assertFalse(install.plan(root,profile))
                receipt = (root/install.RECEIPT).read_bytes()
                self.assertNotIn(b'private-token',receipt)
                self.assertNotIn(b'https://example.invalid',receipt)
                source = root/'.kodi'/next(iter(updated['files']))
                source.write_bytes(source.read_bytes()+b'\n# drift')
                with self.assertRaisesRegex(ValueError,'Manifest drift'):install.plan(root,profile)

    def test_path_guards_reject_symlink_ancestors_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'real').mkdir();(root/'alias').symlink_to(root/'real',target_is_directory=True)
            for name in ('alias/file','../outside','/storage/file'):
                with self.assertRaises(ValueError):install.regular(root,name)

    def test_remote_identity_requires_https_tls_and_own_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile,manifest,updated=self.fixture(root)
            profile['cohort']='remote'
            settings=root/'.kodi/userdata/addon_data/plugin.video.jellyfin/settings.xml'
            settings.write_text('<settings><setting id="useDirectPaths">0</setting><setting id="sslverify">true</setting></settings>')
            marker=root/'.kodi/userdata/addon_data/plugin.video.venom.tv/remote-native.json'
            marker.parent.mkdir(parents=True);marker.write_text('{"transport":"fixture"}')
            profile['remote_marker_sha256']=install.sha(marker.read_bytes())
            install.identity(root,profile)
            settings.write_text(settings.read_text().replace('true','false'))
            with self.assertRaisesRegex(ValueError,'TLS'):install.identity(root,profile)
            settings.write_text(settings.read_text().replace('false','true'))
            with self.assertRaisesRegex(ValueError,'marker'):
                install.identity(root,{**profile,'remote_marker_sha256':'wrong'})
            account=root/'.kodi/userdata/addon_data/plugin.video.jellyfin/data.json'
            auth=json.loads(account.read_bytes());auth['Servers'][0]['address']='http://example.invalid'
            account.write_text(json.dumps(auth))
            with self.assertRaisesRegex(ValueError,'HTTPS'):
                install.identity(root,{**profile,'jellyfin_address':'http://example.invalid'})

    def test_auditor_does_not_read_historical_addon_databases(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('Addons9.db','Addons33.db','Addons33.pre-something.db','Addons999.pre-backup.db'):
                (root/name).touch()
            self.assertEqual(inventory.addon_database(root).name,'Addons33.db')

    def test_unknown_awake_and_dependency_evidence_is_not_success(self):
        record=report.device({},'remote')
        self.assertTrue(all(x=='unknown' for x in record['awake_settings'].values()))
        self.assertEqual(record['cec_override'],'unknown')
        self.assertEqual(record['dependency_status'],'unknown')
        self.assertEqual(record['missing_manual_update_pins'],'unknown')

    def test_awake_type_and_missing_protection_are_reported(self):
        record={'settings':{k:{'result':{'value':v}} for k,v in report.AWAKE.items()},'cec':{'cec_HDMI.xml':report.CEC},'update_rules':[]}
        output=report.device(record,'local')
        self.assertTrue(all(x=='matches' for x in output['awake_settings'].values()))
        self.assertEqual(output['cec_override'],'matches')
        self.assertEqual(len(output['missing_manual_update_pins']),3)
        record['settings']['powermanagement.shutdowntime']['result']['value']=False
        self.assertEqual(report.device(record,'local')['awake_settings']['powermanagement.shutdowntime'],'differs')

    def test_new_unclassified_source_difference_is_visible(self):
        local={'source_hashes':{'addons/plugin.video.jellyfin/new.py':'a'}}
        remote={'source_hashes':{'addons/plugin.video.jellyfin/new.py':'b'}}
        output=report.compare(local,remote)
        self.assertEqual(output['unexplained_source_differences'],['addons/plugin.video.jellyfin/new.py'])
        self.assertFalse(output['automatic_deployment'])


if __name__ == '__main__':unittest.main()
