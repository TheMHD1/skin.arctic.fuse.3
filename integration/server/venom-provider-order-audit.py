"""Run via Dispatcharr Django shell; read only, no stream opened."""
import json
from pathlib import Path
import urllib.parse
import urllib.request
from apps.m3u.models import M3UAccount

try:
    account=M3UAccount.objects.get(name='Venom TV')
    parts=urllib.parse.urlsplit(account.server_url)
    base=urllib.parse.urlunsplit((parts.scheme,parts.netloc,'/player_api.php','',''))
    query=urllib.parse.urlencode({'username':account.username,'password':account.password,'action':'get_live_categories'})
    with urllib.request.urlopen(base+'?'+query,timeout=25) as response:
        rows=json.loads(response.read(1024*1024))
    if not isinstance(rows,list):raise ValueError('Invalid categories')
    data={'source_categories':[{k:r.get(k) for k in ('category_id','category_name')} for r in rows]}
    Path('/tmp/venom-provider-order.json').write_text(json.dumps(data,ensure_ascii=False))
    print(json.dumps({'source_category_count':len(rows),'first_names':[r['category_name'] for r in rows[:5]]},ensure_ascii=False))
except Exception as exc:
    print(json.dumps({'audit_error':type(exc).__name__}))
