from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.implementation_executor import ImplementationExecutor
from agent.patch_approval_manager import PatchApprovalManager
from agent.patch_schema import PatchProposal
from agent.plan_approval_manager import PlanApprovalManager
from agent.plan_review_schema import PlanReviewResult
from agent.plan_schema import ImplementationStep, Plan
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage


class Phase9ReplaceBlockApplyTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.project = self.root / "project"; self.project.mkdir()
        self.storage = PlanStorage(self.root / "ca_data")
        self.run_storage = RunStorage(self.root / "ca_data")
        self.executor = ImplementationExecutor(self.storage, self.run_storage)

    def tearDown(self):
        self.td.cleanup()

    def test_replace_block_apply_requires_approval(self):
        t = self.project / "a.py"; t.write_text("header\nx=1\nfooter\n", encoding="utf-8")
        plan = Plan(plan_id="p0", requirement_id="r0", status="planned", user_goal="g", requirement_summary="s", implementation_steps=[ImplementationStep(step_id="s1", title="u", action_type="update", risk_level="low", target_files=["a.py"])])
        review = PlanReviewResult(review_id="rv0", plan_id="p0", requirement_id="r0", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="u", interpreted_goal="g", review_result=review)
        PlanApprovalManager(self.storage).decide("p0", "approve")
        run_id = self.executor.execute("p0", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True)["run_id"]
        p = PatchProposal(patch_id="patch1", run_id=run_id, plan_id="p0", step_id="s1", target_file=str(t), patch_type="replace_block", original_block="x=1", replacement_block="x=2", match_count=1, apply_allowed=True)
        self.executor.patch_storage.save_patch_proposal(p)
        with self.assertRaises(ValueError):
            self.executor.apply_patch(run_id, "patch1")

    def test_replace_block_apply_success(self):
        t = self.project / "a.py"; t.write_text("header\nx=1\nfooter\n", encoding="utf-8")
        plan = Plan(plan_id="p1", requirement_id="r1", status="planned", user_goal="g", requirement_summary="s", implementation_steps=[ImplementationStep(step_id="s1", title="u", action_type="update", risk_level="low", target_files=["a.py"])])
        review = PlanReviewResult(review_id="rv", plan_id="p1", requirement_id="r1", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="u", interpreted_goal="g", review_result=review)
        PlanApprovalManager(self.storage).decide("p1", "approve")
        run = self.executor.execute("p1", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True)
        run_id = run["run_id"]
        patch = PatchProposal(patch_id="rb1", run_id=run_id, plan_id="p1", step_id="s1", target_file=str(t), patch_type="replace_block", original_block="x=1", replacement_block="x=2", match_count=1, apply_allowed=True, unified_diff="--- a\n+++ a\n@@\n-x=1\n+x=2")
        self.executor.patch_storage.save_patch_proposal(patch)
        PatchApprovalManager(self.executor.patch_storage).decide(run_id, "rb1", "approve")
        res = self.executor.apply_patch(run_id, "rb1")
        self.assertTrue(res["applied"])
        body=t.read_text(encoding="utf-8"); self.assertIn("x=2", body); self.assertIn("header", body)


    def test_replace_block_apply_verification_status_saved(self):
        t = self.project / "a.py"; t.write_text("header\nx=1\nfooter\n", encoding="utf-8")
        plan = Plan(plan_id="p2", requirement_id="r2", status="planned", user_goal="g", requirement_summary="s", implementation_steps=[ImplementationStep(step_id="s1", title="u", action_type="update", risk_level="low", target_files=["a.py"])])
        review = PlanReviewResult(review_id="rv2", plan_id="p2", requirement_id="r2", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="u", interpreted_goal="g", review_result=review)
        PlanApprovalManager(self.storage).decide("p2", "approve")
        run = self.executor.execute("p2", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True)
        run_id = run["run_id"]
        patch = PatchProposal(patch_id="rb2", run_id=run_id, plan_id="p2", step_id="s1", target_file=str(t), patch_type="replace_block", original_block="x=1", replacement_block="x=2", match_count=1, apply_allowed=True, unified_diff="--- a\n+++ a\n@@\n-x=1\n+x=2")
        self.executor.patch_storage.save_patch_proposal(patch)
        PatchApprovalManager(self.executor.patch_storage).decide(run_id, "rb2", "approve")
        res = self.executor.apply_patch(run_id, "rb2")
        self.assertIn("verification=", res["apply_result"]["message"])
        saved = self.executor.patch_storage.load_patch(run_id, "rb2")
        self.assertIn(saved.get("verification_status", ""), {"passed", "failed"})

if __name__ == '__main__':
    unittest.main()
