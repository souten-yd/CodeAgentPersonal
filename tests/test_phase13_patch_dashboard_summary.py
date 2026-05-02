import tempfile
import unittest
from pathlib import Path

from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class TestPhase13PatchDashboardSummary(unittest.TestCase):
    def test_empty_run(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            d = ps.get_run_patch_dashboard_summary('r0')
            self.assertEqual(d['counts']['total'], 0)

    def test_counts_and_flags(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            p1 = PatchProposal(patch_id='p1', run_id='r1', plan_id='pl', step_id='s1', target_file='a.py', patch_type='replace_block', generator='llm_replace_block', apply_allowed=False, quality_score=0.2, verification_status='failed', safety_warnings=['x'], quality_warnings=['q'])
            p2 = PatchProposal(patch_id='p2', run_id='r1', plan_id='pl', step_id='s2', target_file='b.py', patch_type='append', generator='append_mvp', apply_allowed=True, quality_score=0.9, verification_status='passed')
            ps.save_patch_proposal(p1)
            ps.save_patch_proposal(p2)
            ps.update_patch_payload('r1', 'p2', {'approval_status': 'approved'})
            m = [{'check_id': 'c1', 'run_id': 'r1', 'patch_id': 'p2'}]
            t = [{'telemetry_id': 't1', 'run_id': 'r1', 'patch_id': 'p2'}]
            d = ps.get_run_patch_dashboard_summary('r1', manual_checks=m, telemetry=t)
            self.assertEqual(d['counts']['total'], 2)
            self.assertEqual(d['counts']['apply_blocked'], 1)
            self.assertEqual(d['counts']['verification_failed'], 1)
            self.assertEqual(d['counts']['verification_passed'], 1)
            self.assertEqual(d['counts']['low_quality'], 1)
            self.assertEqual(d['counts']['patches_with_manual_check'], 1)
            self.assertEqual(d['counts']['patches_with_telemetry'], 1)
            self.assertIn('p1', d['attention']['reproposal_needed_patch_ids'])
            byid = {x['patch_id']: x for x in d['patches']}
            self.assertIn('blocked', byid['p1']['attention_flags'])
            self.assertIn('missing_telemetry', byid['p1']['attention_flags'])
            self.assertIn('missing_manual_check', byid['p1']['attention_flags'])


if __name__ == '__main__':
    unittest.main()
