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

    def _setup_run(self, plan_id: str, target_rel: str = "a.py"):
        t = self.project / target_rel
        plan = Plan(plan_id=plan_id, requirement_id=f"r_{plan_id}", status="planned", user_goal="g", requirement_summary="s", implementation_steps=[ImplementationStep(step_id="s1", title="u", action_type="update", risk_level="low", target_files=[target_rel])])
        review = PlanReviewResult(review_id=f"rv_{plan_id}", plan_id=plan_id, requirement_id=f"r_{plan_id}", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="u", interpreted_goal="g", review_result=review)
        PlanApprovalManager(self.storage).decide(plan_id, "approve")
        run = self.executor.execute(plan_id, execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True)
        return run["run_id"], t

    def test_replace_block_apply_requires_approval(self):
        t = self.project / "a.py"; t.write_text("header\nx=1\nfooter\n", encoding="utf-8")
        run_id, _ = self._setup_run("p0")
        p = PatchProposal(patch_id="patch1", run_id=run_id, plan_id="p0", step_id="s1", target_file=str(t), patch_type="replace_block", original_block="x=1", replacement_block="x=2", match_count=1, apply_allowed=True, unified_diff="--- a\n+++ a\n@@\n-x=1\n+x=2")
        self.executor.patch_storage.save_patch_proposal(p)
        with self.assertRaises(ValueError):
            self.executor.apply_patch(run_id, "patch1")

    def test_replace_block_no_match_does_not_create_backup(self):
        run_id, t = self._setup_run("p_no_match")
        t.write_text("header\nx=1\nfooter\n", encoding="utf-8")
        patch = PatchProposal(patch_id="rb_no_match", run_id=run_id, plan_id="p_no_match", step_id="s1", target_file=str(t), patch_type="replace_block", original_block="x=1", replacement_block="x=2", match_count=1, apply_allowed=True, unified_diff="--- a\n+++ a\n@@\n-x=1\n+x=2")
        self.executor.patch_storage.save_patch_proposal(patch)
        PatchApprovalManager(self.executor.patch_storage).decide(run_id, "rb_no_match", "approve")

        t.write_text("header\ny=1\nfooter\n", encoding="utf-8")
        before = t.read_text(encoding="utf-8")
        backup = t.with_suffix(t.suffix + ".bak.phase8")
        if backup.exists():
            backup.unlink()

        with self.assertRaises(ValueError):
            self.executor.apply_patch(run_id, "rb_no_match")
        self.assertEqual(t.read_text(encoding="utf-8"), before)
        self.assertFalse(backup.exists())
        saved = self.executor.patch_storage.load_patch(run_id, "rb_no_match")
        self.assertFalse(saved.get("apply_allowed", True))
        self.assertIn("replace_block original_block no longer exists", saved.get("safety_warnings", []))

    def test_replace_block_multiple_match_does_not_create_backup(self):
        run_id, t = self._setup_run("p_multi")
        t.write_text("header\nx=1\nfooter\n", encoding="utf-8")
        patch = PatchProposal(patch_id="rb_multi", run_id=run_id, plan_id="p_multi", step_id="s1", target_file=str(t), patch_type="replace_block", original_block="x=1", replacement_block="x=2", match_count=1, apply_allowed=True, unified_diff="--- a\n+++ a\n@@\n-x=1\n+x=2")
        self.executor.patch_storage.save_patch_proposal(patch)
        PatchApprovalManager(self.executor.patch_storage).decide(run_id, "rb_multi", "approve")

        t.write_text("header\nx=1\nx=1\nfooter\n", encoding="utf-8")
        before = t.read_text(encoding="utf-8")
        backup = t.with_suffix(t.suffix + ".bak.phase8")
        if backup.exists():
            backup.unlink()

        with self.assertRaises(ValueError):
            self.executor.apply_patch(run_id, "rb_multi")
        self.assertEqual(t.read_text(encoding="utf-8"), before)
        self.assertFalse(backup.exists())
        saved = self.executor.patch_storage.load_patch(run_id, "rb_multi")
        self.assertFalse(saved.get("apply_allowed", True))
        self.assertIn("replace_block original_block is ambiguous", saved.get("safety_warnings", []))

    def test_successful_replace_block_creates_backup_and_verification_metadata(self):
        run_id, t = self._setup_run("p_success")
        t.write_text("header\nx=1\nfooter\n", encoding="utf-8")
        patch = PatchProposal(patch_id="rb_ok", run_id=run_id, plan_id="p_success", step_id="s1", target_file=str(t), patch_type="replace_block", original_block="x=1", replacement_block="x=2", match_count=1, apply_allowed=True, unified_diff="--- a\n+++ a\n@@\n-x=1\n+x=2")
        self.executor.patch_storage.save_patch_proposal(patch)
        PatchApprovalManager(self.executor.patch_storage).decide(run_id, "rb_ok", "approve")

        backup = t.with_suffix(t.suffix + ".bak.phase8")
        if backup.exists():
            backup.unlink()

        res = self.executor.apply_patch(run_id, "rb_ok")
        self.assertTrue(res["applied"])
        self.assertTrue(backup.exists())
        self.assertIn("x=2", t.read_text(encoding="utf-8"))
        self.assertIn(res["apply_result"].get("verification_status", ""), {"passed", "failed"})
        self.assertTrue(res["apply_result"].get("verification_summary", "") != "")

        approvals = self.executor.patch_storage.list_patch_approvals(run_id)
        applied = [a for a in approvals if a.get("patch_id") == "rb_ok"][-1]
        meta = applied.get("metadata") or {}
        self.assertIn(meta.get("verification_status", ""), {"passed", "failed"})
        self.assertTrue(meta.get("verification_summary", "") != "")

    def test_append_flow_still_creates_backup_and_works(self):
        run_id, t = self._setup_run("p_append")
        t.write_text("header\n", encoding="utf-8")
        append = "\n# CodeAgent Phase 7 patch note\nprint('ok')\n"
        patch = PatchProposal(patch_id="ap1", run_id=run_id, plan_id="p_append", step_id="s1", target_file=str(t), patch_type="append", proposed_content=append, apply_allowed=True, unified_diff="--- a\n+++ a")
        self.executor.patch_storage.save_patch_proposal(patch)
        PatchApprovalManager(self.executor.patch_storage).decide(run_id, "ap1", "approve")

        backup = t.with_suffix(t.suffix + ".bak.phase8")
        if backup.exists():
            backup.unlink()

        res = self.executor.apply_patch(run_id, "ap1")
        self.assertTrue(res["applied"])
        self.assertTrue(backup.exists())
        body = t.read_text(encoding="utf-8")
        self.assertIn("CodeAgent Phase 7 patch note", body)
        self.assertIn("print('ok')", body)


if __name__ == '__main__':
    unittest.main()
