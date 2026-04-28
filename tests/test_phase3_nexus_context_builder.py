from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.nexus_context_builder import NexusContextBuilder
from agent.task_planning_runner import TaskPlanningRunner


def _fake_llm_json(prompt: str, user_content: str) -> dict | None:
    if "Requirement" in prompt or "requirement" in prompt:
        return {
            "interpreted_goal": "Phase3 nexus context quality",
            "functional_requirements": ["collect context", "keep plan only"],
            "constraints": ["do not execute implementation"],
            "done_definition": ["can produce plan safely"],
        }
    return {
        "requirement_summary": "nexus context flow",
        "selected_architecture": "Incremental",
        "implementation_steps": [
            {
                "title": "Inspect",
                "description": "Inspect planning input",
                "target_files": ["agent/nexus_context_builder.py"],
                "action_type": "inspect",
                "risk_level": "low",
                "verification": "check context",
                "rollback": "revert",
            }
        ],
        "test_plan": ["unittest"],
        "rollback_plan": ["git revert"],
    }


class Phase3NexusContextBuilderTests(unittest.TestCase):
    def test_build_success_when_nexus_unconfigured(self) -> None:
        builder = NexusContextBuilder(memory_search_fn=None, active_skills_fn=None)
        out = builder.build("nexus context test", use_nexus=True)
        self.assertIsInstance(out, dict)
        self.assertFalse(out["available"])
        self.assertTrue(out.get("warnings"))

    def test_build_memory_and_skills_items(self) -> None:
        def fake_memory(query: str, limit: int = 5):
            return [{"title": "Fix warning", "content": "warning fix solution", "category": "log", "score": 0.8}]

        def fake_skills():
            return [{"name": "skill-a", "description": "handles warning patterns", "path": "/tmp/skill-a"}]

        builder = NexusContextBuilder(memory_search_fn=fake_memory, active_skills_fn=fake_skills)
        out = builder.build("warning solution", use_nexus=True)
        self.assertTrue(out["available"])
        self.assertIn("source_counts", out)
        self.assertGreaterEqual(out["source_counts"].get("memory", 0), 1)
        self.assertGreaterEqual(out["source_counts"].get("skill", 0), 1)
        self.assertIn("Nexus Context Summary", out.get("compact_text", ""))

    def test_collect_past_requirements_and_plans(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ca_data = root / "ca_data"
            req_dir = ca_data / "requirements"
            plan_dir = ca_data / "plans"
            req_dir.mkdir(parents=True, exist_ok=True)
            plan_dir.mkdir(parents=True, exist_ok=True)

            (req_dir / "req_x.json").write_text(
                json.dumps({"user_input": "nexus quality", "interpreted_goal": "improve context", "constraints": ["safe"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            (plan_dir / "plan_x.plan.json").write_text(
                json.dumps({"user_goal": "improve context", "selected_architecture": "Incremental", "risks": ["warning"]}, ensure_ascii=False),
                encoding="utf-8",
            )

            builder = NexusContextBuilder(ca_data_dir=str(ca_data))
            out = builder.build("improve context", use_nexus=True)
            types = {str(i.get("source_type") or i.get("type")) for i in out.get("items", [])}
            self.assertIn("past_requirement", types)
            self.assertIn("past_plan", types)

    def test_collect_project_context_and_exclude_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir(parents=True, exist_ok=True)
            (project / "README.md").write_text("# プロジェクト\nNexus Context", encoding="utf-8")
            (project / "pyproject.toml").write_text("[project]\nname='demo'", encoding="utf-8")
            (project / "ui.html").write_text("<html><body>ui</body></html>", encoding="utf-8")
            nm = project / "node_modules"
            nm.mkdir(parents=True, exist_ok=True)
            (nm / "SKILL.md").write_text("SHOULD_NOT_READ", encoding="utf-8")

            builder = NexusContextBuilder()
            out = builder.build("プロジェクト context", project_path=str(project), resolved_project_path=str(project), use_nexus=True)
            paths = [str(i.get("source_path") or "") for i in out.get("items", [])]
            self.assertTrue(any(p.endswith("README.md") for p in paths))
            self.assertFalse(any("node_modules" in p for p in paths))

    def test_context_budget_truncation(self) -> None:
        big_text = "日本語コンテキスト" * 2000

        def fake_memory(query: str, limit: int = 5):
            return [{"title": f"big-{i}", "content": big_text, "score": 0.9} for i in range(5)]

        def fake_skills():
            return [{"name": f"skill-{i}", "description": big_text, "path": f"/tmp/s{i}"} for i in range(5)]

        builder = NexusContextBuilder(memory_search_fn=fake_memory, active_skills_fn=fake_skills)
        out = builder.build("日本語", context_budget_chars=120, use_nexus=True)
        self.assertLessEqual(len(out.get("compact_text", "")), 500)
        self.assertTrue(out.get("truncated"))

    def test_runner_run_contains_extended_nexus_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir(parents=True, exist_ok=True)
            (project / "README.md").write_text("# test", encoding="utf-8")
            runner = TaskPlanningRunner(ca_data_dir=str(root / "ca_data"), llm_json_fn=_fake_llm_json)
            result = runner.run(user_input="context quality", project_path=str(project), use_nexus=True)
            self.assertIn("nexus_context", result)
            nc = result["nexus_context"]
            self.assertIn("compact_text", nc)
            self.assertIn("source_counts", nc)

    def test_continue_uses_saved_project_context_for_nexus_builder(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir(parents=True, exist_ok=True)
            (project / "README.md").write_text("# project context", encoding="utf-8")
            runner = TaskPlanningRunner(ca_data_dir=str(root / "ca_data"), llm_json_fn=_fake_llm_json)
            first = runner.run(user_input="context", project_path=str(project), use_nexus=True)

            captured: dict = {}
            original_build = runner.nexus_builder.build

            def wrapped_build(user_input: str, **kwargs):
                captured.update(kwargs)
                return original_build(user_input, **kwargs)

            runner.nexus_builder.build = wrapped_build  # type: ignore[method-assign]
            runner.continue_from_requirement(
                requirement_id=first["requirement_id"],
                planning_mode="standard",
                requirement_mode="ask_when_needed",
                execution_mode="plan_only",
                use_nexus=True,
                project_path="",
                project_name="",
                resolved_project_path="",
                nexus_context=None,
            )
            self.assertEqual(captured.get("project_path"), str(project))
            self.assertEqual(captured.get("resolved_project_path"), str(project))

    def test_japanese_filename_and_input_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            docs = project / "docs"
            docs.mkdir(parents=True, exist_ok=True)
            (project / "README.md").write_text("日本語README", encoding="utf-8")
            (docs / "設計メモ.md").write_text("要件と失敗例のまとめ", encoding="utf-8")
            builder = NexusContextBuilder()
            out = builder.build("日本語の要件と失敗例", project_path=str(project), resolved_project_path=str(project), use_nexus=True)
            joined = json.dumps(out, ensure_ascii=False)
            self.assertIn("日本語", joined)


if __name__ == "__main__":
    unittest.main()
