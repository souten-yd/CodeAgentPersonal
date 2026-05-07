from __future__ import annotations

from typing import Callable

from agent.deep_planner_schema import DeepArchitectureOption, DeepPlanPayload, DeepPlanningReflection
from agent.requirement_schema import RequirementDefinition


class DeepPlanner:
    def __init__(self, llm_json_fn: Callable[[str, str], dict | None]) -> None:
        self.llm_json_fn = llm_json_fn
        self._last_warnings: list[str] = []

    def get_last_warnings(self) -> list[str]:
        return list(self._last_warnings)

    def build_deep_plan(
        self,
        *,
        requirement: RequirementDefinition,
        prompt: str,
        nexus_context: dict,
        repository_context: str,
    ) -> DeepPlanPayload:
        warnings: list[str] = []
        planner_input = (
            f"User input: {requirement.user_input}\n"
            f"Requirement: {requirement.interpreted_goal}\n"
            f"Nexus context: {nexus_context}\n"
            f"Repository context: {repository_context}"
        )
        raw_payload = self.llm_json_fn(prompt, planner_input)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        if raw_payload is None:
            warnings.append("Deep planner LLM output could not be parsed. Fallback deep plan was generated.")
        elif not isinstance(raw_payload, dict):
            warnings.append("Deep planner LLM output was not a JSON object. Fallback deep plan was generated.")
        elif not raw_payload:
            warnings.append("Deep planner LLM output was empty. Fallback deep plan was generated.")

        options = self._build_three_options(payload)
        selected_option_id = str(payload.get("selected_option_id") or "B").strip().upper()
        if selected_option_id not in {"A", "B", "C"}:
            selected_option_id = "B"
            warnings.append("selected_option_id was invalid and has been normalized to B.")
        for opt in options:
            if opt.option_id == selected_option_id and not opt.why_selected:
                opt.why_selected = "Selected as the best balance of risk, speed, and maintainability."
            if opt.option_id != selected_option_id and not opt.why_rejected:
                opt.why_rejected = "Not selected due to trade-offs versus the chosen option."

        reflection_raw = payload.get("reflection") if isinstance(payload.get("reflection"), dict) else {}
        reflection = DeepPlanningReflection(
            nexus_context_used=str(reflection_raw.get("nexus_context_used") or "Nexus context summarized and considered when available."),
            repository_context_used=str(reflection_raw.get("repository_context_used") or "Repository structure and likely touch points were considered."),
            assumptions=_as_list(reflection_raw.get("assumptions")) or requirement.assumptions,
            unresolved_questions=_as_list(reflection_raw.get("unresolved_questions")),
            safety_notes=_as_list(reflection_raw.get("safety_notes")) or [
                "Planning-only output: no implementation execution.",
                "No direct file mutation in Deep Planner stage.",
            ],
            non_goals=_as_list(reflection_raw.get("non_goals")) or ["No automatic apply/approve in this planning phase."],
        )

        deep_plan = DeepPlanPayload(
            requirement_id=requirement.requirement_id,
            planning_mode="deep_nexus",
            user_goal=str(payload.get("user_goal") or requirement.interpreted_goal),
            requirement_summary=str(payload.get("requirement_summary") or requirement.interpreted_goal),
            architecture_options=options,
            selected_option_id=selected_option_id,
            reflection=reflection,
            implementation_phases=_as_list(payload.get("implementation_phases")) or [
                "Phase 1: analyze scope and impacted components",
                "Phase 2: prepare implementation plan detail",
                "Phase 3: verify readiness and handoff to execution pipeline",
            ],
            verification_strategy=_as_list(payload.get("verification_strategy")) or [
                "Validate plan consistency with requirement and constraints.",
                "Confirm safety gates and approval checkpoints remain intact.",
            ],
            done_definition=_as_list(payload.get("done_definition")) or requirement.done_definition,
        )
        self._last_warnings = warnings
        return deep_plan

    def _build_three_options(self, payload: dict) -> list[DeepArchitectureOption]:
        raw = payload.get("architecture_options") if isinstance(payload.get("architecture_options"), list) else []
        mapped: dict[str, dict] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("option_id") or "").strip().upper()
            if key in {"A", "B", "C"}:
                mapped[key] = item
        return [
            self._build_option("A", "最小改修", mapped.get("A")),
            self._build_option("B", "中規模整理", mapped.get("B")),
            self._build_option("C", "将来拡張前提", mapped.get("C")),
        ]

    def _build_option(self, option_id: str, default_title: str, raw: dict | None) -> DeepArchitectureOption:
        raw = raw or {}
        return DeepArchitectureOption(
            option_id=option_id,
            title=str(raw.get("title") or default_title),
            summary=str(raw.get("summary") or f"{default_title}アプローチで要件を満たす。"),
            scope=_as_list(raw.get("scope")),
            benefits=_as_list(raw.get("benefits")),
            drawbacks=_as_list(raw.get("drawbacks")),
            risk_level=str(raw.get("risk_level") or "medium"),
            estimated_complexity=str(raw.get("estimated_complexity") or "medium"),
            target_files=_as_list(raw.get("target_files")),
            why_selected=str(raw.get("why_selected") or ""),
            why_rejected=str(raw.get("why_rejected") or ""),
        )


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
