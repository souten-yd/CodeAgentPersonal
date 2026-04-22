from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ReplanLevel = Literal["none", "task", "epic", "program"]


@dataclass(slots=True)
class DefinitionOfDone:
    """各計画階層の完了条件。"""

    checks: list[str] = field(default_factory=list)
    satisfied: bool = False
    notes: str = ""


@dataclass(slots=True)
class ExecutableTask:
    """Executor が直接処理できる最小タスク。"""

    id: str
    title: str
    action: str
    input: dict[str, Any] = field(default_factory=dict)
    definition_of_done: DefinitionOfDone = field(default_factory=DefinitionOfDone)
    status: Literal["pending", "in_progress", "done", "failed"] = "pending"


@dataclass(slots=True)
class EpicPlan:
    """機能単位の計画。"""

    id: str
    title: str
    dependencies: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    definition_of_done: DefinitionOfDone = field(default_factory=DefinitionOfDone)
    tasks: list[ExecutableTask] = field(default_factory=list)
    status: Literal["pending", "in_progress", "done", "failed"] = "pending"


@dataclass(slots=True)
class ProgramPlan:
    """全体方針レベルの計画。"""

    objective: str
    deliverables: list[str] = field(default_factory=list)
    non_functional_requirements: list[str] = field(default_factory=list)
    definition_of_done: DefinitionOfDone = field(default_factory=DefinitionOfDone)
    status: Literal["pending", "in_progress", "done", "failed"] = "pending"


@dataclass(slots=True)
class Plan:
    """Planner が作成する実行計画。"""

    goal: str
    steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    program: ProgramPlan | None = None
    epics: list[EpicPlan] = field(default_factory=list)


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
    replan_level: ReplanLevel = "none"
