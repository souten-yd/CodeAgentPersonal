from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Plan:
    """Planner が作成する実行計画。"""

    goal: str
    steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Action:
    """Executor に渡す単一アクション。"""

    id: str
    tool: str
    input: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass(slots=True)
class ToolResult:
    """ツール実行結果。"""

    action_id: str
    success: bool
    output: Any = None
    error: str | None = None


@dataclass(slots=True)
class Evaluation:
    """Evaluator の判定結果。"""

    passed: bool
    feedback: str = ""
    done: bool = False
    next_action: Action | None = None
