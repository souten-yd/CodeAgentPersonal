from __future__ import annotations

from agent.types import Action, Plan, ToolResult


class Planner:
    """Plan/Action 生成インターフェース。"""

    def create_plan(self, objective: str, context: dict) -> Plan:
        raise NotImplementedError

    def choose_next_action(self, plan: Plan, history: list[ToolResult]) -> Action | None:
        raise NotImplementedError
