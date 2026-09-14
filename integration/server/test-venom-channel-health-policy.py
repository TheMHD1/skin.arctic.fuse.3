import runpy
from pathlib import Path
import unittest

m=runpy.run_path(str(Path(__file__).with_name('venom-channel-health-policy.py')))

class PolicyTests(unittest.TestCase):
    def record(self,t=1728000000,**changes):
        return dict(time=t,capacity_available=True,control_ok=True,http_status=404,response_origin='provider',**changes)
    def test_parallel_contention_never_dead(self):
        r=self.record();r['capacity_available']=False
        self.assertEqual(m['classify'](r),'deferred_capacity')
    def test_access_denied_and_gateway_errors_are_not_dead(self):
        for code in (401,403,429,500,502,503):
            r=self.record();r['http_status']=code
            self.assertNotEqual(m['classify'](r),'missing_at_provider')
        r=self.record();r['response_origin']='gateway'
        self.assertNotEqual(m['classify'](r),'missing_at_provider')
    def test_event_offair_and_bad_control_not_dead(self):
        self.assertEqual(m['classify'](self.record(event_channel=True)),'inconclusive_off_air')
        r=self.record();r['control_ok']=False
        self.assertEqual(m['classify'](r),'inconclusive_network')
    def test_retries_same_day_not_independent(self):
        rows=[self.record(t=1728000000+i) for i in range(50)]
        self.assertEqual(m['decision'](rows,1728000100),'keep_visible_pending_evidence')
    def test_three_days_still_requires_catalogue_removal(self):
        rows=[self.record(t=1728000000+i*86400) for i in range(3)]
        self.assertEqual(m['decision'](rows,1728300000),'review_persistent_failure')
        for row in rows:row['absent_from_provider_catalogue']=True
        self.assertEqual(m['decision'](rows,1728300000),'eligible_for_reversible_hide')
    def test_recovery_clears_old_failure_evidence(self):
        rows=[self.record(t=1728000000+i*86400,absent_from_provider_catalogue=True) for i in range(3)]
        rows.append(self.record(t=1728300000,decoded_video_frames=3))
        self.assertEqual(m['decision'](rows,1728300001),'recently_working_keep_visible')
    def test_decoded_frames_are_positive_evidence_without_control(self):
        r=self.record(decoded_video_frames=3);r.pop('control_ok')
        self.assertEqual(m['classify'](r),'working')

if __name__=='__main__':unittest.main()
