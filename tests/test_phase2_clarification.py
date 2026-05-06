from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.requirement_schema import RequirementDefinition
from agent.clarification_policy import ClarificationPolicy
from agent.task_planning_runner import TaskPlanningRunner


def _fake_llm_json_phase2(prompt: str, user_content: str) -> dict | None:
    if "Requirement" in prompt or "requirement" in prompt:
        task_type = "bugfix" if "typo" in user_content.lower() or "バグ" in user_content else "project_generation"
        return {
            "interpreted_goal": "大型機能の要件を固める",
            "task_type": task_type,
            "functional_requirements": ["質問フローを追加する", "Plan onlyを維持する"],
            "non_functional_requirements": ["既存機能を壊さない"],
            "constraints": ["自動実装しない"],
            "open_questions": [
                "優先する方針は？",
                "データ保存方式は？",
                "セキュリティ強化の範囲は？",
                "ログ粒度は？",
                "UI優先度は？",
            ],
            "done_definition": ["質問回答後にPlan生成できる"],
        }
    return {
        "requirement_summary": "Phase 2 clarification flow",
        "architecture_options": ["Incremental additive changes"],
        "selected_architecture": "Incremental additive changes",
        "implementation_steps": [
            {
                "title": "調査",
                "description": "要件と質問を整理",
                "target_files": ["main.py", "ui.html"],
                "action_type": "inspect",
                "risk_level": "low",
                "verification": "API動作確認",
                "rollback": "変更をrevert",
            }
        ],
        "test_plan": ["pytest"],
        "rollback_plan": ["git revert"],
    }


