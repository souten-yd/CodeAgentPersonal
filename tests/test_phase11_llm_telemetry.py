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


class Phase11LLMTelemetryTests(unittest.TestCase):
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

    def _approve_plan(self, plan_id: str):
        plan = Plan(plan_id=plan_id, requirement_id="r1", status="planned", user_goal="g", requirement_summary="s", implementation_steps=[ImplementationStep(step_id="s1", title="u", action_type="update", risk_level="low", target_files=["a.py"])])
        review = PlanReviewResult(review_id="rv", plan_id=plan_id, requirement_id="r1", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="u", interpreted_goal="g", review_result=review)
        PlanApprovalManager(self.storage).decide(plan_id, "approve")

    def test_llm_replace_block_generation_saves_telemetry(self):
        self._approve_plan("p1")

        def fake_llm(**kwargs):
            return '{"candidate_id":"cand_1","original_block":"x=1","replacement_block":"x=2"}'

        ex = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=fake_llm)
        run = ex.execute("p1", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="llm_replace_block")
        patch = ex.patch_storage.list_patches(run["run_id"])[0]
        tlist = ex.llm_telemetry_storage.list_telemetry(run["run_id"])
        self.assertGreaterEqual(len(tlist), 1)
        tid = (patch.get("metadata") or {}).get("llm_telemetry_id", "")
        self.assertTrue(tid)
        telemetry = ex.llm_telemetry_storage.load_telemetry(run["run_id"], tid)
        self.assertEqual(telemetry["patch_id"], patch["patch_id"])
        self.assertGreater(telemetry["prompt_chars"], 0)
        self.assertGreater(telemetry["response_chars"], 0)
        self.assertEqual(telemetry["apply_allowed_after_validation"], patch["apply_allowed"])

    def test_auto_fallback_stores_fallback_telemetry_id(self):
        self._approve_plan("p2")

        def fake_llm(**kwargs):
            return "{}"

        ex = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=fake_llm)
        run = ex.execute("p2", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="auto")
        patch = ex.patch_storage.list_patches(run["run_id"])[0]
        self.assertEqual(patch["patch_type"], "append")
        md = patch.get("metadata") or {}
        self.assertEqual(md.get("fallback_from"), "llm_replace_block")
        fallback_tid = md.get("fallback_telemetry_id", "")
        self.assertTrue(fallback_tid)
        telemetry = ex.llm_telemetry_storage.load_telemetry(run["run_id"], fallback_tid)
        self.assertEqual(telemetry["run_id"], run["run_id"])

    def test_llm_invalid_output_success_semantics(self):
        self._approve_plan("p3")

        def fake_llm(**kwargs):
            return "not json"

        ex = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=fake_llm)
        run = ex.execute("p3", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="llm_replace_block")
        patch = ex.patch_storage.list_patches(run["run_id"])[0]
        tid = (patch.get("metadata") or {}).get("llm_telemetry_id", "")
        telemetry = ex.llm_telemetry_storage.load_telemetry(run["run_id"], tid)
        self.assertTrue(telemetry["success"])
        self.assertFalse(telemetry["apply_allowed_after_validation"])
        self.assertTrue((telemetry.get("metadata") or {}).get("rejected_by_validation"))

    def test_llm_unavailable_or_error_success_false(self):
        self._approve_plan("p4")
        ex1 = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=None)
        run1 = ex1.execute("p4", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="llm_replace_block")
        patch1 = ex1.patch_storage.list_patches(run1["run_id"])[0]
        tid1 = (patch1.get("metadata") or {}).get("llm_telemetry_id", "")
        t1 = ex1.llm_telemetry_storage.load_telemetry(run1["run_id"], tid1)
        self.assertFalse(t1["success"])
        self.assertFalse(t1["apply_allowed_after_validation"])

        self._approve_plan("p5")

        def raise_llm(**kwargs):
            raise RuntimeError("boom")

        ex2 = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=raise_llm)
        run2 = ex2.execute("p5", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="llm_replace_block")
        patch2 = ex2.patch_storage.list_patches(run2["run_id"])[0]
        tid2 = (patch2.get("metadata") or {}).get("llm_telemetry_id", "")
        t2 = ex2.llm_telemetry_storage.load_telemetry(run2["run_id"], tid2)
        self.assertFalse(t2["success"])
        self.assertFalse(t2["apply_allowed_after_validation"])

    def test_duration_ms_is_int_non_negative(self):
        self._approve_plan("p6")

        def fake_llm(**kwargs):
            return "{}"

        ex = ImplementationExecutor(self.storage, self.run_storage, llm_patch_fn=fake_llm)
        run = ex.execute("p6", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, preview_only=True, patch_generation_mode="llm_replace_block")
        patch = ex.patch_storage.list_patches(run["run_id"])[0]
        tid = (patch.get("metadata") or {}).get("llm_telemetry_id", "")
        telemetry = ex.llm_telemetry_storage.load_telemetry(run["run_id"], tid)
        self.assertIsInstance(telemetry["duration_ms"], int)
        self.assertGreaterEqual(telemetry["duration_ms"], 0)


if __name__ == '__main__':
    unittest.main()
