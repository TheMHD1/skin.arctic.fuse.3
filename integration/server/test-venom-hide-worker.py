import contextlib
import io
import json
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parent
worker=runpy.run_path(str(ROOT/'venom-hide-confirmed-worker.py'))
decision=runpy.run_path(str(ROOT/'venom-channel-health-policy.py'))['decision']
action=runpy.run_path(str(ROOT/'venom-hide-plan.py'))['action']

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=time.time()
        with sqlite3.connect(self.root/'provider-presence.sqlite3') as db:
            db.execute('create table observations(channel_id integer,time real,present integer,source_ids text)')
            db.execute('insert into observations values(7,?,0,?)',(self.now,json.dumps(['99'])))
        with sqlite3.connect(self.root/'provider-negative-evidence.sqlite3') as db:
            db.execute('create table observations(channel_id integer,time real,record text)')
            for days in (3,2,0):
                stamp=self.now-days*86400
                record=dict(time=stamp,capacity_available=True,control_ok=True,http_status=404,response_origin='provider',absent_from_provider_catalogue=True,provider_source_ids=['99'])
                db.execute('insert into observations values(7,?,?)',(stamp,json.dumps(record)))
        self.channel=types.SimpleNamespace(uuid='stable',auto_created_by_id=1,channel_number=33,hidden_from_output=False,
            streams=types.SimpleNamespace(all=lambda:[types.SimpleNamespace(m3u_account_id=1,stream_id=99)]),
            save=lambda **kw:None,refresh_from_db=lambda:None)
        manager=types.SimpleNamespace(select_for_update=lambda:manager,filter=lambda **kw:manager,first=lambda:self.channel)
        self.modules={'django':types.ModuleType('django'),'django.db':types.SimpleNamespace(transaction=types.SimpleNamespace(atomic=contextlib.nullcontext)),
          'apps':types.ModuleType('apps'),'apps.channels':types.ModuleType('apps.channels'),
          'apps.channels.models':types.SimpleNamespace(Channel=types.SimpleNamespace(objects=manager)),
          'apps.channels.compact_numbering':types.SimpleNamespace(get_group_relation_for_channel=lambda c:None,is_compact_group=lambda r:False)}
    def execute(self,apply=False,success=None):
        output=io.StringIO()
        def load(path):return {'decision':decision} if 'health-policy' in path else {'action':action}
        with patch.dict(sys.modules,self.modules),patch.dict(worker['main'].__globals__,ROOT=self.root),patch.object(worker['runpy'],'run_path',side_effect=load),patch.object(sys,'stdin',io.StringIO(json.dumps({'generated':time.time(),'apply':apply,'success':success or {}}))),contextlib.redirect_stdout(output):
            worker['main']()
        return json.loads(output.getvalue())
    def test_dry_run_does_not_write_ledger_or_channel(self):
        result=self.execute()
        self.assertEqual(result['decisions'],{'hide':1});self.assertFalse(self.channel.hidden_from_output)
        self.assertFalse((self.root/'venom-hidden-channels.json').exists())
    def test_hide_restore_retains_number_and_identity(self):
        self.assertEqual(self.execute(True)['changed'],1);self.assertTrue(self.channel.hidden_from_output)
        with sqlite3.connect(self.root/'provider-presence.sqlite3') as db:db.execute('update observations set present=1')
        self.assertEqual(self.execute(True)['changed'],1);self.assertFalse(self.channel.hidden_from_output)
        self.assertEqual(self.channel.channel_number,33);self.assertEqual(self.channel.uuid,'stable')
    def test_recent_working_observation_blocks_hide(self):
        self.assertEqual(self.execute(True,{'7':self.now+0.01})['changed'],0)
    def test_existing_manual_hide_is_untouched(self):
        self.channel.hidden_from_output=True
        self.assertEqual(self.execute(True)['decisions'],{'respect_existing_hide':1})
        self.assertFalse((self.root/'venom-hidden-channels.json').exists())

if __name__=='__main__':unittest.main()
