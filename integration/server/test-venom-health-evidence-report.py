from pathlib import Path
import runpy
import unittest

evaluate=runpy.run_path(str(Path(__file__).with_name('venom-health-evidence-report.py')))['evaluate']

class EvidenceTests(unittest.TestCase):
    def test_absence_never_replaces_failure_evidence(self):
        state=evaluate([],{'time':1000000,'present':0},1000000,lambda *_:'keep_visible_pending_evidence')
        self.assertEqual(state,'keep_visible_pending_evidence')
    def test_reappearance_or_staleness_blocks_candidate(self):
        now=1000000;records=[{'time':now}];eligible=lambda *_:'eligible_for_reversible_hide'
        for presence in (None,{'time':now,'present':1},{'time':now-40*3600,'present':0}):
            self.assertNotEqual(evaluate(records,presence,now,eligible),'eligible_for_reversible_hide')
        self.assertNotEqual(evaluate([{'time':0}],{'time':now,'present':0},now,eligible),'eligible_for_reversible_hide')
        self.assertEqual(evaluate(records,{'time':now,'present':0},now,eligible),'eligible_for_reversible_hide')

if __name__=='__main__':unittest.main()
