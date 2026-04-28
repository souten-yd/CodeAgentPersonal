from __future__ import annotations

import json
from pathlib import Path

from agent.plan_review_schema import PlanReviewResult
from agent.plan_schema import Plan
from agent.requirement_schema import RequirementDefinition


class PlanStorage:
    def __init__(self, ca_data_dir: str | Path) -> None:
        self.base_dir = Path(ca_data_dir)
        self.requirements_dir = self.base_dir / "requirements"
        self.plans_dir = self.base_dir / "plans"
        self.reviews_dir = self.base_dir / "reviews"
        self.requirements_dir.mkdir(parents=True, exist_ok=True)
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.reviews_dir.mkdir(parents=True, exist_ok=True)

    def requirement_json_path(self, requirement_id: str) -> Path:
        return self.requirements_dir / f"{requirement_id}.json"

    def requirement_markdown_path(self, requirement_id: str) -> Path:
        return self.requirements_dir / f"{requirement_id}.md"

    def plan_json_path(self, plan_id: str) -> Path:
        return self.plans_dir / f"{plan_id}.plan.json"

    def plan_markdown_path(self, plan_id: str) -> Path:
        return self.plans_dir / f"{plan_id}.plan.md"

    def review_json_path(self, review_id: str) -> Path:
        return self.reviews_dir / f"{review_id}.review.json"

    def review_markdown_path(self, review_id: str) -> Path:
        return self.reviews_dir / f"{review_id}.review.md"

    def save_requirement(self, req: RequirementDefinition) -> tuple[Path, Path]:
        req_json = self.requirement_json_path(req.requirement_id)
        req_md = self.requirement_markdown_path(req.requirement_id)
        req_json.write_text(json.dumps(req.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        req_md.write_text(self._requirement_to_markdown(req), encoding="utf-8")
        return req_json, req_md

    def save_plan(
        self,
        plan: Plan,
        user_input: str,
        interpreted_goal: str,
        review_result: PlanReviewResult | None = None,
    ) -> tuple[Path, Path]:
        plan_json = self.plan_json_path(plan.plan_id)
        plan_md = self.plan_markdown_path(plan.plan_id)
        payload = plan.model_dump()
        if review_result is not None:
            payload["review_result"] = review_result.model_dump()
        plan_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        plan_md.write_text(
            self._plan_to_markdown(
                plan,
                user_input=user_input,
                interpreted_goal=interpreted_goal,
                review_result=review_result,
            ),
            encoding="utf-8",
        )
        return plan_json, plan_md

    def save_review(self, review_result: PlanReviewResult) -> tuple[Path, Path]:
        review_json = self.review_json_path(review_result.review_id)
        review_md = self.review_markdown_path(review_result.review_id)
        review_json.write_text(json.dumps(review_result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        review_md.write_text(self._review_to_markdown(review_result), encoding="utf-8")
        return review_json, review_md

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

    def load_review(self, review_id: str) -> dict:
        path = self.review_json_path(review_id)
        if not path.exists():
            raise FileNotFoundError(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def read_plan_markdown(self, plan_id: str) -> str:
        path = self.plan_markdown_path(plan_id)
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8")

    def read_review_markdown(self, review_id: str) -> str:
        path = self.review_markdown_path(review_id)
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8")

    def read_requirement_markdown(self, requirement_id: str) -> str:
        path = self.requirement_markdown_path(requirement_id)
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
            f"## Clarification Status\n- {req.clarification_status}",
            "",
            "## 未回答質問",
            *[f"- [{q.importance}] {q.question} (default: {q.default})" for q in req.open_questions],
            "",
            "## 回答済み質問",
            *[f"- [{q.importance}] {q.question} => {q.answer}" for q in req.answered_questions],
            "",
            "## 完了条件",
            *[f"- {x}" for x in req.done_definition],
            "",
            f"## 要件明確度スコア\n- overall: {req.requirement_completeness_score}",
        ])

    def _plan_to_markdown(
        self,
        plan: Plan,
        user_input: str,
        interpreted_goal: str,
        review_result: PlanReviewResult | None = None,
    ) -> str:
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

        review_section = self._plan_review_markdown_section(review_result)
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
            "",
            *review_section,
        ])

    def _plan_review_markdown_section(self, review_result: PlanReviewResult | None) -> list[str]:
        if review_result is None:
            return ["## Plan Review", "- Review result: not available"]

        lines = [
            "## Plan Review",
            f"- Overall risk: {review_result.overall_risk}",
            f"- Requires user confirmation: {str(review_result.requires_user_confirmation).lower()}",
            f"- Destructive change detected: {str(review_result.destructive_change_detected).lower()}",
            f"- Recommended next action: {review_result.recommended_next_action}",
            f"- Summary: {review_result.summary}",
            "",
            "### Findings",
        ]
        if not review_result.findings:
            lines.append("- No findings")
            return lines

        for finding in review_result.findings[:10]:
            lines.extend([
                f"- [{finding.severity}][{finding.category}] {finding.title}",
                f"  - detail: {finding.detail}",
                f"  - recommendation: {finding.recommendation}",
            ])
        return lines

    def _review_to_markdown(self, review_result: PlanReviewResult) -> str:
        lines = [
            f"# Plan Review: {review_result.review_id}",
            f"- Plan ID: {review_result.plan_id}",
            f"- Requirement ID: {review_result.requirement_id}",
            f"- Created At: {review_result.created_at}",
            "",
            f"- Overall risk: {review_result.overall_risk}",
            f"- Requires user confirmation: {str(review_result.requires_user_confirmation).lower()}",
            f"- Destructive change detected: {str(review_result.destructive_change_detected).lower()}",
            f"- Recommended next action: {review_result.recommended_next_action}",
            f"- Summary: {review_result.summary}",
            "",
            "## Findings",
        ]
        if not review_result.findings:
            lines.append("- No findings")
        else:
            for finding in review_result.findings:
                lines.extend([
                    f"- [{finding.severity}][{finding.category}] {finding.title}",
                    f"  - detail: {finding.detail}",
                    f"  - recommendation: {finding.recommendation}",
                ])
        return "\n".join(lines)
