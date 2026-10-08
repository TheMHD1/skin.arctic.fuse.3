"""Compare private inventories without publishing identities or raw logs.

Release targets are source checks, NOT proof of UI, AV, wake or WAN acceptance.
Older inventories missing evidence are unknown, never silently treated as good.
"""
import argparse
import json
from pathlib import Path
import install
ux=install.module('report_ux_release',install.HERE.parent/'ux-round/install.py',install.HERE.parent/'ux-round')

REQUIRED = ('plugin.video.habibi.resume', 'plugin.video.jellyfin', 'plugin.video.kodiseerr',
            'plugin.video.venom.tv', 'skin.arctic.fuse.3', 'plugin.video.themoviedb.helper',
            'script.skinvariables', 'script.audiooffsetmanager', 'service.upnext',
            'slyguy.dependencies', 'slyguy.trailers', 'inputstream.adaptive')
PINS = ('skin.arctic.fuse.3', 'plugin.video.jellyfin', 'plugin.video.kodiseerr')
AWAKE = json.loads((install.HERE.parents[1]/'device-policy/always-awake/kodi-settings.json').read_text())
TRANSPORT_FILES = {
    'addons/plugin.video.jellyfin/jellyfin_kodi/helper/api.py',
    'addons/plugin.video.jellyfin/jellyfin_kodi/helper/playutils.py',
    'addons/plugin.video.jellyfin/jellyfin_kodi/jellyfin/api.py',
    'addons/plugin.video.venom.tv/default.py', 'addons/plugin.video.venom.tv/remote_catalogue.py',
    *('addons/plugin.video.jellyfin/jellyfin_kodi/helper/remote_native/'+name for name in
      ('manifest.py', 'gate.py', 'kodi_adapter.py', '__init__.py'))}
REMOTE_TARGETS = {'.kodi/'+name: digest for name, digest in install.LOCAL_AFTER.items()
                  if not name.endswith('/browser.py')}
REMOTE_TARGETS[install.remote.BROWSER] = '6e0f3939ab89cdd1f9d85c167416d08d1b9a15846e3aad7f1619bca7398f7498'
CEC = {'enabled': '1', 'standby_pc_on_tv_standby': '36028',
       'cec_standby_screensaver_mode': '231', 'cec_wake_screensaver': '0',
       'wake_devices': '231', 'activate_source': '0', 'standby_devices': '231',
       'standby_tv_on_pc_standby': '0'}


def device(record, cohort):
    addons = {row['addonid']: row for row in record.get('addons', {}).get('result', {}).get('addons', [])}
    missing = [name for name in REQUIRED if name not in addons or not addons[name].get('enabled')]
    dependency_issues = []
    declarations = record.get('dependencies')
    if declarations is not None:
        for name, declaration in declarations.items():
            if name not in addons or not addons[name].get('enabled'):
                continue
            for requirement in declaration['requires']:
                dep = requirement['addon']
                # Host ABI declarations aren't installable addon packages.
                if requirement.get('optional') == 'true' or dep.startswith(('xbmc.', 'kodi.binary.', 'kodi.resource')):
                    continue
                if dep not in addons or not addons[dep].get('enabled'):
                    dependency_issues.append([name, dep])
    awake = {name: ('matches' if record.get('settings', {}).get(name, {}).get('result', {}).get('value') == expected
                     and type(record.get('settings', {}).get(name, {}).get('result', {}).get('value')) is type(expected)
                     and 'result' in record.get('settings', {}).get(name, {}) else
                    'unknown' if 'result' not in record.get('settings', {}).get(name, {}) else 'differs')
             for name, expected in AWAKE.items()}
    cec = record.get('cec', {})
    cec_state = ('unknown' if not cec else 'matches' if len(cec) == 1 and
                 all(next(iter(cec.values())).get(k) == v for k, v in CEC.items()) else 'review-required')
    targets = ({'.kodi/'+k: v for k, v in install.LOCAL_AFTER.items()} if cohort == 'local' else REMOTE_TARGETS)
    hashes = record.get('source_hashes', {})
    repair_state = {name.removeprefix('.kodi/'): ('target-source-present' if hashes.get(name.removeprefix('.kodi/')) == digest
                    or (name.removeprefix('.kodi/') in ux.AFTER[cohort]
                        and hashes.get(name.removeprefix('.kodi/'))==ux.AFTER[cohort][name.removeprefix('.kodi/')])
                    else 'pending-or-unreviewed') for name, digest in targets.items()}
    rules = record.get('update_rules')
    pinned = {row[1] for row in rules or [] if len(row) >= 3 and row[2] == 1}
    pins = PINS + (('service.tailscale',) if cohort == 'remote' else ())
    return {'evidence': record.get('evidence', 'read-only-inventory'),
            'captured_at': record.get('captured_at', 'unknown-saved-date'),
            'installed_shared_release': record.get('shared_release', 'unknown-not-captured'),
            'installed_ux_release':record.get('ux_release','unknown-not-captured'),
            'ux_sources':{name:('target-source-present' if hashes.get(name)==digest else 'pending-or-unreviewed')
                          for name,digest in ux.AFTER[cohort].items()},
            'skin_policy':record.get('skin_policy','unknown-not-captured'),
            'menu_contracts':record.get('menu_contracts','unknown-not-captured'),
            'live_acceptance': 'not-proven-by-inventory',
            'missing_or_disabled_tools': missing,
            'dependency_status': 'unknown' if declarations is None else 'checked',
            'missing_or_disabled_required_dependencies': dependency_issues,
            'awake_settings': awake, 'cec_override': cec_state,
            'cec_load_and_tv_off_acceptance': 'requires-live-check',
            'missing_manual_update_pins': 'unknown' if rules is None else sorted(set(pins)-pinned),
            'manifest_drift': record.get('manifest_drift', 'unknown'),
            'paired_release_repairs': repair_state,
            'backup_selection': record.get('local_backup_checks', record.get('backup_roots', 'unknown')),
            'recent_log_counts': record.get('recent_log_counts', 'unknown'),
            'tool_versions': {k: addons[k]['version'] for k in REQUIRED if k in addons}}


def compare(local, remote):
    left, right = local.get('source_hashes', {}), remote.get('source_hashes', {})
    names = (set(left) | set(right)) - {'addons/plugin.video.habibi.resume/verified-build.json'}
    differences = [name for name in sorted(names) if left.get(name) != right.get(name)]
    repair_paths = set(install.LOCAL_AFTER)|set(ux.AFTER['local'])
    return {'release': install.RELEASE, 'local': device(local, 'local'), 'remote': device(remote, 'remote'),
            'identical_common_source_files': sum(left.get(n) == right.get(n) for n in names if n in left and n in right),
            'transport_sources_to_review_against_cohort_pins': [n for n in differences if n in TRANSPORT_FILES],
            'shared_repairs_or_browser_variant': [n for n in differences if n in repair_paths],
            'unexplained_source_differences': [n for n in differences if n not in TRANSPORT_FILES | repair_paths],
            'shortcut_hashes_equal': local.get('shortcut_hashes') == remote.get('shortcut_hashes')
                if 'shortcut_hashes' in local and 'shortcut_hashes' in remote else 'unknown',
            'menu_contracts_equal':local.get('menu_contracts')==remote.get('menu_contracts')
                if 'menu_contracts' in local and 'menu_contracts' in remote else 'unknown',
            'automatic_deployment': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', type=Path, required=True)
    parser.add_argument('--remote', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(json.loads(args.local.read_text()), json.loads(args.remote.read_text())), indent=2))
