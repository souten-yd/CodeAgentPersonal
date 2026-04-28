from __future__ import annotations

import json
from pathlib import Path

from agent.plan_schema import Plan
from agent.requirement_schema import RequirementDefinition


class PlanStorage:
    def __init__(self, ca_data_dir: str | Path) -> None:
        self.base_dir = Path(ca_data_dir)
        self.requirements_dir = self.base_dir / "requirements"
        self.plans_dir = self.base_dir / "plans"
        self.requirements_dir.mkdir(parents=True, exist_ok=True)
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    def requirement_json_path(self, requirement_id: str) -> Path:
        return self.requirements_dir / f"{requirement_id}.json"

    def requirement_markdown_path(self, requirement_id: str) -> Path:
        return self.requirements_dir / f"{requirement_id}.md"

    def plan_json_path(self, plan_id: str) -> Path:
        return self.plans_dir / f"{plan_id}.plan.json"

    def plan_markdown_path(self, plan_id: str) -> Path:
        return self.plans_dir / f"{plan_id}.plan.md"

    def save_requirement(self, req: RequirementDefinition) -> tuple[Path, Path]:
        req_json = self.requirement_json_path(req.requirement_id)
        req_md = self.requirement_markdown_path(req.requirement_id)
        req_json.write_text(json.dumps(req.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        req_md.write_text(self._requirement_to_markdown(req), encoding="utf-8")
        return req_json, req_md

    def save_plan(self, plan: Plan, user_input: str, interpreted_goal: str) -> tuple[Path, Path]:
        plan_json = self.plan_json_path(plan.plan_id)
        plan_md = self.plan_markdown_path(plan.plan_id)
        plan_json.write_text(json.dumps(plan.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        plan_md.write_text(self._plan_to_markdown(plan, user_input=user_input, interpreted_goal=interpreted_goal), encoding="utf-8")
        return plan_json, plan_md

    def load_requirement(self, requirement_id: str) -> dict:
        path = self.requirement_json_path(requirement_id)
        if not path.exists():
            raise FileNotFoundError(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def load_plan(self, plan_id: str) -> dict:
        path = self.plan_json_path(plan_id)
        if not path.exists():
            raise FileNotFoundError(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def read_plan_markdown(self, plan_id: str) -> str:
        path = self.plan_markdown_path(plan_id)
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8")

    def _requirement_to_markdown(self, req: RequirementDefinition) -> str:
        return "\n".join([
            f"# Requirement Definition: {req.requirement_id}",
            "",
            "## ユーザー入力",
            req.user_input,
            "",
            "## 解釈した目的",
            req.interpreted_goal,
            "",
            "## ユーザー意図",
            req.user_intent,
            "",
            "## 機能要件",
            *[f"- {x}" for x in req.functional_requirements],
            "",
            "## 非機能要件",
            *[f"- {x}" for x in req.non_functional_requirements],
            "",
            "## 制約",
            *[f"- {x}" for x in req.constraints],
            "",
            "## 仮定",
            *[f"- {x}" for x in req.assumptions],
            "",
            "## 完了条件",
            *[f"- {x}" for x in req.done_definition],
            "",
            f"## 要件明確度スコア\n- overall: {req.requirement_completeness_score}",
        ])

    def _plan_to_markdown(self, plan: Plan, user_input: str, interpreted_goal: str) -> str:
        step_lines: list[str] = []
        for idx, step in enumerate(plan.implementation_steps, start=1):
            step_lines.extend([
                f"### Step {idx}: {step.title}",
                f"- Description: {step.description}",
                f"- Action: {step.action_type}",
                f"- Risk: {step.risk_level}",
                f"- Target files: {', '.join(step.target_files) if step.target_files else '-'}",
                f"- Verification: {step.verification}",
                f"- Rollback: {step.rollback}",
                "",
            ])

        return "\n".join([
            f"# Plan: {plan.plan_id}",
            "",
            "## ユーザー依頼",
            user_input,
            "",
            "## 解釈した目的",
            interpreted_goal,
            "",
            "## 要件要約",
            plan.requirement_summary,
            "",
            "## Nexus参照要約",
            plan.nexus_context_summary,
            "",
            "## 現状・前提",
            *[f"- {x}" for x in plan.assumptions],
            "",
            "## 実装案",
            *[f"- {x}" for x in plan.architecture_options],
            "",
            "## 採用案",
            plan.selected_architecture,
            "",
            "## 実装ステップ",
            *step_lines,
            "## 対象ファイル",
            *[f"- {x}" for x in plan.target_files],
            "",
            "## リスク",
            *[f"- {x}" for x in plan.risks],
            "",
            "## テスト計画",
            *[f"- {x}" for x in plan.test_plan],
            "",
            "## 完了条件",
            *[f"- {x}" for x in plan.done_definition],
            "",
            "## ロールバック方針",
            *[f"- {x}" for x in plan.rollback_plan],
        ])
