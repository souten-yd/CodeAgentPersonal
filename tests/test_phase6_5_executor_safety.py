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
from agent.requirement_schema import RequirementDefinition
from agent.run_storage import RunStorage


class Phase65ExecutorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.project = self.root / "project"
        self.project.mkdir(parents=True, exist_ok=True)
        self.storage = PlanStorage(self.root / "ca_data")
        self.approval_manager = PlanApprovalManager(self.storage)
        self.run_storage = RunStorage(self.root / "ca_data")
        self.executor = ImplementationExecutor(self.storage, self.run_storage)
        req = RequirementDefinition(requirement_id="req6", source_task_id="task1", user_input="u")
        self.storage.save_requirement(req)

    def tearDown(self):
        self.td.cleanup()

    def _save_plan(self, steps=None):
        plan = Plan(
            plan_id="plan6",
            requirement_id="req6",
            status="planned",
            user_goal="goal",
            requirement_summary="summary",
            implementation_steps=steps or [ImplementationStep(step_id="s1", title="inspect", action_type="inspect", target_files=["a.txt"])],
        )
        review = PlanReviewResult(review_id="r6", plan_id="plan6", requirement_id="req6", overall_risk="low", recommended_next_action="proceed")
        self.storage.save_plan(plan, user_input="in", interpreted_goal="goal", review_result=review)

    def _approve(self):
        self.approval_manager.decide(plan_id="plan6", decision="approve")

    def _inject_plan_fields(self, **fields):
        p = self.storage.plan_json_path("plan6")
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload.update(fields)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_safe_apply_with_empty_project_path_uses_plan_fallback(self):
        self._save_plan([ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["new.txt"])])
        self._approve()
        self._inject_plan_fields(resolved_project_path=str(self.project))
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path="", allow_create=True)
        self.assertEqual(out["run"]["step_results"][0]["status"], "completed")


    def test_safe_apply_with_dot_project_path_uses_plan_fallback(self):
        self._save_plan([ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["new.txt"])])
        self._approve()
        self._inject_plan_fields(resolved_project_path=str(self.project))
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=".", allow_create=True)
        self.assertEqual(out["run"]["step_results"][0]["status"], "completed")

    def test_safe_apply_with_blank_project_path_fails(self):
        self._save_plan([ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["new.txt"])])
        self._approve()
        with self.assertRaises(ValueError):
            self.executor.execute("plan6", execution_mode="safe_apply", project_path="   ", allow_create=True)
    def test_dry_run_with_empty_project_path_succeeds_with_warning(self):
        self._save_plan([ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["new.txt"])])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="dry_run", project_path="", allow_create=True)
        self.assertIn("project_path was not resolved; dry_run only", out["run"]["warnings"])
        self.assertFalse((self.project / "new.txt").exists())

    def test_safe_apply_with_dot_project_path_without_fallback_fails(self):
        self._save_plan([ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["from_plan.txt"])])
        self._approve()
        with self.assertRaises(ValueError):
            self.executor.execute("plan6", execution_mode="safe_apply", project_path=".", allow_create=True)

    def test_safe_apply_with_empty_request_rejected_if_plan_path_is_cwd(self):
        self._save_plan([ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["from_plan.txt"])])
        self._approve()
        self._inject_plan_fields(resolved_project_path=str(Path.cwd()))
        with self.assertRaises(ValueError):
            self.executor.execute("plan6", execution_mode="safe_apply", project_path="", allow_create=True)

    def test_safe_apply_with_empty_request_rejected_if_requirement_is_app(self):
        self._save_plan([ImplementationStep(step_id="s1", title="作成", action_type="create", target_files=["from_requirement.txt"])])
        req = RequirementDefinition(
            requirement_id="req6",
            source_task_id="task1",
            user_input="u",
            resolved_project_path="/app",
        )
        self.storage.save_requirement(req)
        self._approve()
        with self.assertRaises(ValueError):
            self.executor.execute("plan6", execution_mode="safe_apply", project_path="", allow_create=True)

    def test_existing_create_target_blocked_counted(self):
        (self.project / "exists.txt").write_text("x", encoding="utf-8")
        self._save_plan([ImplementationStep(step_id="s1", title="create", action_type="create", target_files=["exists.txt"])])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project), allow_create=True)
        step = out["run"]["step_results"][0]
        self.assertEqual(step["status"], "blocked")
        self.assertEqual(out["run"]["blocked_steps"], 1)
        self.assertEqual(out["run"]["completed_steps"], 0)

    def test_ca_data_create_blocked(self):
        self._save_plan([ImplementationStep(step_id="s1", title="create", action_type="create", target_files=["ca_data/test.txt"])])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.root), allow_create=True)
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")
        self.assertFalse((self.root / "ca_data" / "test.txt").exists())

    def test_ca_data_update_blocked(self):
        target = self.root / "ca_data" / "test.txt"
        target.write_text("hello", encoding="utf-8")
        self._save_plan([ImplementationStep(step_id="s1", title="update", action_type="update", target_files=["ca_data/test.txt"])])
        before = target.read_text(encoding="utf-8")
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.root), allow_update=True)
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")
        self.assertEqual(before, target.read_text(encoding="utf-8"))

    def test_allow_delete_true_still_blocks_delete(self):
        self._save_plan([ImplementationStep(step_id="s1", title="del", action_type="delete")])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project), allow_delete=True)
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")

    def test_allow_run_command_true_still_blocks_run_command(self):
        self._save_plan([ImplementationStep(step_id="s1", title="cmd", action_type="run_command")])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project), allow_run_command=True)
        self.assertEqual(out["run"]["step_results"][0]["status"], "blocked")

    def test_run_counts_consistent(self):
        (self.project / "exists.txt").write_text("x", encoding="utf-8")
        (self.project / "u.txt").write_text("u", encoding="utf-8")
        steps = [
            ImplementationStep(step_id="s1", title="ok create", action_type="create", target_files=["new_ok.txt"]),
            ImplementationStep(step_id="s2", title="blocked create", action_type="create", target_files=["exists.txt"]),
            ImplementationStep(step_id="s3", title="ok update", action_type="update", target_files=["u.txt"]),
            ImplementationStep(step_id="s4", title="blocked delete", action_type="delete"),
        ]
        self._save_plan(steps)
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project), allow_create=True, allow_update=True)
        run = out["run"]
        self.assertEqual(run["total_steps"], len(steps))
        self.assertEqual(run["completed_steps"] + run["skipped_steps"] + run["blocked_steps"] + run["failed_steps"], run["total_steps"])

    def test_japanese_text_not_broken(self):
        self._save_plan([ImplementationStep(step_id="s1", title="日本語タイトル", description="説明です", action_type="inspect", target_files=["none.txt"])])
        self._approve()
        out = self.executor.execute("plan6", execution_mode="safe_apply", project_path=str(self.project))
        self.assertEqual(out["run"]["step_results"][0]["title"], "日本語タイトル")


if __name__ == "__main__":
    unittest.main()
