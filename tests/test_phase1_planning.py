from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.task_planning_runner import TaskPlanningRunner


def _fake_llm_json_ok(prompt: str, user_content: str) -> dict | None:
    if "Requirement" in prompt or "requirement" in prompt:
        return {
            "interpreted_goal": "Phase 1.5 の計画品質を改善する",
            "functional_requirements": ["Plan only 結果を保存する", "warning を返す"],
            "non_functional_requirements": ["既存機能を壊さない"],
            "constraints": ["Phase 2 機能は実装しない"],
            "done_definition": ["計画を安全に確認できること"],
        }
    return {
        "requirement_summary": "Plan only の安定化",
        "architecture_options": ["Incremental additive changes"],
        "selected_architecture": "Incremental additive changes",
        "implementation_steps": [
            {
                "title": "調査",
                "description": "既存実装を確認する",
                "target_files": ["main.py", "ui.html"],
                "action_type": "inspect",
                "risk_level": "low",
                "verification": "差分が最小であること",
                "rollback": "変更をrevert",
            }
        ],
        "test_plan": ["pytest を実行する"],
        "rollback_plan": ["git revert を実施する"],
    }


def _fake_llm_json_none(prompt: str, user_content: str) -> dict | None:
    return None


class Phase1PlanningRunnerTests(unittest.TestCase):
    def _build_runner(self, tmp_path: Path, llm_json_fn) -> TaskPlanningRunner:
        return TaskPlanningRunner(
            ca_data_dir=str(tmp_path / "ca_data"),
            llm_json_fn=llm_json_fn,
            memory_search_fn=None,
            active_skills_fn=None,
        )

    def test_phase1_runner_success_and_storage(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            runner = self._build_runner(tmp_path, _fake_llm_json_ok)
            project_dir = tmp_path / "project_a"
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "README.md").write_text("# sample\n", encoding="utf-8")

            result = runner.run(
                user_input="Task機能のPlan only補修をしたい",
                project_path=str(project_dir),
                planning_mode="standard",
                requirement_mode="ask_when_needed",
                execution_mode="plan_and_execute",
                use_nexus=True,
            )

            self.assertEqual(result["status"], "planned")
            self.assertEqual(result["effective_execution_mode"], "plan_only")
            self.assertFalse(result["nexus_context"]["available"])
            self.assertIsInstance(result.get("warnings"), list)

            requirement_id = result["requirement_id"]
            plan_id = result["plan_id"]
            ca_data = tmp_path / "ca_data"
            req_json = ca_data / "requirements" / f"{requirement_id}.json"
            req_md = ca_data / "requirements" / f"{requirement_id}.md"
            plan_json = ca_data / "plans" / f"{plan_id}.plan.json"
            plan_md = ca_data / "plans" / f"{plan_id}.plan.md"

            self.assertTrue(req_json.exists())
            self.assertTrue(req_md.exists())
            self.assertTrue(plan_json.exists())
            self.assertTrue(plan_md.exists())

    def test_phase1_runner_fallback_warning_and_japanese_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            runner = self._build_runner(tmp_path, _fake_llm_json_none)
            project_dir = tmp_path / "project_b"
            project_dir.mkdir(parents=True, exist_ok=True)

            jp_input = "要件定義と計画を日本語で安全に作成したい"
            result = runner.run(
                user_input=jp_input,
                project_path=str(project_dir),
                planning_mode="deep_nexus",
                requirement_mode="full_session",
                execution_mode="plan_and_execute",
                use_nexus=True,
            )

            self.assertEqual(result["status"], "planned")
            self.assertEqual(result["effective_execution_mode"], "plan_only")
            warnings = result.get("warnings") or []
            self.assertTrue(warnings)
            self.assertTrue(any("Fallback" in w or "fallback" in w for w in warnings))

            req_path = Path(result["requirement_markdown_path"])
            plan_path = Path(result["plan_markdown_path"])
            self.assertIn(jp_input, req_path.read_text(encoding="utf-8"))
            self.assertIn("要件", plan_path.read_text(encoding="utf-8"))

            req_json_path = tmp_path / "ca_data" / "requirements" / f"{result['requirement_id']}.json"
            req_data = json.loads(req_json_path.read_text(encoding="utf-8"))
            self.assertEqual(req_data["user_input"], jp_input)


if __name__ == "__main__":
    unittest.main()
