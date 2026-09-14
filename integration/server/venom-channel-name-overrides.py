"""Run inside Dispatcharr Django shell; persistent supported name overrides only.

VENOM_NAMES_APPLY=1 applies. VENOM_NAMES_CHANNEL optionally limits a canary.
Default is dry run. Existing user overrides are never replaced. Original raw
Channel fields, stream URLs, numbers, IDs and all non-name overrides stay intact.
"""
import json
import fcntl
import os
from pathlib import Path
import runpy
from django.db import transaction
from apps.channels.models import Channel, ChannelOverride

planned_override = runpy.run_path('/data/venom-channel-names.py')['planned_override']
lock=Path('/data/venom-name-overrides.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX)
ledger_path = Path('/data/venom-name-overrides.json')
ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
only = os.environ.get('VENOM_NAMES_CHANNEL')
query = Channel.objects.filter(auto_created_by__name='Venom TV').select_related('override')
if only:
    query = query.filter(pk=int(only))
changes = []
for channel in query:
    override = getattr(channel, 'override', None)
    current = override.name if override else None
    previous = ledger.get(str(channel.pk))
    desired = planned_override(channel.name,current,previous)
    # If the provider later supplies a clean/new name, update our old override
    # too. Otherwise it would keep displaying an obsolete title forever.
    if current == desired:
        continue
    changes.append((channel.pk, current, desired))

if os.environ.get('VENOM_NAMES_APPLY') == '1' and changes:
    # Save the recovery record before changing anything. On retry an unchanged
    # original null override remains eligible; externally edited names do not.
    for pk, current, desired in changes:
        ledger.setdefault(str(pk), {'original': current})['applied'] = desired
    tmp = ledger_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2))
    tmp.chmod(0o600)
    tmp.replace(ledger_path)
    with transaction.atomic():
        for pk, current, desired in changes:
            row, _ = ChannelOverride.objects.get_or_create(channel_id=pk)
            row = ChannelOverride.objects.select_for_update().get(pk=row.pk)
            if row.name != current:
                raise RuntimeError('Concurrent name override changed; no overrides applied')
            row.name = desired
            row.save(update_fields=['name', 'updated_at'])
print(json.dumps({'apply': os.environ.get('VENOM_NAMES_APPLY') == '1',
                  'changed': len(changes), 'examples': changes[:8]}, ensure_ascii=False))
