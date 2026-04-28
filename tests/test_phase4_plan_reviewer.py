from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.plan_reviewer import PlanReviewer
from agent.plan_schema import ImplementationStep, Plan
from agent.requirement_schema import RequirementDefinition
from agent.task_planning_runner import TaskPlanningRunner


class Phase4PlanReviewerTests(unittest.TestCase):
    def _requirement(self, **kwargs) -> RequirementDefinition:
        data = {
            "requirement_id": "req_phase4",
            "source_task_id": "task_phase4",
            "user_input": "Plan review test",
            "interpreted_goal": "安全に計画レビューする",
            "done_definition": ["review_resultが返る"],
            "out_of_scope": ["自動コード実装"],
            "constraints": ["自動実装しない"],
        }
        data.update(kwargs)
        return RequirementDefinition(**data)

    def _plan(self, **kwargs) -> Plan:
        data = {
            "plan_id": "plan_phase4",
            "requirement_id": "req_phase4",
            "requirement_summary": "安全な計画",
            "done_definition": ["review_resultが返る"],
            "implementation_steps": [
                ImplementationStep(
                    step_id="step_1",
                    title="調査",
                    description="既存構成を確認",
                    action_type="inspect",
                    target_files=["agent/task_planning_runner.py"],
                    risk_level="low",
                    verification="確認",
                    rollback="不要",
                )
            ],
            "target_files": ["agent/task_planning_runner.py"],
            "test_plan": ["python -m unittest"],
        }
        data.update(kwargs)
        return Plan(**data)

    def test_safe_plan_low_risk(self):
        reviewer = PlanReviewer()
        result = reviewer.review(
            requirement=self._requirement(),
            plan=self._plan(),
            nexus_context={"warnings": []},
            repository_context="Top file candidates:\n- agent/task_planning_runner.py",
        )
        self.assertEqual(result.overall_risk, "low")
        self.assertFalse(result.requires_user_confirmation)
        self.assertTrue(result.approved_for_execution)

    def test_delete_step_detects_destructive_change(self):
        reviewer = PlanReviewer()
        plan = self._plan(
            implementation_steps=[
                ImplementationStep(
                    step_id="step_1",
                    title="大量削除",
                    description="delete all files",
                    action_type="delete",
                    target_files=["src/*"],
                    risk_level="high",
                    verification="-",
                    rollback="-",
                )
            ],
            target_files=["src/*"],
            test_plan=[],
        )
        result = reviewer.review(requirement=self._requirement(), plan=plan, nexus_context={}, repository_context="")
        self.assertIn(result.overall_risk, {"high", "critical"})
        self.assertTrue(result.requires_user_confirmation)
        self.assertTrue(result.destructive_change_detected)

    def test_dependency_change_detect(self):
        reviewer = PlanReviewer()
        plan = self._plan(target_files=["requirements.txt", "Dockerfile"], test_plan=["dependency test"])
        result = reviewer.review(requirement=self._requirement(), plan=plan, nexus_context={}, repository_context="")
        cats = {f.category for f in result.findings}
        self.assertTrue("dependency_change" in cats or "config_change" in cats)
        self.assertIn(result.overall_risk, {"medium", "high", "critical"})

    def test_security_change_detect(self):
        reviewer = PlanReviewer()
        plan = self._plan(
            implementation_steps=[
                ImplementationStep(
                    step_id="step_1",
                    title="認証公開設定の変更",
                    description="auth token external exposure public CORS",
                    action_type="update",
                    target_files=["main.py"],
                    risk_level="high",
                    verification="-",
                    rollback="-",
                )
            ]
        )
        result = reviewer.review(requirement=self._requirement(), plan=plan, nexus_context={}, repository_context="")
        self.assertIn("security", {f.category for f in result.findings})
        self.assertIn(result.overall_risk, {"high", "critical"})

    def test_missing_test_detect_for_high_risk(self):
        reviewer = PlanReviewer()
        plan = self._plan(
            target_files=["requirements.txt"],
            test_plan=[],
        )
        result = reviewer.review(requirement=self._requirement(), plan=plan, nexus_context={}, repository_context="")
        cats = [f.category for f in result.findings]
        self.assertIn("missing_test", cats)

    def test_out_of_scope_detect(self):
        reviewer = PlanReviewer()
        req = self._requirement(out_of_scope=["自動コード実装"])
        plan = self._plan(
            implementation_steps=[
                ImplementationStep(
                    step_id="step_1",
                    title="自動コード実装を実行",
                    description="自動コード実装を行う",
                    action_type="run_command",
                    target_files=["agent/project_generator.py"],
                    risk_level="high",
                    verification="-",
                    rollback="-",
                )
            ],
            target_files=["agent/project_generator.py"],
        )
        result = reviewer.review(requirement=req, plan=plan, nexus_context={}, repository_context="")
        self.assertIn("requirement_mismatch", {f.category for f in result.findings})

    def test_japanese_keyword_detect(self):
        reviewer = PlanReviewer()
        plan = self._plan(
            implementation_steps=[
                ImplementationStep(
                    step_id="step_1",
                    title="大量削除と外部公開",
                    description="認証設定を変更し外部公開する",
                    action_type="update",
                    target_files=["main.py"],
                    risk_level="high",
                    verification="-",
                    rollback="-",
                )
            ],
            test_plan=[],
        )
        result = reviewer.review(requirement=self._requirement(), plan=plan, nexus_context={}, repository_context="")
        categories = {f.category for f in result.findings}
        self.assertTrue({"destructive_change", "security"} & categories)



def _fake_llm_json_phase4(prompt: str, user_content: str) -> dict | None:
    if "User Input:" not in user_content:
        return {
            "interpreted_goal": "Plan review統合",
            "functional_requirements": ["Plan生成後にreviewする"],
            "constraints": ["自動実装しない"],
            "done_definition": ["review_resultが返る"],
        }
    return {
        "requirement_summary": "phase4",
        "selected_architecture": "incremental",
        "implementation_steps": [
            {
                "title": "依存更新",
                "description": "requirements.txt を更新",
                "target_files": ["requirements.txt"],
                "action_type": "delete",
                "risk_level": "high",
                "verification": "-",
                "rollback": "-",
            }
        ],
        "target_files": ["requirements.txt"],
        "test_plan": [],
    }


class Phase4RunnerIntegrationTests(unittest.TestCase):
    def test_runner_returns_review_result_and_updates_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir(parents=True, exist_ok=True)
            (project / "requirements.txt").write_text("fastapi\n", encoding="utf-8")

            runner = TaskPlanningRunner(ca_data_dir=str(root / "ca_data"), llm_json_fn=_fake_llm_json_phase4)
            out = runner.run(
                user_input="依存更新を含む計画を作る",
                project_path=str(project),
                planning_mode="standard",
                requirement_mode="ask_when_needed",
                execution_mode="plan_and_execute",
                use_nexus=False,
            )
            self.assertIn("review_result", out)
            self.assertEqual(out.get("effective_execution_mode"), "plan_only")
            self.assertTrue(out["plan"]["requires_user_confirmation"])
            self.assertIn(out["status"], {"needs_confirmation", "needs_revision", "rejected"})


if __name__ == "__main__":
    unittest.main()
