import tempfile
import unittest
from pathlib import Path

from agent.implementation_executor import ImplementationExecutor
from agent.patch_schema import PatchProposal
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage


class ReproposalPreviewTests(unittest.TestCase):
    def _save_run(self, run_storage: RunStorage, run_id: str, project_path: Path):
        run_storage.save_run(
            type(
                'R',
                (),
                {'run_id': run_id, 'model_dump': lambda self: {'run_id': run_id, 'project_path': str(project_path)}},
            )()
        )

    def test_reproposal_requires_failed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ps = PlanStorage(root / 'ca')
            rs = RunStorage(root / 'ca')
            ex = ImplementationExecutor(ps, rs, llm_patch_fn=lambda **k: '{"original_block":"x=1","replacement_block":"x=2","candidate_id":"cand_1"}')
            run_id = 'run_x'
            (root / 'proj').mkdir()
            tf = root / 'proj' / 'a.py'
            tf.write_text('x=1\n', encoding='utf-8')
            self._save_run(rs, run_id, root / 'proj')
            p = PatchProposal(patch_id='p1', run_id=run_id, plan_id='pl', step_id='s1', target_file=str(tf), patch_type='replace_block', verification_status='passed')
            ex.patch_storage.save_patch_proposal(p)
            with self.assertRaises(ValueError):
                ex.generate_reproposal(run_id, 'p1')

    def test_reproposal_allowed_if_verification_failed_and_stays_pending(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ps, rs = PlanStorage(root / 'ca'), RunStorage(root / 'ca')
            ex = ImplementationExecutor(ps, rs, llm_patch_fn=lambda **k: '{"candidate_id":"cand_1","original_block":"x=1","replacement_block":"x=2"}')
            run_id = 'run_ok'
            proj = root / 'proj'; proj.mkdir()
            tf = proj / 'a.py'; tf.write_text('x=1\n', encoding='utf-8')
            self._save_run(rs, run_id, proj)

            original = PatchProposal(
                patch_id='p_orig', run_id=run_id, plan_id='pl', step_id='s1', target_file=str(tf),
                patch_type='replace_block', verification_status='failed', verification_summary='failed', metadata={},
            )
            original.metadata = {'verification_id': 'v_old'}
            original_dict = original.model_dump(); original_dict['verification_id'] = 'v_old'
            ex.patch_storage.save_patch_proposal(PatchProposal(**{k: v for k, v in original_dict.items() if k in PatchProposal.model_fields}))
            ex.patch_storage.update_patch_payload(run_id, 'p_orig', {'verification_id': 'v_old'})

            result = ex.generate_reproposal(run_id, 'p_orig')
            new_id = result['patch_id']
            self.assertNotEqual(new_id, 'p_orig')
            new_patch = ex.patch_storage.load_patch(run_id, new_id)
            self.assertEqual(new_patch.get('reproposal_of_patch_id'), 'p_orig')
            self.assertEqual(new_patch.get('parent_verification_id'), 'v_old')
            self.assertEqual(new_patch.get('reproposal_reason'), 'verification_failed')
            self.assertEqual(new_patch.get('status'), 'proposed')
            self.assertFalse(new_patch.get('applied', True))
            self.assertEqual(new_patch.get('generator'), 'llm_replace_block')
            self.assertEqual(new_patch.get('patch_type'), 'replace_block')
            listed = {p['patch_id']: p for p in ex.patch_storage.list_patches(run_id)}
            self.assertEqual(listed[new_id].get('approval_status'), 'pending')
            self.assertEqual(listed[new_id].get('patch_approval_id', ''), '')

    def test_reproposal_does_not_approve_or_apply(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ps, rs = PlanStorage(root / 'ca'), RunStorage(root / 'ca')
            ex = ImplementationExecutor(ps, rs, llm_patch_fn=lambda **k: '{"candidate_id":"cand_1","original_block":"x=1","replacement_block":"x=2"}')
            run_id = 'run_no_apply'; proj = root / 'proj'; proj.mkdir()
            tf = proj / 'a.py'; tf.write_text('x=1\n', encoding='utf-8')
            self._save_run(rs, run_id, proj)
            original = PatchProposal(patch_id='p1', run_id=run_id, plan_id='pl', step_id='s1', target_file=str(tf), patch_type='replace_block', verification_status='failed')
            ex.patch_storage.save_patch_proposal(original)
            before = tf.read_text(encoding='utf-8')
            res = ex.generate_reproposal(run_id, 'p1')
            self.assertEqual(tf.read_text(encoding='utf-8'), before)
            patch = ex.patch_storage.load_patch(run_id, res['patch_id'])
            self.assertFalse(patch.get('applied', True))
            self.assertEqual(ex.patch_storage.list_patch_approvals(run_id), [])

    def test_reproposal_applies_safety_checker_before_save(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ps, rs = PlanStorage(root / 'ca'), RunStorage(root / 'ca')
            ex = ImplementationExecutor(ps, rs, llm_patch_fn=lambda **k: '{"candidate_id":"cand_1","original_block":"x=1","replacement_block":"x=2"}')
            run_id = 'run_denied'; proj = root / 'proj'; proj.mkdir()
            tf = proj / 'a.json'; tf.write_text('x=1\n', encoding='utf-8')
            self._save_run(rs, run_id, proj)
            original = PatchProposal(patch_id='p_denied', run_id=run_id, plan_id='pl', step_id='s1', target_file=str(tf), patch_type='replace_block', verification_status='failed')
            ex.patch_storage.save_patch_proposal(original)
            res = ex.generate_reproposal(run_id, 'p_denied')
            patch = ex.patch_storage.load_patch(run_id, res['patch_id'])
            self.assertFalse(patch.get('apply_allowed', True))
            self.assertTrue(len(patch.get('safety_warnings', [])) >= 1)

    def test_reproposal_llm_unavailable_does_not_break_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ps, rs = PlanStorage(root / 'ca'), RunStorage(root / 'ca')
            ex = ImplementationExecutor(ps, rs, llm_patch_fn=None)
            run_id = 'run_llm_none'; proj = root / 'proj'; proj.mkdir()
            tf = proj / 'a.py'; tf.write_text('x=1\n', encoding='utf-8')
            self._save_run(rs, run_id, proj)
            original = PatchProposal(patch_id='p1', run_id=run_id, plan_id='pl', step_id='s1', target_file=str(tf), patch_type='replace_block', verification_status='failed')
            ex.patch_storage.save_patch_proposal(original)
            res = ex.generate_reproposal(run_id, 'p1')
            patch = ex.patch_storage.load_patch(run_id, res['patch_id'])
            self.assertFalse(patch.get('apply_allowed', True))
            self.assertIn(patch.get('can_apply_reason', ''), {'llm_unavailable', 'reproposal_safety_blocked', 'reproposal_safety_error'})

    def test_reproposal_telemetry_duration_and_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ps, rs = PlanStorage(root / 'ca'), RunStorage(root / 'ca')
            ex = ImplementationExecutor(ps, rs, llm_patch_fn=lambda **k: '{"candidate_id":"cand_1","original_block":"x=1","replacement_block":"x=2"}')
            run_id = 'run_telemetry'; proj = root / 'proj'; proj.mkdir()
            tf = proj / 'a.py'; tf.write_text('x=1\n', encoding='utf-8')
            self._save_run(rs, run_id, proj)
            original = PatchProposal(patch_id='p1', run_id=run_id, plan_id='pl', step_id='s1', target_file=str(tf), patch_type='replace_block', verification_status='failed')
            ex.patch_storage.save_patch_proposal(original)
            res = ex.generate_reproposal(run_id, 'p1')
            patch = ex.patch_storage.load_patch(run_id, res['patch_id'])
            tid = (patch.get('metadata') or {}).get('llm_telemetry_id', '')
            self.assertTrue(tid)
            t = ex.llm_telemetry_storage.load_telemetry(run_id, tid)
            self.assertEqual(t.get('purpose'), 'reproposal_generation')
            self.assertIsInstance(t.get('duration_ms'), int)
            self.assertGreaterEqual(int(t.get('duration_ms', -1)), 0)


if __name__ == '__main__':
    unittest.main()
