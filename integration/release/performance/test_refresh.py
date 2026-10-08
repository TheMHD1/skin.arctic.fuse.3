import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'plugin.video.venom.tv'))
spec=importlib.util.spec_from_file_location('favorite_lane',HERE/'favorite_refresh.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Worker:
    def __init__(self):self.pending=None;self.result=None;self.closed=False
    def submit(self,generation,name,work):self.pending=(generation,name,work);return True
    def discard_pending(self):self.pending=None
    def poll(self):result=self.result;self.result=None;return result
    def close(self):self.closed=True

class Tests(unittest.TestCase):
    def test_idle_delay_and_busy_foreground_do_not_submit_optional_work(self):
        worker=Worker();lane=m.FavoriteRefresh(worker,{},lambda v:None,now=10)
        lane.poll(now=11);self.assertIsNone(worker.pending)
        lane.poll(blocked=True,now=12);self.assertIsNone(worker.pending)
        lane.poll(now=13);self.assertIsNotNone(worker.pending)
        pending=worker.pending;lane.poll(now=100);self.assertIs(worker.pending,pending)
    def test_read_cannot_replace_foreground_or_run_twice(self):
        worker=Worker();seen=[];lane=m.FavoriteRefresh(worker,{},seen.append,now=0)
        lane.poll(now=2);worker.result=(0,'read',({'one'},False),None,1)
        lane.poll(blocked=True,now=3);self.assertEqual(seen,[({'one'},False)])
        self.assertFalse(lane.busy);self.assertEqual(lane.due,32)
    def test_mutation_invalidates_old_result_and_request(self):
        worker=Worker();seen=[];lane=m.FavoriteRefresh(worker,{},seen.append,now=0)
        with patch.object(m.shared_favorites,'SharedFavorites') as client:
            lane.poll(now=2);job=worker.pending
            lane.invalidate();job[2]()
            self.assertTrue(client.return_value.keys.call_args.kwargs['cancelled']())
        worker.result=(0,'read',({'old'},False),None,1)
        lane.poll(blocked=True,now=3);self.assertEqual(seen,[])
    def test_close_retires_worker_and_never_applies_late_data(self):
        worker=Worker();seen=[];lane=m.FavoriteRefresh(worker,{},seen.append,now=0)
        lane.poll(now=2);lane.close();worker.result=(0,'read',({'old'},False),None,1)
        lane.poll(now=99);self.assertEqual(seen,[]);self.assertTrue(worker.closed)
    def test_error_retains_existing_keys_and_throttles_retry(self):
        worker=Worker();seen=[];lane=m.FavoriteRefresh(worker,{},seen.append,now=0)
        lane.poll(now=2);worker.result=(0,'read',None,TimeoutError(),1)
        lane.poll(now=3);self.assertEqual(seen,[(None,True)]);self.assertEqual(lane.due,32)

if __name__=='__main__':unittest.main()
