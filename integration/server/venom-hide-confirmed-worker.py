"""Dispatcharr visibility worker; called only by the locked CT controller.

Never delete channels. Preserve UUID, number, stream mappings and user hides.
Default controller mode is dry run. Recovery ledger is saved before each write.
"""
from collections import defaultdict,Counter
import json
from pathlib import Path
import runpy
import sqlite3
import sys
import time

ROOT=Path('/data')

def main():
    from django.db import transaction
    from apps.channels.models import Channel
    from apps.channels.compact_numbering import get_group_relation_for_channel,is_compact_group
    payload=json.load(sys.stdin);now=time.time()
    if not 0<=now-payload['generated']<=120:raise ValueError('Stale controller snapshot')
    apply=payload.get('apply') is True
    decision=runpy.run_path(str(ROOT/'venom-channel-health-policy.py'))['decision']
    action=runpy.run_path(str(ROOT/'venom-hide-plan.py'))['action']
    path=ROOT/'venom-hidden-channels.json'
    ledger=json.loads(path.read_text()) if path.exists() else {}
    records=defaultdict(list)
    negative=ROOT/'provider-negative-evidence.sqlite3'
    if negative.exists():
        with sqlite3.connect('file:'+str(negative)+'?mode=ro',uri=True) as db:
            for cid,raw in db.execute('select channel_id,record from observations'):records[str(cid)].append(json.loads(raw))
    presence={}
    with sqlite3.connect('file:'+str(ROOT/'provider-presence.sqlite3')+'?mode=ro',uri=True) as db:
        for cid,stamp,present,sources in db.execute('select channel_id,time,present,source_ids from observations order by time'):
            presence[str(cid)]={'time':stamp,'present':present,'sources':json.loads(sources)}
    def save_ledger():
        temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(ledger,sort_keys=True));temp.chmod(0o600);temp.replace(path)
    counts=Counter();changes=0
    for cid in sorted(set(records)|set(ledger)):
        if changes>=5:break
        with transaction.atomic():
            channel=Channel.objects.select_for_update().filter(pk=int(cid),auto_created_by__name='Venom TV').first()
            if not channel:counts['missing_or_different_account']+=1;continue
            sources=list(channel.streams.all())
            if len(sources)!=1 or sources[0].m3u_account_id!=channel.auto_created_by_id:
                counts['source_mapping_requires_review']+=1;continue
            source_ids=[str(sources[0].stream_id)]
            identity=json.dumps([str(channel.uuid),channel.auto_created_by_id,source_ids])
            current=presence.get(cid,{})
            fresh=(0<=now-current.get('time',0)<=36*3600 and current.get('sources')==source_ids)
            prior=ledger.get(cid)
            evidence=[r for r in records[cid] if r.get('provider_source_ids')==source_ids]
            success=max(payload['success'].get(cid,0),(prior or {}).get('restored_at',0))
            if success:evidence.append({'time':success,'capacity_available':True,'decoded_video_frames':3})
            eligible=(fresh and current.get('present')==0 and evidence
                      and 0<=now-max(r['time'] for r in evidence)<=36*3600
                      and decision(evidence,now)=='eligible_for_reversible_hide')
            relation=get_group_relation_for_channel(channel)
            compact=is_compact_group(relation) if relation else False
            result=action(channel.hidden_from_output,prior,bool(eligible),fresh and current.get('present')==1,identity,compact)
            counts[result]+=1
            if not apply:continue
            if result=='manual_unhide':
                ledger[cid]={**prior,'status':'manual_unhide','updated':now};save_ledger();continue
            if result not in ('hide','restore'):continue
            original_number=channel.channel_number
            # Persist intent before the database transaction. A crash can cause
            # a conservative manual-review result, never an unrecorded hide.
            ledger[cid]={**(prior or {}),'identity':identity,'status':'managed',
                         'original_hidden':False,'number':original_number,'updated':now}
            save_ledger()
            channel.hidden_from_output=result=='hide'
            channel.save(update_fields=['hidden_from_output'])
            channel.refresh_from_db()
            if channel.channel_number!=original_number:raise ValueError('Number changed; transaction rolled back')
            changes+=1
        if apply and result=='restore':
            ledger[cid].update(status='restored',restored_at=now);save_ledger()
    print(json.dumps({'event':'visibility_finished','apply':apply,'decisions':dict(counts),'changed':changes}),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'event':'visibility_error','type':type(exc).__name__}),flush=True)
        raise SystemExit(1)
