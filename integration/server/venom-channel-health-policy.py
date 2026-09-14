"""Conservative, pure decision policy for the staged channel health worker.

Not a stream checker by itself and never changes gateway visibility.
Probe records must come from independent controlled measurements, not inferred
from a filename or a single failed client playback.
"""
from datetime import datetime, timezone

def classify(record):
    if record.get('capacity_available') is not True:return 'deferred_capacity'
    if record.get('decoded_video_frames',0)>=3 or record.get('decoded_audio_frames',0)>=10:return 'working'
    if record.get('control_ok') is not True:return 'inconclusive_network'
    code=record.get('http_status')
    if code in (401,403,429):return 'inconclusive_access_or_limit'
    if record.get('event_channel'):return 'inconclusive_off_air'
    if code in (404,410) and record.get('response_origin')=='provider':return 'missing_at_provider'
    return 'inconclusive_playback'

def decision(records,now):
    observations=sorted(records,key=lambda r:r['time'])
    outcomes=[(r,classify(r)) for r in observations]
    success=max((r['time'] for r,status in outcomes if status=='working'),default=0)
    # Repeated retries in one session count as ONE window, not independent
    # evidence. Never hide after timeout, failed HTML response or concurrency.
    missing=[r for r,status in outcomes if status=='missing_at_provider' and r['time']>success]
    windows={datetime.fromtimestamp(r['time'],timezone.utc).date() for r in missing}
    if len(windows)>=3 and missing[-1]['time']-missing[0]['time']>=48*3600:
        # Candidate only. The worker must additionally confirm persistent
        # provider removal before a reversible visibility change is allowed.
        if all(r.get('absent_from_provider_catalogue') is True for r in missing):return 'eligible_for_reversible_hide'
        return 'review_persistent_failure'
    if success and now-success<7*86400:return 'recently_working_keep_visible'
    return 'keep_visible_pending_evidence'
