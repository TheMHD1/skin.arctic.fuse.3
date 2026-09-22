"""Guarded Dispatcharr profile-6 HTTP-403 retry update.

Run through the existing Dispatcharr Django shell. Credentials are read only
from its existing /data/venom-credentials.json mount and are never printed.
"""
import datetime,json,os,shlex,subprocess,urllib.request
from pathlib import Path

OLD=('-nostdin -hide_banner -loglevel warning -rw_timeout 15000000 '
     '-user_agent {userAgent} -i {streamUrl} -map 0:v:0? -map 0:a? '
     '-c copy -f mpegts pipe:1')
OPTIONS=('-reconnect_on_http_error 403 -reconnect_streamed 1 '
         '-reconnect_max_retries 4 -reconnect_delay_max 7 '
         '-reconnect_delay_total_max 11')
NEW=OLD.replace(' -i {streamUrl}',' '+OPTIONS+' -i {streamUrl}')

def main():
    from django.db import transaction
    from core.models import StreamProfile,CoreSettings
    apply=os.environ.get('VENOM_RETRY_APPLY')=='1';rollback=os.environ.get('VENOM_RETRY_ROLLBACK')=='1'
    assert not (apply and rollback),'Choose one operation'
    expected,replacement=(NEW,OLD) if rollback else (OLD,NEW)
    help_result=subprocess.run(['ffmpeg','-hide_banner','-h','protocol=http'],capture_output=True,text=True,timeout=10,check=True)
    for option in shlex.split(OPTIONS)[::2]:assert option in help_result.stdout+help_result.stderr,'Unsupported FFmpeg option: '+option
    secret=json.loads(Path('/data/venom-credentials.json').read_text())
    def request(path,data=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        req=urllib.request.Request('http://127.0.0.1:9191'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=8) as response:return json.load(response)
    token=request('/api/accounts/token/',{'username':secret['admin_user'],'password':secret['admin_password']})['access']
    def check_idle():
        stats=request('/proxy/stats/',token=token)
        for name,count,rows in [('live','count','channels'),('vod','total_connections','vod_connections'),('catchup','total_connections','timeshift_sessions')]:
            assert stats.get(name,{}).get(count)==0 and stats[name].get(rows)==[],'Relay busy'
    check_idle()
    with transaction.atomic():
        settings=CoreSettings.objects.get(key='stream_settings').value;assert settings['default_stream_profile']==6
        profile=StreamProfile.objects.select_for_update().get(pk=6)
        assert profile.name=='Venom Original Quality' and profile.command=='ffmpeg' and profile.is_active and not profile.locked
        assert profile.user_agent_id is None and profile.parameters==expected,'Profile drift: re-review before changing'
        assert shlex.split(NEW).count('-reconnect_on_http_error')==1
        if not (apply or rollback):print('RETRY_PROFILE_PREFLIGHT_OK: no changes',flush=True);return
        check_idle();backup_dir=Path('/data/venom-maintenance')/('http-retry-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        backup_dir.mkdir(parents=True,mode=0o700,exist_ok=False);backup=backup_dir/'profile6.json'
        with backup.open('x') as handle:
            json.dump({'id':profile.pk,'name':profile.name,'command':profile.command,'parameters':expected,
                       'user_agent_id':profile.user_agent_id,'replacement':replacement,'rollback':rollback},handle,indent=2)
            handle.flush();os.fsync(handle.fileno())
        backup.chmod(0o600);profile.parameters=replacement;profile.save(update_fields=['parameters']);profile.refresh_from_db();assert profile.parameters==replacement
    print('RETRY_PROFILE_ROLLED_BACK' if rollback else 'RETRY_PROFILE_APPLIED',json.dumps({'profile_id':6,'backup':str(backup),'restart':False}),flush=True)

if __name__=='__main__' or any(os.environ.get(k)=='1' for k in ('VENOM_RETRY_APPLY','VENOM_RETRY_ROLLBACK','VENOM_RETRY_CHECK')):main()
