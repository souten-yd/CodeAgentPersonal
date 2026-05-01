from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.implementation_executor import ImplementationExecutor
from agent.patch_approval_manager import PatchApprovalManager
from agent.plan_approval_manager import PlanApprovalManager
from agent.plan_review_schema import PlanReviewResult
from agent.plan_schema import ImplementationStep, Plan
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage


class Phase8PatchApplyApiTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.storage = PlanStorage(self.root / "ca_data")
        self.approval_manager = PlanApprovalManager(self.storage)
        self.run_storage = RunStorage(self.root / "ca_data")
        self.executor = ImplementationExecutor(self.storage, self.run_storage)

    def tearDown(self):
        self.td.cleanup()

    def _run_with_patch(self, fn="a.py"):
        target = self.project / fn
        target.write_text("x=1\n", encoding="utf-8")
        plan = Plan(plan_id="plan8", requirement_id="req8", status="planned", user_goal="g", requirement_summary="s", implementation_steps=[ImplementationStep(step_id="s1", title="u", action_type="update", risk_level="low", target_files=[fn])])
        review = PlanReviewResult(review_id="r8", plan_id="plan8", requirement_id="req8", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="u", interpreted_goal="g", review_result=review)
        self.approval_manager.decide(plan_id="plan8", decision="approve")
        out = self.executor.execute("plan8", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, apply_patches=False, preview_only=True)
        step = out["run"]["step_results"][0]
        return out["run_id"], step["patch_id"], target

    def test_unapproved_cannot_apply(self):
        run_id, patch_id, _ = self._run_with_patch()
        with self.assertRaises(ValueError):
            self.executor.apply_patch(run_id, patch_id)

    def test_approved_can_apply_and_backup_created(self):
        run_id, patch_id, target = self._run_with_patch()
        pm = PatchApprovalManager(self.executor.patch_storage)
        pm.decide(run_id, patch_id, "approve")
        res = self.executor.apply_patch(run_id, patch_id)
        self.assertTrue(res["applied"])
        self.assertTrue(Path(res["apply_result"]["backup_path"]).exists())
        self.assertIn("CodeAgent Phase 7 patch note", target.read_text(encoding="utf-8"))
        self.assertEqual(res["approval"]["status"], "applied")

    def test_duplicate_apply_rejected(self):
        run_id, patch_id, _ = self._run_with_patch()
        pm = PatchApprovalManager(self.executor.patch_storage)
        pm.decide(run_id, patch_id, "approve")
        self.executor.apply_patch(run_id, patch_id)
        with self.assertRaises(ValueError):
            self.executor.apply_patch(run_id, patch_id)

    def test_patch_list_includes_approval_fields(self):
        run_id, patch_id, _ = self._run_with_patch()
        pm = PatchApprovalManager(self.executor.patch_storage)
        pm.decide(run_id, patch_id, "approve", user_comment="日本語コメント")
        patches = self.executor.patch_storage.list_patches(run_id)
        self.assertIn("approval_status", patches[0])
        self.assertIn("unified_diff", patches[0])
        self.assertIn("safety_warnings", patches[0])

if __name__ == "__main__":
    unittest.main()
