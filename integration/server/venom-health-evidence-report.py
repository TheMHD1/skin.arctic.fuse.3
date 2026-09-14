"""Read-only bridge from persistent observations to the conservative policy.

No stream requests, no hiding, no changes to either database. Reports missing
evidence explicitly; catalogue absence is not substituted for a playback test.
"""
from collections import Counter,defaultdict
import json
from pathlib import Path
import runpy
import sqlite3
import time

ROOT=Path('/data/config/iptv-venom')

def evaluate(records,presence,now,decision):
    # A current independent catalogue observation is required; stale removal
    # observations or reappearance can never authorize a visibility change.
    state=decision(records,now)
    if state=='eligible_for_reversible_hide':
        if not presence or presence['present']!=0 or not 0<=now-presence['time']<=36*3600:
            return 'keep_visible_catalogue_not_currently_absent'
        if not records or not 0<=now-max(r['time'] for r in records)<=36*3600:
            return 'keep_visible_stale_playback_evidence'
    return state

def main():
    decision=runpy.run_path(str(ROOT/'venom-channel-health-policy.py'))['decision']
    by_channel=defaultdict(list)
    with sqlite3.connect('file:'+str(ROOT/'channel-health.sqlite3')+'?mode=ro',uri=True) as db:
        for cid,record in db.execute('select channel_id,record from observations'):
            by_channel[str(cid)].append(json.loads(record))
    negative=Path('/data/config/dispatcharr/provider-negative-evidence.sqlite3')
    if negative.exists():
        with sqlite3.connect('file:'+str(negative)+'?mode=ro',uri=True) as db:
            for cid,record in db.execute('select channel_id,record from observations'):
                by_channel[str(cid)].append(json.loads(record))
    presence={}
    with sqlite3.connect('file:/data/config/dispatcharr/provider-presence.sqlite3?mode=ro',uri=True) as db:
        for cid,stamp,present in db.execute('select channel_id,time,present from observations order by time'):
            presence[str(cid)]={'time':stamp,'present':present}
    now=time.time();counts=Counter();eligible=[]
    for cid,records in by_channel.items():
        outcome=evaluate(records,presence.get(cid),now,decision)
        counts[outcome]+=1
        if outcome=='eligible_for_reversible_hide':eligible.append(cid)
    print(json.dumps({'observed_channels':len(by_channel),'decisions':dict(counts),
                      'eligible_channel_ids':eligible,'visibility_changed':False,
                      'note':'Eligibility requires controlled provider-origin failure evidence; gateway timeouts are insufficient.'}))

if __name__=='__main__':main()
