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


class Phase6ImplementationExecutorTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.project = self.root / "project"
        self.project.mkdir(parents=True, exist_ok=True)
        self.storage = PlanStorage(self.root / "ca_data")
        self.approval_manager = PlanApprovalManager(self.storage)
        self.run_storage = RunStorage(self.root / "ca_data")
        self.executor = ImplementationExecutor(self.storage, self.run_storage)

    def tearDown(self):
        self.td.cleanup()

    def _save_plan(self, status="planned", steps=None, destructive=False):
        plan = Plan(
            plan_id="plan6",
            requirement_id="req6",
            status=status,
            user_goal="goal",
            requirement_summary="summary",
            destructive_change_detected=destructive,
            implementation_steps=steps
            or [ImplementationStep(step_id="s1", title="inspect", action_type="inspect", target_files=["a.txt"])],
        )
        review = PlanReviewResult(
            review_id="r6",
            plan_id="plan6",
            requirement_id="req6",
            overall_risk="low",
            recommended_next_action="proceed",
        )
        self.storage.save_plan(plan, user_input="in", interpreted_goal="goal", review_result=review)

    def _approve(self):
        self.approval_manager.decide(plan_id="plan6", decision="approve")

    def test_non_execution_ready_rejected(self):
        self._save_plan(status="planned")
        with self.assertRaises(ValueError):
            self.executor.execute("plan6", project_path=str(self.project))

    def test_no_approval_rejected(self):
        self._save_plan()
        with self.assertRaises(ValueError):
            self.executor.execute("plan6", project_path=str(self.project))

    def test_dry_run_no_file_changes(self):
        steps = [ImplementationStep(step_id="s1", title="create", action_type="create", target_files=["new.py"])]
        self._save_plan(steps=steps)
        self._approve()
        out = self.executor.execute("plan6", execution_mode="dry_run", project_path=str(self.project), allow_create=True)
        self.assertIn(out["status"], {"completed", "completed_with_skips"})
        self.assertFalse((self.project / "new.py").exists())

    def test_delete_blocked(self):
        self._save_plan(steps=[ImplementationStep(step_id="s1", title="del", action_type="delete", risk_level="low")])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project))
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")
        self.assertTrue(out["run"]["no_destructive_actions"])

    def test_run_command_blocked(self):
        self._save_plan(steps=[ImplementationStep(step_id="s1", title="cmd", action_type="run_command")])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project))
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")

    def test_high_risk_blocked(self):
        self._save_plan(steps=[ImplementationStep(step_id="s1", title="high", action_type="inspect", risk_level="high")])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project))
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")

    def test_safe_apply_create(self):
        self._save_plan(steps=[ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["new.txt"])])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project), allow_create=True)
        self.assertTrue((self.project / "new.txt").exists())
        self.assertTrue(out["run"]["step_results"][0]["changed_files"])

    def test_safe_apply_create_existing_blocked(self):
        (self.project / "new.txt").write_text("x", encoding="utf-8")
        self._save_plan(steps=[ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["new.txt"])])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project), allow_create=True)
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")

    def test_safe_apply_update_default_false_blocked(self):
        (self.project / "a.txt").write_text("abc", encoding="utf-8")
        self._save_plan(steps=[ImplementationStep(step_id="s1", title="upd", action_type="update", target_files=["a.txt"])])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project))
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")

    def test_project_path_outside_blocked(self):
        self._save_plan(steps=[ImplementationStep(step_id="s1", title="create", action_type="create", target_files=["../outside.txt"])])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project), allow_create=True)
        self.assertIn(out["run"]["step_results"][0]["status"], {"blocked", "failed"})

    def test_run_storage_files_exist(self):
        self._save_plan()
        self._approve()
        out = self.executor.execute("plan6", execution_mode="dry_run", project_path=str(self.project))
        run_id = out["run_id"]
        rd = self.root / "ca_data" / "runs" / run_id
        self.assertTrue((rd / "run.json").exists())
        self.assertTrue((rd / "steps.json").exists())
        self.assertTrue((rd / "execution.log").exists())
        self.assertTrue((rd / "final_report.md").exists())

    def test_response_shape(self):
        self._save_plan()
        self._approve()
        out = self.executor.execute("plan6", execution_mode="dry_run", project_path=str(self.project))
        self.assertIn("run_id", out)
        self.assertIn("status", out)
        self.assertIn("message", out)


if __name__ == "__main__":
    unittest.main()