class Phase2ClarificationTests(unittest.TestCase):
    def _build_runner(self, tmp_path: Path) -> TaskPlanningRunner:
        return TaskPlanningRunner(
            ca_data_dir=str(tmp_path / "ca_data"),
            llm_json_fn=_fake_llm_json_phase2,
            memory_search_fn=None,
            active_skills_fn=None,
        )

    def test_waiting_for_clarification_and_requirement_saved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            project_dir = tmp_path / "project_phase2"
            project_dir.mkdir(parents=True, exist_ok=True)
            runner = self._build_runner(tmp_path)

            result = runner.run(
                user_input="新規 project を生成し公開運用まで見据えたい",
                project_path=str(project_dir),
                planning_mode="standard",
                requirement_mode="ask_when_needed",
                execution_mode="plan_only",
                use_nexus=False,
            )

            self.assertEqual(result["status"], "waiting_for_clarification")
            self.assertTrue(result.get("questions"))
            requirement_id = result["requirement_id"]
            req_json = tmp_path / "ca_data" / "requirements" / f"{requirement_id}.json"
            self.assertTrue(req_json.exists())
            self.assertNotIn("plan_id", result)

    def test_answer_updates_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            project_dir = tmp_path / "project_phase2_b"
            project_dir.mkdir(parents=True, exist_ok=True)
            runner = self._build_runner(tmp_path)

            waiting = runner.run(
                user_input="新規 project を生成し公開運用まで見据えたい",
                project_path=str(project_dir),
                requirement_mode="ask_when_needed",
            )
            q = waiting["questions"][0]
            ans = runner.answer_requirement_questions(
                requirement_id=waiting["requirement_id"],
                answers=[{"question_id": q["question_id"], "answer": "おまかせ"}],
            )
            req = ans["requirement"]
            self.assertTrue(req["answered_questions"])
            self.assertLess(len(req["open_questions"]), len(waiting["questions"]))
            self.assertIn(req["clarification_status"], {"answered", "waiting"})

    def test_continue_generates_plan_plan_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            project_dir = tmp_path / "project_phase2_c"
            project_dir.mkdir(parents=True, exist_ok=True)
            runner = self._build_runner(tmp_path)

            waiting = runner.run(
                user_input="新規 project を生成し公開運用まで見据えたい",
                project_path=str(project_dir),
                requirement_mode="ask_when_needed",
            )
            runner.skip_requirement_questions(requirement_id=waiting["requirement_id"])
            planned = runner.continue_from_requirement(
                requirement_id=waiting["requirement_id"],
                planning_mode="standard",
                requirement_mode="ask_when_needed",
                execution_mode="plan_only",
                use_nexus=False,
                project_path=str(project_dir),
            )
            self.assertEqual(planned["status"], "planned")
            self.assertTrue(planned.get("plan_id"))
            self.assertEqual(planned["effective_execution_mode"], "plan_only")

    def test_small_task_without_questions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            project_dir = tmp_path / "project_small"
            project_dir.mkdir(parents=True, exist_ok=True)
            runner = self._build_runner(tmp_path)

            result = runner.run(
                user_input="小さなUIバグ修正: ボタンの文言 typo を直す",
                project_path=str(project_dir),
                requirement_mode="ask_when_needed",
            )
            self.assertEqual(result["status"], "planned")
            self.assertFalse(result.get("questions"))

    def test_question_limit_per_mode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            runner = self._build_runner(tmp_path)
            req = RequirementDefinition(
                requirement_id="req_limit",
                source_task_id="task_limit",
                user_input="新規 project の詳細設計",
                task_type="project_generation",
                open_questions=[f"Q{i}" for i in range(1, 12)],
            )
            ask_result = runner.clarification_manager.generate(req.model_copy(deep=True), "ask_when_needed")
            full_result = runner.clarification_manager.generate(req.model_copy(deep=True), "full_requirement_session")
            self.assertLessEqual(len(ask_result.questions), 3)
            self.assertLessEqual(len(full_result.questions), 7)

    def test_japanese_question_answer_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            project_dir = tmp_path / "project_jp"
            project_dir.mkdir(parents=True, exist_ok=True)
            runner = self._build_runner(tmp_path)

            waiting = runner.run(
                user_input="新規 project を日本語UIで作成したい",
                project_path=str(project_dir),
                requirement_mode="ask_when_needed",
            )
            first = waiting["questions"][0]
            runner.answer_requirement_questions(
                requirement_id=waiting["requirement_id"],
                answers=[{"question_id": first["question_id"], "answer": "UI/UX品質を優先する"}],
            )
            req_json = tmp_path / "ca_data" / "requirements" / f"{waiting['requirement_id']}.json"
            data = json.loads(req_json.read_text(encoding="utf-8"))
            answer_text = json.dumps(data.get("answered_questions", []), ensure_ascii=False)
            self.assertIn("UI/UX品質を優先する", answer_text)

    def test_legacy_what_question_is_not_yes_no(self) -> None:
        req = RequirementDefinition(
            requirement_id="req_legacy",
            source_task_id="task_legacy",
            user_input="x",
            open_questions=["What level of fidelity is required?"],
        )
        self.assertEqual(req.open_questions[0].type, "free_text")
        self.assertEqual(req.open_questions[0].options, ["おまかせ"])

    def test_answer_backward_compatibility_string_normalization(self) -> None:
        req = RequirementDefinition(
            requirement_id="req_ans",
            source_task_id="task_ans",
            user_input="x",
            open_questions=[{"question_id": "q1", "question": "必要ですか", "type": "yes_no", "options": ["はい", "いいえ", "おまかせ"], "default": "おまかせ"}],
        )
        from agent.clarification_manager import ClarificationManager
        updated = ClarificationManager().apply_answers(req, [{"question_id": "q1", "answer": "おまかせ"}])
        self.assertEqual(updated.answered_questions[0].answer.get("mode"), "delegate")

    def test_clarification_policy_stable(self) -> None:
        policy = ClarificationPolicy()
        d1 = policy.classify(user_input="新規 project を設計する", task_type="project_generation", requirement_mode="ask_when_needed", project_context="")
        d2 = policy.classify(user_input="新規 project を設計する", task_type="project_generation", requirement_mode="ask_when_needed", project_context="")
        self.assertEqual(d1, d2)


if __name__ == "__main__":
    unittest.main()
