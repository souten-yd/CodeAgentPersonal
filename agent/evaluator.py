from __future__ import annotations

from agent.types import Evaluation, Plan, ToolResult


class Evaluator:
    """実行結果の評価インターフェース。"""

    def evaluate(self, plan: Plan, history: list[ToolResult]) -> Evaluation:
        raise NotImplementedError
