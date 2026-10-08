"""Bounded, read-only active episode-ID revisions for the local XC gateway."""
import hashlib,json,subprocess

MAX_ROWS=500000
def revision(ids):
    values=sorted({int(value) for value in ids})
    if any(value<1 for value in values):raise ValueError('Invalid episode identity')
    return hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest()

# XC series ID is M3USeriesRelation.id, not Series.id. Detail responses combine
# episodes from all active providers of that shared Series. Mirror that domain;
# do not confuse external stream IDs with either primary key.
QUERY='''import os,json,hashlib
os.environ.setdefault('DJANGO_SETTINGS_MODULE','dispatcharr.settings')
import django
django.setup()
from apps.vod.models import M3USeriesRelation,M3UEpisodeRelation
relations=list(M3USeriesRelation.objects.filter(m3u_account__is_active=True).values_list('id','series_id'))
if len(relations)>50000:raise ValueError('Too many series relations')
groups={series:set() for ident,series in relations}
rows=M3UEpisodeRelation.objects.filter(m3u_account__is_active=True).values_list('episode__series_id','episode_id').distinct().order_by('episode__series_id','episode_id')
for i,(series,episode) in enumerate(rows.iterator(chunk_size=2000)):
    if i>=500000:raise ValueError('Too many episode identities')
    if series in groups:groups[series].add(episode)
revisions={str(ident):hashlib.sha256(json.dumps(sorted(groups[series]),separators=(',',':')).encode()).hexdigest() for ident,series in relations}
print(json.dumps({'schema':1,'revisions':revisions},separators=(',',':')))
'''
def load(run=subprocess.run):
    result=run(['docker','exec','dispatcharr','python','-c',QUERY],capture_output=True,text=True,check=True,timeout=20)
    if len(result.stdout)>8*1024*1024:raise ValueError('Revision response too large')
    # Django setup writes informational lines before the final JSON payload.
    data=json.loads(result.stdout.strip().splitlines()[-1])
    if data.get('schema')!=1 or not isinstance(data.get('revisions'),dict):raise ValueError('Invalid revision response')
    revisions=data['revisions']
    if len(revisions)>50000 or any(not key.isdigit() or not isinstance(value,str) or len(value)!=64 or
                                  any(char not in '0123456789abcdef' for char in value) for key,value in revisions.items()):
        raise ValueError('Invalid series revision')
    return revisions

def due(old,known,current,now,canary=False):
    if not old or canary:return True
    if old[1]=='ok' and current is not None and known!=current:return True
    return now-old[0]>=(604800 if old[1]=='ok' else 21600)
