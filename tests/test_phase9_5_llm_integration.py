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


class Phase95LLMIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "a.py").write_text("x=1\n", encoding="utf-8")
        self.storage = PlanStorage(self.root / "ca_data")
        self.run_storage = RunStorage(self.root / "ca_data")

    def tearDown(self):
        self.td.cleanup()

    def _approve_plan(self, plan_id="p1"):
        plan = Plan(plan_id=plan_id, requirement_id="r1", status="planned", user_goal="g", requirement_summary="s", implementation_steps=[ImplementationStep(step_id="s1", title="u", action_type="update", risk_level="low", target_files=["a.py"])])
        review = PlanReviewResult(review_id="rv", plan_id=plan_id, requirement_id="r1", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="u", interpreted_goal="g", review_result=review)
        PlanApprovalManager(self.storage).decide(plan_id, "approve")

    def test_llm_replace_block_calls_injected_fn(self):
        self._approve_plan("p2")
        called = {"n": 0}
        def fake_llm(**kwargs):
            called["n"] += 1
            return '{"original_block":"x=1","replacement_block":"x=2"}'
        ex = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=fake_llm)
        run = ex.execute("p2", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="llm_replace_block")
        self.assertEqual(called["n"], 1)
        patches = ex.patch_storage.list_patches(run["run_id"])
        self.assertEqual(patches[0]["patch_type"], "replace_block")
        self.assertTrue(patches[0]["apply_allowed"])

    def test_auto_fallback_when_invalid_llm(self):
        self._approve_plan("p3")
        def fake_llm(**kwargs):
            return '{}'
        ex = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=fake_llm)
        run = ex.execute("p3", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="auto")
        p = ex.patch_storage.list_patches(run["run_id"])[0]
        self.assertEqual(p["patch_type"], "append")
        self.assertEqual((p.get("metadata") or {}).get("fallback_from"), "llm_replace_block")

    def test_llm_exception_does_not_fail_run(self):
        self._approve_plan("p4")
        def fake_llm(**kwargs):
            raise RuntimeError("boom")
        ex = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=fake_llm)
        run = ex.execute("p4", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="llm_replace_block")
        self.assertIn(run["status"], {"completed", "completed_with_skips"})
        p = ex.patch_storage.list_patches(run["run_id"])[0]
        self.assertFalse(p["apply_allowed"])

if __name__ == '__main__':
    unittest.main()
