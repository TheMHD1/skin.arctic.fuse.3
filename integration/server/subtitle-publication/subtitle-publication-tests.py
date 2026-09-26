import importlib.util
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('publication',ROOT/'subtitle-publication-queue.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
jobs = q.load(ROOT,'subtitle-library-jobs')
raw_spec = importlib.util.spec_from_file_location('raw_arrival',ROOT/'subtitle-raw-arrival.py')
raw = importlib.util.module_from_spec(raw_spec)
raw_spec.loader.exec_module(raw)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = str(self.root/'Show - S01E02 - The Witness WEBDL-2160p.mkv')
        Path(self.video).write_bytes(b'movie')
        self.db = jobs.connect(self.root/'four-track-jobs.sqlite')
        self.addCleanup(self.db.close)
        jobs.enqueue(self.db,self.video)
        self.revision = 'one'
        self.sig = jobs.signature(self.video)
        self.patch = patch.object(q,'snapshot',side_effect=lambda *args:(self.revision,self.sig,{}))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.valid = True
        self.verifier = SimpleNamespace(manifest_verified=lambda *a:self.valid,expected_version=lambda *a:'v')

    def enqueue(self):
        q.enqueue(self.video,self.root)
        return self.db.execute('SELECT * FROM jellyfin_publications').fetchone()

    def job(self): return self.db.execute('SELECT * FROM jobs').fetchone()

    def test_generation_success_is_not_jellyfin_success(self):
        jobs.result_state(self.db,self.video,0,True,'files ready')
        self.assertEqual(self.job()['status'],'awaiting_jellyfin')
        self.assertEqual(self.job()['verified'],0)

    def test_enqueue_is_durable_and_preserves_backoff(self):
        self.enqueue()
        self.db.execute('UPDATE jellyfin_publications SET attempts=4,available=12345')
        self.db.commit()
        self.enqueue()
        with q.connect(self.root) as fresh:
            row=fresh.execute('SELECT * FROM jellyfin_publications').fetchone()
        self.assertEqual((row['attempts'],row['available']),(4,12345))

    def test_identical_managed_revision_cannot_resurrect_deadletter(self):
        self.enqueue()
        with self.db:
            self.db.execute("UPDATE jellyfin_publications SET status='deadletter',attempts=7,available=0")
        self.enqueue()
        row=self.db.execute('SELECT status,attempts FROM jellyfin_publications').fetchone()
        self.assertEqual((row['status'],row['attempts']),('deadletter',7))

    def test_new_revision_resets_old_retry(self):
        self.enqueue()
        self.db.execute('UPDATE jellyfin_publications SET attempts=4,available=12345')
        self.db.commit()
        self.revision='two'
        row=self.enqueue()
        self.assertEqual((row['revision'],row['attempts'],row['available']),('two',0,0))

    def test_unverified_queue_cannot_complete_job(self):
        row=self.enqueue()
        jobs.result_state(self.db,self.video,0,True,'files')
        q.acknowledge(self.db,row,self.root,self.verifier,None)
        self.assertEqual(self.job()['status'],'awaiting_jellyfin')

    def test_verified_acknowledgement(self):
        row=self.enqueue()
        jobs.result_state(self.db,self.video,0,True,'files')
        self.db.execute("UPDATE jellyfin_publications SET status='complete'")
        self.db.commit()
        q.acknowledge(self.db,row,self.root,self.verifier,None)
        self.assertEqual(self.job()['status'],'complete')
        self.assertGreater(self.job()['verified'],0)

    def test_producer_finishes_after_ack(self):
        row=self.enqueue()
        self.db.execute("UPDATE jobs SET status='running'")
        self.db.execute("UPDATE jellyfin_publications SET status='complete'")
        self.db.commit()
        q.acknowledge(self.db,row,self.root,self.verifier,None)
        self.assertEqual(self.job()['status'],'running')
        jobs.result_state(self.db,self.video,0,True,'files')
        q.acknowledge(self.db,row,self.root,self.verifier,None)
        self.assertEqual(self.job()['status'],'complete')

    def test_stale_revision_never_acknowledges_new_files(self):
        row=self.enqueue()
        jobs.result_state(self.db,self.video,0,True,'files')
        self.revision='two'
        self.enqueue()
        q.acknowledge(self.db,row,self.root,self.verifier,None)
        self.assertNotEqual(self.job()['status'],'complete')
        latest=self.db.execute('SELECT * FROM jellyfin_publications').fetchone()
        self.assertEqual((latest['revision'],latest['status']),('two','pending'))

    def test_deleted_media_not_resurrected(self):
        row=self.enqueue()
        jobs.result_state(self.db,self.video,0,True,'files')
        Path(self.video).unlink()
        q.acknowledge(self.db,row,self.root,self.verifier,None)
        self.assertEqual(self.job()['status'],'missing')

    def test_changed_inputs_return_to_generation(self):
        row=self.enqueue()
        jobs.result_state(self.db,self.video,0,True,'files')
        self.valid=False
        q.acknowledge(self.db,row,self.root,self.verifier,None)
        self.assertEqual(self.job()['status'],'pending')

    def test_resolver_exact_path_and_cache(self):
        self.enqueue()
        requests=[]
        def request(path):
            requests.append(path)
            return json.dumps({'Items':[{'Id':'abc','Path':self.video}]}).encode()
        self.assertEqual(q.resolve(self.db,self.video,request),'abc')
        self.assertIn('SearchTerm=The+Witness',requests[0])
        requests.clear()
        self.assertEqual(q.resolve(self.db,self.video,request),'abc')
        self.assertEqual(len(requests),1)
        self.assertIn('Ids=abc',requests[0])

    def test_refresh_hint_throttling(self):
        self.enqueue()
        self.assertTrue(q.hint_due(self.db,'item:abc'))
        q.record_hint(self.db,'item:abc')
        self.assertFalse(q.hint_due(self.db,'item:abc'))
        self.assertTrue(q.hint_due(self.db,'item:other'))

    def test_all_publication_paths_use_the_same_finite_taper(self):
        self.assertEqual(q.RETRY_DELAYS, (30, 120, 600, 1800, 7200, 21600, 43200))
        self.assertEqual(q.publication_delay(q.LookupPending('missing'), 0), 30)
        self.assertEqual(q.publication_delay(q.ViewPending('view'), 3), 1800)
        self.assertEqual(q.publication_delay(RuntimeError(), 9000), 43200)

    def test_exact_parent_refresh_not_iptv(self):
        self.enqueue();calls=[]
        def request(path,method='GET'):
            calls.append((path,method))
            return json.dumps({'Items':[{'Id':'local','Path':str(Path(self.video).parent)},
                {'Id':'iptv','Path':'/config/venom-catalogue/series/Show'}]}).encode()
        self.assertTrue(q.refresh_parent(self.db,self.video,request))
        self.assertIn('/Items/local/Refresh?',calls[-1][0])
        self.assertFalse(q.refresh_parent(self.db,self.video,request))
        self.assertEqual(len(calls),2)

    def test_parent_wrong_path_never_refreshed(self):
        self.enqueue();calls=[]
        def request(path,method='GET'):
            calls.append(method)
            return json.dumps({'Items':[{'Id':'other','Path':'/wrong'}]}).encode()
        self.assertFalse(q.refresh_parent(self.db,self.video,request))
        self.assertEqual(calls,['GET'])

    def test_missing_view_is_not_missing_canonical_media(self):
        view=self.root/'view';view.mkdir()
        with self.assertRaises(q.ViewPending):q.check_view(self.video,str(self.root),str(view))
        self.assertTrue(Path(self.video).is_file())
        (view/Path(self.video).name).write_bytes(b'compatible')
        q.check_view(self.video,str(self.root),str(view))

    def test_transport_circuit_stops_a_due_batch_without_consuming_more_attempts(self):
        self.enqueue()
        q.defer(self.db, 'jellyfin_publications', 'video', self.video, 0, time.time(), TimeoutError())
        self.assertTrue(q.circuit_open(self.db))
        self.assertEqual(self.db.execute('SELECT attempts FROM jellyfin_publications').fetchone()[0], 1)

    def test_final_twelve_hour_retry_precedes_deadletter(self):
        self.enqueue()
        status, available=q.defer(self.db,'jellyfin_publications','video',self.video,6,time.time(),RuntimeError(),revision=self.revision)
        self.assertEqual(status,'pending')
        self.assertEqual(self.db.execute('SELECT attempts FROM jellyfin_publications').fetchone()[0],7)
        self.assertGreaterEqual(round(available-time.time()),43199)
        status, _=q.defer(self.db,'jellyfin_publications','video',self.video,7,time.time(),RuntimeError(),revision=self.revision)
        self.assertEqual(status,'deadletter')

    def test_aged_row_deadletters_before_network_attempt(self):
        self.enqueue()
        self.assertTrue(q.expire_if_aged(self.db,'jellyfin_publications','video',self.video,time.time()-q.MAX_AGE-1,self.revision))
        self.assertEqual(self.db.execute('SELECT status FROM jellyfin_publications').fetchone()[0],'deadletter')

    def test_resolver_does_not_trust_same_title_wrong_path(self):
        self.enqueue()
        with self.assertRaises(RuntimeError):
            q.resolve(self.db,self.video,lambda p:json.dumps({'Items':[{'Id':'abc','Path':'/other/file.mkv'}]}).encode())

    def test_resolver_duplicate_exact_path_rejected(self):
        self.enqueue()
        with self.assertRaises(RuntimeError):
            q.resolve(self.db,self.video,lambda p:json.dumps({'Items':[{'Id':x,'Path':self.video} for x in ('a','b')]}).encode())

    def test_series_inventory_recovers_wrong_metadata_without_title_match(self):
        self.enqueue()
        parent = str(Path(self.video).parent)
        def request(path):
            if 'IncludeItemTypes=Episode%2CMovie' in path:
                return json.dumps({'Items': []}).encode()
            if 'IncludeItemTypes=Series' in path and 'SearchTerm=' in path:
                return json.dumps({'Items': [{'Id':'venom','Path':'/config/venom-catalogue/series/42'}],
                    'TotalRecordCount':1}).encode()
            if 'IncludeItemTypes=Series' in path and 'ParentId' not in path:
                return json.dumps({'Items': [{'Id':'local-series','Path':parent},
                    {'Id':'venom','Path':'/config/venom-catalogue/series/42'}],
                    'TotalRecordCount':2}).encode()
            if 'ParentId=local-series' in path:
                return json.dumps({'Items':[{'Id':'episode','Path':self.video}]}).encode()
            return json.dumps({'Items': []}).encode()
        self.assertEqual(q.resolve(self.db,self.video,request),'episode')
        self.assertEqual(self.db.execute('SELECT item_id FROM jellyfin_series_path_cache WHERE path=?',
            (parent,)).fetchone()['item_id'],'local-series')

    def test_series_parent_search_strips_filesystem_year_but_still_requires_paths(self):
        parent = self.root/'New Amsterdam (2018)'
        parent.mkdir()
        video = str(parent/'New Amsterdam (2018) - S04E13 - Family WEBDL-1080p.mkv')
        Path(video).write_bytes(b'movie')
        terms=[]
        def request(path):
            if 'IncludeItemTypes=Episode%2CMovie' in path:
                return json.dumps({'Items': []}).encode()
            if 'IncludeItemTypes=Series' in path and 'SearchTerm=' in path:
                terms.append(path)
                if 'SearchTerm=New+Amsterdam&' in path:
                    return json.dumps({'Items':[{'Id':'local-series','Path':str(parent)}]}).encode()
                return json.dumps({'Items': []}).encode()
            if 'ParentId=local-series' in path:
                return json.dumps({'Items':[{'Id':'episode','Path':video}]}).encode()
            return json.dumps({'Items': []}).encode()
        with q.connect(self.root) as publication_db:
            self.assertEqual(q.resolve(publication_db,video,request),'episode')
        self.assertTrue(any('SearchTerm=New+Amsterdam&' in call for call in terms))

    def test_series_inventory_does_not_stop_on_omitted_total_count(self):
        self.enqueue()
        parent = str(Path(self.video).parent)
        pages=[]
        def request(path):
            if 'IncludeItemTypes=Episode%2CMovie' in path:
                return json.dumps({'Items': []}).encode()
            if 'IncludeItemTypes=Series' in path and 'SearchTerm=' in path:
                return json.dumps({'Items': []}).encode()
            if 'IncludeItemTypes=Series' in path and 'ParentId' not in path:
                pages.append(path)
                if 'StartIndex=0' in path:
                    return json.dumps({'Items':[{'Id':'other-'+str(i),'Path':'/other/'+str(i)} for i in range(500)]}).encode()
                return json.dumps({'Items':[{'Id':'local-series','Path':parent}]}).encode()
            if 'ParentId=local-series' in path:
                return json.dumps({'Items':[{'Id':'episode','Path':self.video}]}).encode()
            return json.dumps({'Items': []}).encode()
        self.assertEqual(q.resolve(self.db,self.video,request),'episode')
        self.assertEqual(len(pages),2)
        self.assertTrue(all('EnableTotalRecordCount=true' in path for path in pages))

    def test_series_inventory_revision_rebuilds_a_stale_partial_index(self):
        self.enqueue()
        parent = str(Path(self.video).parent)
        # Simulate the old paginator marking its one-page partial result as
        # fresh.  A code deployment must not wait fifteen minutes to discover
        # an exact physical parent that was beyond that page.
        with self.db:
            self.db.execute("INSERT INTO jellyfin_series_inventory_state(id,scanned,revision) VALUES(1,?,?)",
                            (time.time(), 'exact-path-pagination-v1'))
        calls=[]
        def request(path):
            calls.append(path)
            if 'IncludeItemTypes=Episode%2CMovie' in path:
                return json.dumps({'Items': []}).encode()
            if 'IncludeItemTypes=Series' in path and 'SearchTerm=' in path:
                return json.dumps({'Items': []}).encode()
            if 'IncludeItemTypes=Series' in path and 'ParentId' not in path:
                return json.dumps({'Items':[{'Id':'local-series','Path':parent}],
                                   'TotalRecordCount':1}).encode()
            if 'ParentId=local-series' in path:
                return json.dumps({'Items':[{'Id':'episode','Path':self.video}]}).encode()
            return json.dumps({'Items': []}).encode()
        self.assertEqual(q.resolve(self.db,self.video,request),'episode')
        self.assertTrue(any('EnableTotalRecordCount=true' in call for call in calls))
        self.assertEqual(self.db.execute('SELECT revision FROM jellyfin_series_inventory_state WHERE id=1').fetchone()[0],
                         q.SERIES_INVENTORY_REVISION)

    def test_series_inventory_is_rate_limited_when_no_exact_parent_exists(self):
        self.enqueue()
        calls=[]
        def request(path):
            calls.append(path)
            return json.dumps({'Items': [], 'TotalRecordCount':0}).encode()
        with self.assertRaises(q.LookupPending): q.resolve(self.db,self.video,request)
        first=len([p for p in calls if 'IncludeItemTypes=Series' in p and 'ParentId' not in p and 'SearchTerm=' not in p])
        with self.assertRaises(q.LookupPending): q.resolve(self.db,self.video,request)
        second=len([p for p in calls if 'IncludeItemTypes=Series' in p and 'ParentId' not in p and 'SearchTerm=' not in p])
        self.assertEqual((first,second),(1,1))

    def test_jellyfin_outage_only_retries_publication(self):
        self.enqueue()
        jobs.result_state(self.db,self.video,0,True,'files')
        (self.root/'post-sub.sh').write_text('JELLYFIN_URL="http://test"\nJELLYFIN_KEY="test"')
        fake_jobs=SimpleNamespace(load_engine=lambda *a:None,
            manifest_verified=lambda *a:True,expected_version=lambda *a:'v')
        sync=SimpleNamespace(synchronize=lambda *a,**kw:None)
        with patch.object(q,'load',side_effect=lambda root,name:fake_jobs if name=='subtitle-library-jobs' else sync), \
             patch.object(q,'resolve',side_effect=TimeoutError('Jellyfin unavailable')):
            q.work(self.root)
        row=self.db.execute('SELECT * FROM jellyfin_publications').fetchone()
        self.assertEqual((row['status'],row['attempts']),('pending',1))
        self.assertGreater(row['available'],0)
        self.assertEqual((self.job()['status'],self.job()['attempts']),('awaiting_jellyfin',0))

    def test_missing_manifest_cannot_starve_ack_reconciliation(self):
        row=self.enqueue()
        jobs.result_state(self.db,self.video,0,True,'files')
        with patch.object(q,'snapshot',side_effect=FileNotFoundError):
            self.assertFalse(q.acknowledge(self.db,row,self.root,self.verifier,None))
        self.assertEqual(self.job()['status'],'pending')

    def test_new_import_defers_without_new_title_notification(self):
        self.enqueue()
        jobs.result_state(self.db,self.video,0,True,'files')
        (self.root/'post-sub.sh').write_text('JELLYFIN_URL="http://test"\nJELLYFIN_KEY="test"')
        fake_jobs=SimpleNamespace(load_engine=lambda *a:None,
            manifest_verified=lambda *a:True,expected_version=lambda *a:'v')
        sync=SimpleNamespace(synchronize=lambda *a,**kw:None)
        from unittest.mock import MagicMock
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b''
        with patch.object(q,'load',side_effect=lambda root,name:fake_jobs if name=='subtitle-library-jobs' else sync), \
             patch.object(q,'resolve',side_effect=q.LookupPending('new import')), \
             patch.object(q.urllib.request,'urlopen',return_value=response) as post:
            q.work(self.root)
        self.assertEqual(post.call_count,0)
        self.assertEqual(self.job()['status'],'awaiting_jellyfin')


class RawArrivalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.canonical = self.root/'media'; self.view = self.root/'view'
        (self.canonical/'shows').mkdir(parents=True); self.view.mkdir()
        self.video = self.canonical/'shows'/'Movie.mkv'; self.subtitle = self.canonical/'shows'/'Movie.en.srt'
        self.video.write_bytes(b'video'); self.subtitle.write_bytes(b'1\n00:00:00,000 --> 00:00:01,000\nOne\n')

    def rows(self):
        db, _ = raw.connect(self.root)
        try:return db.execute('SELECT * FROM raw_subtitle_arrivals').fetchall()
        finally:db.close()

    def test_duplicate_fingerprint_keeps_existing_retry_budget(self):
        raw.enqueue(self.root,self.video,self.subtitle,now=100,canonical=self.canonical)
        db, _ = raw.connect(self.root)
        with db: db.execute('UPDATE raw_subtitle_arrivals SET attempts=3,available=999')
        db.close()
        raw.enqueue(self.root,self.video,self.subtitle,now=200,canonical=self.canonical)
        row=self.rows()[0]
        self.assertEqual((row['attempts'],row['available'],row['first_seen']),(3,999,100))

    def test_changed_provider_bytes_create_a_fresh_revision(self):
        first=raw.enqueue(self.root,self.video,self.subtitle,now=100,canonical=self.canonical)
        self.subtitle.write_bytes(b'two')
        second=raw.enqueue(self.root,self.video,self.subtitle,now=200,canonical=self.canonical)
        self.assertNotEqual(first,second)
        self.assertEqual(len(self.rows()),2)

    def test_host_view_sidecar_uses_logical_jellyfin_paths_and_served_ack(self):
        target = self.view/'shows'/'Movie.mkv'; target.parent.mkdir(); target.write_bytes(b'video')
        (self.view/'shows'/'Movie.en.srt').write_bytes(b'old provider inode')
        raw.enqueue(self.root,self.video,self.subtitle,canonical=self.canonical)
        (self.root/'post-sub.sh').write_text('JELLYFIN_URL="http://test"\nJELLYFIN_KEY="test"')
        calls=[]
        def request(path, method='GET'):
            calls.append((path,method))
            if path.startswith('/Items?Ids='):
                return json.dumps({'Items':[{'Id':'item','Path':str(self.video),'MediaSources':[{'Id':'source'}],
                    'MediaStreams':[{'Type':'Subtitle','IsExternal':True,'Path':str(self.subtitle),'Index':7}]}]}).encode()
            if '/Stream.srt' in path:return b'1\r\n00:00:00,000 --> 00:00:01,000\r\nOne\r\n'
            return b''
        db, _ = raw.connect(self.root)
        with patch.object(raw,'connect',return_value=(db, q)), patch.object(raw,'config_request',return_value=('', '', request)), patch.object(q,'resolve',return_value='item') as resolve:
            raw.work(self.root,canonical=self.canonical,view=self.view)
        self.assertEqual(resolve.call_args.args[1],str(self.video))
        self.assertTrue((self.view/'shows'/'Movie.en.srt').is_file())
        self.assertEqual((self.view/'shows'/'Movie.en.srt').read_bytes(), self.subtitle.read_bytes())
        self.assertEqual(self.rows()[0]['status'],'complete')
        self.assertTrue(any(method=='POST' and '/Items/item/Refresh?' in path for path,method in calls))

    def test_raw_http_failure_opens_shared_circuit(self):
        target = self.view/'shows'/'Movie.mkv'; target.parent.mkdir(); target.write_bytes(b'video')
        raw.enqueue(self.root,self.video,self.subtitle,canonical=self.canonical)
        db, _ = raw.connect(self.root); self.addCleanup(db.close)
        def offline(path, method='GET'): raise TimeoutError('offline')
        with patch.object(raw,'connect',return_value=(db, q)), patch.object(raw,'config_request',return_value=('', '', offline)), patch.object(q,'resolve',return_value='item'):
            raw.work(self.root,canonical=self.canonical,view=self.view)
        db, _ = raw.connect(self.root); self.addCleanup(db.close)
        self.assertTrue(q.circuit_open(db))
        self.assertEqual(db.execute('SELECT attempts FROM raw_subtitle_arrivals').fetchone()[0],1)

    def test_missing_view_root_defers_before_jellyfin_request(self):
        raw.enqueue(self.root,self.video,self.subtitle,canonical=self.canonical)
        db, _ = raw.connect(self.root)
        calls=[]
        def request(path, method='GET'): calls.append(path); return b'{}'
        with patch.object(raw,'connect',return_value=(db, q)), patch.object(raw,'config_request',return_value=('', '', request)):
            raw.work(self.root,canonical=self.canonical,view=self.root/'absent-view')
        self.assertEqual(calls,[])


if __name__ == '__main__': unittest.main()
