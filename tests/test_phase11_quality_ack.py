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


if __name__ == '__main__':
    unittest.main()
