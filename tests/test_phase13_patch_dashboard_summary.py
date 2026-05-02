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

    def test_phase13_5_quality_and_telemetry_rules(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            # A: append patch without quality_score should not be low_quality.
            p_append = PatchProposal(
                patch_id='p_append', run_id='r2', plan_id='pl', step_id='s0',
                target_file='append.txt', patch_type='append', generator='append_mvp', apply_allowed=True
            )
            # B: evaluated LLM patch with low score.
            p_low = PatchProposal(
                patch_id='p_low', run_id='r2', plan_id='pl', step_id='s1',
                target_file='a.py', patch_type='replace_block', generator='llm_replace_block',
                apply_allowed=False, quality_score=0.2
            )
            # C: evaluated LLM patch with high score.
            p_high = PatchProposal(
                patch_id='p_high', run_id='r2', plan_id='pl', step_id='s2',
                target_file='b.py', patch_type='replace_block', generator='llm_replace_block',
                apply_allowed=True, quality_score=0.9
            )
            # D/E/F: LLM replace_block without quality score, approved not applied, fallback telemetry only.
            p_no_quality = PatchProposal(
                patch_id='p_no_quality', run_id='r2', plan_id='pl', step_id='s3',
                target_file='c.py', patch_type='replace_block', generator='llm_replace_block',
                apply_allowed=True, approval_status='approved', metadata={'fallback_telemetry_id': 't_fallback'}
            )
            # G: llm_telemetry_id only.
            p_main_tid = PatchProposal(
                patch_id='p_main_tid', run_id='r2', plan_id='pl', step_id='s4',
                target_file='d.py', patch_type='replace_block', generator='llm_replace_block',
                apply_allowed=True, metadata={'llm_telemetry_id': 't_main'}
            )
            # H/I: telemetry record + missing_manual_check only on llm patch.
            p_record = PatchProposal(
                patch_id='p_record', run_id='r2', plan_id='pl', step_id='s5',
                target_file='e.py', patch_type='replace_block', generator='llm_replace_block',
                apply_allowed=True, quality_score=0.6
            )
            for p in [p_append, p_low, p_high, p_no_quality, p_main_tid, p_record]:
                ps.save_patch_proposal(p)
            ps.update_patch_payload('r2', 'p_no_quality', {'quality_score': None})
            ps.update_patch_payload('r2', 'p_main_tid', {'quality_score': None})
            ps.update_patch_payload('r2', 'p_no_quality', {'approval_status': 'approved', 'applied': False})

            telemetry = [{'telemetry_id': 't1', 'run_id': 'r2', 'patch_id': 'p_record'}]
            d = ps.get_run_patch_dashboard_summary('r2', manual_checks=[], telemetry=telemetry)
            byid = {x['patch_id']: x for x in d['patches']}

            self.assertFalse(byid['p_append']['quality_evaluated'])
            self.assertFalse(byid['p_append']['is_low_quality'])
            self.assertNotIn('low_quality', byid['p_append']['attention_flags'])

            self.assertTrue(byid['p_low']['quality_evaluated'])
            self.assertTrue(byid['p_low']['is_low_quality'])
            self.assertIn('low_quality', byid['p_low']['attention_flags'])

            self.assertTrue(byid['p_high']['quality_evaluated'])
            self.assertFalse(byid['p_high']['is_low_quality'])
            self.assertNotIn('low_quality', byid['p_high']['attention_flags'])

            self.assertIn('quality_not_evaluated', byid['p_no_quality']['attention_flags'])
            self.assertEqual(d['counts']['quality_not_evaluated'], 2)  # p_no_quality + p_main_tid
            self.assertEqual(d['counts']['approved_not_applied'], 1)

            self.assertTrue(byid['p_no_quality']['has_telemetry'])
            self.assertEqual(byid['p_no_quality']['telemetry_reference_count'], 1)
            self.assertEqual(byid['p_no_quality']['telemetry_record_count'], 0)

            self.assertTrue(byid['p_main_tid']['has_telemetry'])
            self.assertEqual(byid['p_main_tid']['telemetry_reference_count'], 1)

            self.assertEqual(byid['p_record']['telemetry_record_count'], 1)
            self.assertEqual(byid['p_record']['telemetry_count'], 1)
            self.assertIn('missing_manual_check', byid['p_low']['attention_flags'])
            self.assertNotIn('missing_manual_check', byid['p_append']['attention_flags'])
            self.assertEqual(d['counts']['low_quality'], 1)


if __name__ == '__main__':
    unittest.main()
