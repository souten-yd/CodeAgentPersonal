from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import json

from agent.implementation_executor import ImplementationExecutor
from agent.plan_approval_manager import PlanApprovalManager
from agent.plan_review_schema import PlanReviewResult
from agent.plan_schema import ImplementationStep, Plan
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage


class Phase7PatchGenerationTests(unittest.TestCase):
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

    def _save_plan(self, steps):
        plan = Plan(plan_id="plan7", requirement_id="req7", status="planned", user_goal="goal", requirement_summary="sum", implementation_steps=steps)
        review = PlanReviewResult(review_id="r7", plan_id="plan7", requirement_id="req7", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="u", interpreted_goal="g", review_result=review)
        self.approval_manager.decide(plan_id="plan7", decision="approve")

    def test_preview_only_generates_patch_without_file_change(self):
        target = self.project / "a.py"; target.write_text("print('x')\n", encoding="utf-8")
        self._save_plan([ImplementationStep(step_id="s1", title="日本語", description="説明", action_type="update", risk_level="low", target_files=["a.py"])])
        before = target.read_text(encoding="utf-8")
        out = self.executor.execute("plan7", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, apply_patches=False, preview_only=True)
        self.assertEqual(before, target.read_text(encoding="utf-8"))
        step = out["run"]["step_results"][0]
        self.assertTrue(step["patch_id"])

    def test_apply_patches_true_updates_when_allow_update_true(self):
        target = self.project / "b.py"; target.write_text("x=1\n", encoding="utf-8")
        self._save_plan([ImplementationStep(step_id="s1", title="upd", action_type="update", risk_level="low", target_files=["b.py"])])
        out = self.executor.execute("plan7", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, apply_patches=True, preview_only=False)
        self.assertIn("CodeAgent Phase 7 patch note", target.read_text(encoding="utf-8"))
        self.assertTrue(out["run"]["step_results"][0]["verification_id"])

    def test_json_update_is_rejected(self):
        target = self.project / "a.json"; target.write_text("{\"a\":1}\n", encoding="utf-8")
        self._save_plan([ImplementationStep(step_id="s1", title="upd", action_type="update", risk_level="low", target_files=["a.json"])])
        out = self.executor.execute("plan7", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, apply_patches=True, preview_only=False)
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")

    def test_html_and_js_use_expected_comment_styles(self):
        html = self.project / "a.html"; html.write_text("<h1>x</h1>\n", encoding="utf-8")
        js = self.project / "a.js"; js.write_text("const x = 1;\n", encoding="utf-8")
        self._save_plan([
            ImplementationStep(step_id="s1", title="upd html", action_type="update", risk_level="low", target_files=["a.html"]),
            ImplementationStep(step_id="s2", title="upd js", action_type="update", risk_level="low", target_files=["a.js"]),
        ])
        out = self.executor.execute("plan7", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, apply_patches=True, preview_only=False)
        self.assertEqual(out["run"]["step_results"][0]["status"], "completed")
        self.assertIn("<!-- CodeAgent Phase 7 patch note", html.read_text(encoding="utf-8"))
        self.assertIn("/* CodeAgent Phase 7 patch note", js.read_text(encoding="utf-8"))

    def test_preview_only_has_no_verification_id_and_apply_has_it(self):
        target = self.project / "c.py"; target.write_text("x=1\n", encoding="utf-8")
        self._save_plan([ImplementationStep(step_id="s1", title="upd", action_type="update", risk_level="low", target_files=["c.py"])])
        out1 = self.executor.execute("plan7", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, apply_patches=False, preview_only=True)
        self.assertFalse(out1["run"]["step_results"][0]["verification_id"])
        out2 = self.executor.execute("plan7", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, apply_patches=True, preview_only=False)
        self.assertTrue(out2["run"]["step_results"][0]["verification_id"])

    def test_patch_and_verification_files_saved_utf8(self):
        target = self.project / "d.py"; target.write_text("x=1\n", encoding="utf-8")
        self._save_plan([ImplementationStep(step_id="s1", title="日本語タイトル", description="説明", action_type="update", risk_level="low", target_files=["d.py"])])
        out = self.executor.execute("plan7", execution_mode="safe_apply", project_path=str(self.project), allow_update=True, apply_patches=True, preview_only=False)
        step = out["run"]["step_results"][0]
        patch_json = self.root / "ca_data" / "runs" / out["run_id"] / "patches" / f"{step['patch_id']}.patch.json"
        payload = json.loads(patch_json.read_text(encoding="utf-8"))
        self.assertIn("日本語タイトル", payload["proposed_content"])
