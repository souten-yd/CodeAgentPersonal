import tempfile
import unittest
from pathlib import Path

from agent.manual_check_schema import ManualLLMCheckResult
from agent.manual_check_storage import ManualCheckStorage
from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class T(unittest.TestCase):
    def test_manual_check_storage(self):
        with tempfile.TemporaryDirectory() as td:
            st = ManualCheckStorage(Path(td))
            rec = ManualLLMCheckResult(check_id='c1', run_id='r1', patch_id='p1', notes='日本語メモ')
            st.save_manual_check(rec)
            self.assertEqual(st.load_manual_check('r1', 'c1')['notes'], '日本語メモ')
            self.assertEqual(len(st.list_manual_checks('r1')), 1)

    def test_manual_check_does_not_change_patch_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ps = PatchStorage(root)
            mcs = ManualCheckStorage(root)
            patch = PatchProposal(patch_id='p1', run_id='r1', plan_id='pl', step_id='s1', target_file='a.py', apply_allowed=True)
            ps.save_patch_proposal(patch)

            before = ps.load_patch('r1', 'p1')
            before_approval = before.get('approval_status', 'pending')
            before_applied = bool(before.get('applied', False))
            before_approvals_count = len(ps.list_patch_approvals('r1'))

            rec = ManualLLMCheckResult(check_id='c2', run_id='r1', patch_id='p1', reviewer='user', observed_issue='none', notes='日本語notes')
            mcs.save_manual_check(rec)

            after = ps.load_patch('r1', 'p1')
            self.assertEqual(after.get('approval_status', 'pending'), before_approval)
            self.assertEqual(bool(after.get('applied', False)), before_applied)
            self.assertEqual(len(ps.list_patch_approvals('r1')), before_approvals_count)

            checks = mcs.list_manual_checks('r1')
            self.assertEqual(len(checks), 1)
            self.assertEqual(checks[0]['notes'], '日本語notes')


if __name__ == '__main__':
    unittest.main()
