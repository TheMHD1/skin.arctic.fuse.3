"""Add exact guide mappings for new channels; retain manual overrides."""
from apps.m3u.models import M3UAccount
from apps.channels.models import Channel,ChannelOverride,ChannelGroupM3UAccount
from apps.epg.models import EPGSource,EPGData
from apps.epg.tasks import refresh_epg_data
from apps.m3u.tasks import sync_auto_channels
from django.db.models import Q

account=M3UAccount.objects.get(name='Venom TV')
if account.status!='success':
    print('Import not ready; maintenance deferred until next timer run.')
else:
    new_groups=ChannelGroupM3UAccount.objects.filter(m3u_account=account,enabled=True,auto_channel_sync=False).update(auto_channel_sync=True)
    if new_groups:sync_auto_channels(account.id)
    source=EPGSource.objects.get(name='Venom TV Guide')
    by_id={str(e.tvg_id):e.id for e in EPGData.objects.filter(epg_source=source)}
    updates=[]
    for channel in Channel.objects.filter(auto_created_by=account).filter(Q(override__isnull=True)|Q(override__epg_data__isnull=True)).prefetch_related('streams'):
        stream=next(iter(channel.streams.all()),None)
        if stream and str(stream.stream_id) in by_id:
            updates.append(ChannelOverride(channel=channel,epg_data_id=by_id[str(stream.stream_id)]))
    # Name-only overrides must not block later exact guide mappings. Update only
    # an empty EPG field, preserving both names and any concurrently assigned EPG.
    for update in updates:
        row,_=ChannelOverride.objects.get_or_create(channel_id=update.channel_id)
        ChannelOverride.objects.filter(pk=row.pk,epg_data__isnull=True).update(epg_data_id=update.epg_data_id)
    if updates:refresh_epg_data.delay(source.id,force=True)
    print('New live groups:',new_groups,'new exact guide mappings:',len(updates))
