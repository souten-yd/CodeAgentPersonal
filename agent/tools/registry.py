from __future__ import annotations

from collections.abc import Callable

from agent.types import Action, ToolResult

ToolCallable = Callable[[dict], ToolResult]


class ToolRegistry:
    """Action.tool 名と実行関数を結びつけるレジストリ。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolCallable] = {}

    def register(self, name: str, handler: ToolCallable) -> None:
        self._tools[name] = handler

    def get(self, name: str) -> ToolCallable | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def invoke(self, action: Action) -> ToolResult:
        handler = self.get(action.tool)
        if handler is None:
            return ToolResult(
                action_id=action.id,
                success=False,
                error=f"tool not found: {action.tool}",
            )
        return handler(action.input)
