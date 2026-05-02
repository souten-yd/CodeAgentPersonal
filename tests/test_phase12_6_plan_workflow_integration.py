from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.implementation_executor import ImplementationExecutor
from agent.plan_approval_manager import PlanApprovalManager
from agent.plan_review_schema import PlanReviewResult
from agent.plan_schema import ImplementationStep, Plan
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage


class Phase12_6PlanWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.project = self.root / 'project'
        self.project.mkdir(parents=True, exist_ok=True)
        (self.project / 'a.py').write_text('x=1\n', encoding='utf-8')
        self.storage = PlanStorage(self.root / 'ca_data')
        self.approval_manager = PlanApprovalManager(self.storage)
        self.run_storage = RunStorage(self.root / 'ca_data')
        self.executor = ImplementationExecutor(self.storage, self.run_storage)

    def tearDown(self):
        self.td.cleanup()

    def _save_plan(self, plan_id='plan126', risk='low', destructive=False):
        plan = Plan(
            plan_id=plan_id,
            requirement_id='req126',
            status='planned',
            user_goal='goal',
            requirement_summary='summary',
            destructive_change_detected=destructive,
            implementation_steps=[ImplementationStep(step_id='s1', title='upd', action_type='update', target_files=['a.py'])],
        )
        review = PlanReviewResult(
            review_id='rev126',
            plan_id=plan_id,
            requirement_id='req126',
            overall_risk=risk,
            recommended_next_action='proceed',
            destructive_change_detected=destructive,
            requires_user_confirmation=destructive,
        )
        self.storage.save_plan(plan, user_input='u', interpreted_goal='g', review_result=review)

    def test_execute_requires_approval(self):
        self._save_plan()
        with self.assertRaises(ValueError):
            self.executor.execute('plan126', execution_mode='safe_apply', project_path=str(self.project), allow_update=True)

    def test_high_risk_approve_requires_ack(self):
        self._save_plan(risk='high')
        with self.assertRaises(ValueError):
            self.approval_manager.decide(plan_id='plan126', decision='approve')

    def test_destructive_approve_requires_ack(self):
        self._save_plan(destructive=True)
        with self.assertRaises(ValueError):
            self.approval_manager.decide(plan_id='plan126', decision='approve', risk_acknowledged=True)

    def test_execute_preview_generates_run_and_patch(self):
        self._save_plan()
        res = self.approval_manager.decide(plan_id='plan126', decision='approve')
        self.assertTrue(res['approval']['execution_ready'])
        out = self.executor.execute(
            'plan126',
            execution_mode='safe_apply',
            project_path=str(self.project),
            allow_update=True,
            apply_patches=True,
            preview_only=True,
            patch_generation_mode='auto',
        )
        self.assertTrue(out['run_id'])
        patches = self.executor.patch_storage.list_patches(out['run_id'])
        self.assertGreaterEqual(len(patches), 1)


if __name__ == '__main__':
    unittest.main()
