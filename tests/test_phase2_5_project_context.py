from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main
from agent.task_planning_runner import TaskPlanningRunner


def _fake_llm_json_phase25(prompt: str, user_content: str) -> dict | None:
    if "Requirement" in prompt or "requirement" in prompt:
        return {
            "interpreted_goal": "質問フローの安定化",
            "functional_requirements": ["質問への回答を受け付ける"],
            "non_functional_requirements": ["安全にplan_onlyで動作"],
            "constraints": ["実装は実行しない"],
            "open_questions": ["優先事項は？", "想定ユーザーは？", "対象環境は？"],
            "done_definition": ["質問後に計画を生成できる"],
        }
    return {
        "requirement_summary": "Phase2.5 project context",
        "architecture_options": ["Incremental"],
        "selected_architecture": "Incremental",
        "implementation_steps": [
            {
                "title": "Context確認",
                "description": "repository_contextを確認",
                "target_files": ["README.md"],
                "action_type": "inspect",
                "risk_level": "low",
                "verification": "contextにファイルが出る",
                "rollback": "revert",
            }
        ],
        "test_plan": ["unittest"],
        "rollback_plan": ["git revert"],
    }


class Phase25ProjectContextTests(unittest.TestCase):
    def _build_runner(self, tmp_path: Path) -> TaskPlanningRunner:
        return TaskPlanningRunner(
            ca_data_dir=str(tmp_path / "ca_data"),
            llm_json_fn=_fake_llm_json_phase25,
            memory_search_fn=None,
            active_skills_fn=None,
        )

    def test_continue_inherits_project_context_when_project_path_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            project_dir = tmp_path / "project_ctx"
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "README.md").write_text("# phase2.5\n", encoding="utf-8")
            runner = self._build_runner(tmp_path)

            waiting = runner.run(
                user_input="質問フローの続行を確認したい",
                project_path=str(project_dir),
                project_name="project_ctx",
                requirement_mode="ask_when_needed",
                execution_mode="plan_and_execute",
                use_nexus=False,
            )
            runner.skip_requirement_questions(requirement_id=waiting["requirement_id"])

            planned = runner.continue_from_requirement(
                requirement_id=waiting["requirement_id"],
                planning_mode="standard",
                requirement_mode="ask_when_needed",
                execution_mode="plan_and_execute",
                use_nexus=False,
                project_path="",
                project_name="",
                resolved_project_path="",
            )
            self.assertEqual(planned["status"], "planned")
            self.assertEqual(planned["effective_execution_mode"], "plan_only")
            self.assertIn("README.md", planned["repository_context"])
            self.assertEqual(planned.get("resolved_project_path"), str(project_dir))

    def test_project_resolver_with_project_name_and_invalid_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            (work_dir / "sample_project").mkdir(parents=True, exist_ok=True)
            original_work_dir = main.WORK_DIR
            try:
                main.WORK_DIR = str(work_dir)
                resolved, warnings = main._resolve_project_path_for_phase_planning("", "sample_project")
                self.assertEqual(resolved, str((work_dir / "sample_project").resolve()))
                self.assertEqual(warnings, [])

                bad_resolved, bad_warnings = main._resolve_project_path_for_phase_planning("missing/path", "not_found")
                self.assertEqual(bad_resolved, str((work_dir / "default").resolve()))
                self.assertTrue(any("project_path" in w or "project_name" in w for w in bad_warnings))
            finally:
                main.WORK_DIR = original_work_dir

    def test_japanese_requirement_answer_continue_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            project_dir = tmp_path / "project_japanese"
            project_dir.mkdir(parents=True, exist_ok=True)
            runner = self._build_runner(tmp_path)

            waiting = runner.run(
                user_input="日本語の質問フローを継続したい",
                project_path=str(project_dir),
                project_name="project_japanese",
                requirement_mode="ask_when_needed",
                use_nexus=False,
            )
            first = waiting["questions"][0]
            runner.answer_requirement_questions(
                requirement_id=waiting["requirement_id"],
                answers=[{"question_id": first["question_id"], "answer": "日本語でお願いします"}],
            )
            runner.skip_requirement_questions(requirement_id=waiting["requirement_id"])
            planned = runner.continue_from_requirement(
                requirement_id=waiting["requirement_id"],
                planning_mode="standard",
                requirement_mode="ask_when_needed",
                execution_mode="plan_only",
                use_nexus=False,
            )
            text = str(planned.get("requirement", {}))
            self.assertIn("日本語", text)


if __name__ == "__main__":
    unittest.main()
