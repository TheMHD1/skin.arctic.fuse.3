"""Run in Dispatcharr Django shell after reviewed Jellyfin artwork uploads.

Persist successful station matches through provider refreshes. Existing
explicit logo overrides are preserved. Never changes names/streams/numbers.
"""
import json
from pathlib import Path
from django.db import transaction
from apps.channels.models import Channel,ChannelOverride,Logo
rows=json.loads(Path('/data/venom-artwork-applied.json').read_text())
changed=preserved=0
with transaction.atomic():
    for row in rows.values():
        channel=Channel.objects.filter(pk=row['gateway_id'],auto_created_by__name='Venom TV').first()
        if not channel:continue
        override,_=ChannelOverride.objects.get_or_create(channel=channel)
        override=ChannelOverride.objects.select_for_update().get(pk=override.pk)
        if override.logo_id:preserved+=1;continue
        logo,_=Logo.objects.get_or_create(url=row['url'],defaults={'name':'Reviewed: '+row['station']})
        override.logo=logo;override.save(update_fields=['logo','updated_at']);changed+=1
print(json.dumps({'logo_overrides_added':changed,'existing_preserved':preserved}))
