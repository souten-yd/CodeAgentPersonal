from __future__ import annotations

from agent.types import Action, ToolResult


class Executor:
    """Action 実行インターフェース。"""

    def execute(self, action: Action) -> ToolResult:
        raise NotImplementedError
