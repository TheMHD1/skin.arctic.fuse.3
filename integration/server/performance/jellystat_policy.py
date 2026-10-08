"""Native, database-scoped query budget for the reviewed Jellystat workload.

No stored-procedure rewrite, schema change, media deletion or PostgreSQL restart.
The caller supplies SQL/backup/restart adapters; private auth stays in memory.
"""
import json

PROCEDURE_MD5='dbd0c3eaf3051578a6ef0be0373750f1'
IMAGE='cyfershepard/jellystat:1.1.12@sha256:e61c759ec706da378bc8374e797da1dfd298ab30f804cefd82d192c301a888c7'
POLICY={'work_mem':'32MB','statement_timeout':'5min','lock_timeout':'15s'}

def identifier(value):
    import re
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',value):raise ValueError('Unsafe PostgreSQL identity')
    return '"'+value+'"'

def statements(role,database,settings):
    scope='ALTER ROLE '+identifier(role)+' IN DATABASE '+identifier(database)
    result=[]
    for key in POLICY:
        value=settings.get(key)
        if value is None:result.append(scope+' RESET '+key)
        elif value in (POLICY[key],'4MB','0'):
            result.append(scope+" SET "+key+"='"+value+"'")
        else:raise ValueError('Unreviewed query-budget value')
    return '; '.join(result)+';'

def deploy(snapshot,execute,backup,restart,journal,apply=False):
    before=snapshot()
    if (before['postgres_major']!=15 or before['jellystat_image']!=IMAGE
            or before['procedure_md5']!=PROCEDURE_MD5):raise ValueError('Unreviewed statistics schema/version')
    settings=before['settings']
    for key in POLICY:
        if settings.get(key) not in (None,POLICY[key]):raise ValueError('Unreviewed statistics policy drift')
    statements(before['role'],before['database'],settings)
    changes=[k for k,v in POLICY.items() if settings.get(k)!=v]
    result={'changes':changes,'scope':'Jellystat role in its own database','postgres_restart':False}
    if not apply or not changes:return result
    with journal.open('x') as f:
        journal.chmod(0o600);json.dump({'before':before,'after':POLICY},f,indent=2)
    # Dump first; an exclusive journal or failed backup cannot alter anything.
    backup()
    try:
        execute(statements(before['role'],before['database'],POLICY))
        if snapshot()['settings']!={**settings,**POLICY}:raise RuntimeError('Statistics policy readback mismatch')
        # Cancel only this procedure's old sessions, never generic media jobs.
        execute("SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE datname=current_database() "
                "AND usename=current_user AND state='active' AND query='CALL jd_remove_orphaned_data()' "
                "AND query_start < now()-interval '20 minutes';")
        restart()
    except BaseException:
        execute(statements(before['role'],before['database'],settings));restart();raise
    return result

if __name__=='__main__':
    import argparse
    from pathlib import Path
    import subprocess
    import time
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--container',default='jellystat');p.add_argument('--db-container',default='jellystat-db')
    p.add_argument('--journal',type=Path,required=True);p.add_argument('--backup',type=Path,required=True)
    p.add_argument('--apply',action='store_true');p.add_argument('--benchmark',action='store_true')
    a=p.parse_args()
    def run(args):return subprocess.check_output(args,text=True,timeout=30)
    info=json.loads(run(['docker','inspect',a.db_container]))[0]
    env=dict(row.split('=',1) for row in info['Config']['Env'] if '=' in row)
    role=env.get('POSTGRES_USER','postgres');database=env.get('POSTGRES_DB',role)
    identifier(role);identifier(database)
    command=['docker','exec',a.db_container,'psql','-X','-v','ON_ERROR_STOP=1','-U',role,'-d',database,'-At','-c']
    def execute(sql):return run(command+[sql])
    def snapshot():
        settings=json.loads(execute("SELECT COALESCE((SELECT to_json(setconfig) FROM pg_db_role_setting WHERE setrole=(SELECT oid FROM pg_roles WHERE rolname=current_user) AND setdatabase=(SELECT oid FROM pg_database WHERE datname=current_database())), '[]'::json)"))
        digest=execute("SELECT md5(pg_get_functiondef(oid)) FROM pg_proc WHERE proname='jd_remove_orphaned_data' AND pronamespace='public'::regnamespace").strip()
        return {'postgres_major':int(execute('SHOW server_version_num').strip())//10000,
            'jellystat_image':json.loads(run(['docker','inspect',a.container]))[0]['Config']['Image'],
            'procedure_md5':digest,'settings':dict(x.split('=',1) for x in settings),'role':role,'database':database}
    def backup():
        with a.backup.open('xb') as output:
            a.backup.chmod(0o600)
            subprocess.run(['docker','exec',a.db_container,'pg_dump','-U',role,'-d',database,'-Fc'],stdout=output,check=True,timeout=180)
        with a.backup.open('rb') as source:
            subprocess.run(['docker','exec','-i',a.db_container,'pg_restore','-l'],stdin=source,stdout=subprocess.DEVNULL,check=True,timeout=30)
    def restart():subprocess.run(['docker','restart','--time','15',a.container],check=True,timeout=60,stdout=subprocess.DEVNULL)
    print(json.dumps(deploy(snapshot,execute,backup,restart,a.journal,a.apply)))
    if a.benchmark:
        if not a.apply:raise SystemExit('Native maintenance benchmark requires explicit --apply')
        # Use the native procedure unchanged. This removes only its ordinary
        # orphaned statistics rows; it does not delete Jellyfin media/content.
        started=time.monotonic();execute('CALL jd_remove_orphaned_data()')
        print(json.dumps({'native_cleanup_seconds':round(time.monotonic()-started,3)}))
