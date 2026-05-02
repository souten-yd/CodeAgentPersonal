import tempfile
import unittest
from pathlib import Path

from agent.patch_approval_manager import PatchApprovalManager
from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class T(unittest.TestCase):
    def test_quality_ack_rules(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            p = PatchProposal(patch_id='p1', run_id='r1', plan_id='pl', step_id='s1', target_file='a.py', apply_allowed=True, quality_score=0.3, quality_warnings=['日本語警告'])
            ps.save_patch_proposal(p)
            pm = PatchApprovalManager(ps)
            with self.assertRaises(ValueError):
                pm.decide('r1', 'p1', 'approve')
            ok = pm.decide('r1', 'p1', 'approve', quality_warnings_acknowledged=True, low_quality_acknowledged=True)
            a = ok['approval']
            self.assertEqual(a['quality_score_at_approval'], 0.3)
            self.assertIn('日本語警告', a['quality_warnings_at_approval'])

    def test_quality_warnings_only_ack_required(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            p = PatchProposal(patch_id='p2', run_id='r1', plan_id='pl', step_id='s1', target_file='a.py', apply_allowed=True, quality_score=0.8, quality_warnings=['warn'])
            ps.save_patch_proposal(p)
            pm = PatchApprovalManager(ps)
            with self.assertRaises(ValueError):
                pm.decide('r1', 'p2', 'approve')
            pm.decide('r1', 'p2', 'approve', quality_warnings_acknowledged=True)

    def test_low_quality_only_ack_required(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            p = PatchProposal(patch_id='p3', run_id='r1', plan_id='pl', step_id='s1', target_file='a.py', apply_allowed=True, quality_score=0.2, quality_warnings=[])
            ps.save_patch_proposal(p)
            pm = PatchApprovalManager(ps)
            with self.assertRaises(ValueError):
                pm.decide('r1', 'p3', 'approve')
            pm.decide('r1', 'p3', 'approve', low_quality_acknowledged=True)

    def test_no_quality_issue_no_ack_needed(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            p = PatchProposal(patch_id='p4', run_id='r1', plan_id='pl', step_id='s1', target_file='a.py', apply_allowed=True, quality_score=0.9, quality_warnings=[])
            ps.save_patch_proposal(p)
            pm = PatchApprovalManager(ps)
            out = pm.decide('r1', 'p4', 'approve')
            self.assertEqual(out['approval']['status'], 'approved')

    def test_safety_and_risk_ack_still_required(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            p = PatchProposal(patch_id='p5', run_id='r1', plan_id='pl', step_id='s1', target_file='a.py', apply_allowed=True, risk_level='high', safety_warnings=['s1'], quality_score=0.9)
            ps.save_patch_proposal(p)
            pm = PatchApprovalManager(ps)
            with self.assertRaises(ValueError):
                pm.decide('r1', 'p5', 'approve')
            with self.assertRaises(ValueError):
                pm.decide('r1', 'p5', 'approve', risk_acknowledged=True)
            out = pm.decide('r1', 'p5', 'approve', risk_acknowledged=True, safety_warnings_acknowledged=True)
            self.assertEqual(out['approval']['status'], 'approved')


if __name__ == '__main__':
    unittest.main()
