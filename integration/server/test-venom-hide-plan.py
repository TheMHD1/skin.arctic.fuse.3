import runpy
from pathlib import Path
import unittest

action=runpy.run_path(str(Path(__file__).with_name('venom-hide-plan.py')))['action']

class HidePlanTests(unittest.TestCase):
    def test_hide_requires_evidence_and_safe_numbering(self):
        self.assertEqual(action(False,None,False,False,'id'),'keep_visible')
        self.assertEqual(action(False,None,True,False,'id'),'hide')
        self.assertEqual(action(False,None,True,False,'id',True),'compact_numbering_requires_review')
    def test_manual_hides_are_not_owned_or_restored(self):
        self.assertEqual(action(True,None,True,True,'id'),'respect_existing_hide')
    def test_reappearance_restores_only_owned_identity(self):
        previous={'identity':'id','status':'managed'}
        self.assertEqual(action(True,previous,False,True,'id'),'restore')
        self.assertEqual(action(True,previous,True,False,'id'),'keep_hidden')
        self.assertEqual(action(True,previous,False,True,'replacement'),'identity_changed')
    def test_user_unhide_is_never_undone(self):
        previous={'identity':'id','status':'managed'}
        self.assertEqual(action(False,previous,True,False,'id'),'manual_unhide')
        previous['status']='manual_unhide'
        self.assertEqual(action(False,previous,True,False,'id'),'respect_manual_unhide')

if __name__=='__main__':unittest.main()
