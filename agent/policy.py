from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from agent.safety import AutoStopDecision, HumanGateDecision, detect_human_gate
from agent.types import Action, Evaluation, ToolResult


@dataclass(slots=True)
class ExecutionBudget:
    """実行予算（ループ/コマンド/変更ファイル/トークン）。"""

    max_loops: int = 10
    max_commands: int = 20
    max_changed_files: int = 20
    max_tokens: int = 120_000


@dataclass(slots=True)
class CapabilityPolicy:
    """実行可能な能力の制約。"""

    allowed_tools: set[str] = field(default_factory=set)
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_operations: set[str] = field(default_factory=set)


@dataclass(slots=True)
class ExecutionPolicyState:
    loops: int = 0
    commands: int = 0
    changed_files: set[str] = field(default_factory=set)
    tokens_used: int = 0
    stagnation_count: int = 0
    evaluation_regressions: int = 0
    previous_feedback: str = ""
    previous_passed: bool | None = None


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""


class ExecutionPolicy:
    """実行ポリシーを中央管理するオーケストレータ。"""

    def __init__(
        self,
        budget: ExecutionBudget | None = None,
        capability: CapabilityPolicy | None = None,
    ) -> None:
        self.budget = budget or ExecutionBudget()
        self.capability = capability or CapabilityPolicy()
        self.state = ExecutionPolicyState()

    def check_action(self, action: Action) -> PolicyDecision:
        if self.capability.allowed_tools and action.tool not in self.capability.allowed_tools:
            return PolicyDecision(False, f"tool_not_allowed:{action.tool}")

        path = str(action.input.get("path", "")).strip()
        if path and self.capability.allowed_paths and not self._is_path_allowed(path):
            return PolicyDecision(False, f"path_not_allowed:{path}")

        payload = f"{action.tool}\n{action.input}".lower()
        for forbidden in self.capability.forbidden_operations:
            if forbidden.lower() in payload:
                return PolicyDecision(False, f"forbidden_operation:{forbidden}")

        return PolicyDecision(True)

    def assess_human_gate(self, action: Action) -> HumanGateDecision:
        return detect_human_gate(action)

    def register_iteration(self) -> None:
        self.state.loops += 1

    def register_result(self, result: ToolResult) -> None:
        self.state.commands += 1
        output = result.output if isinstance(result.output, dict) else {}
        token_hint = int(output.get("tokens_used", 0) or 0)
        self.state.tokens_used += max(0, token_hint)

        changed = output.get("changed_files", [])
        if isinstance(changed, list):
            for item in changed:
                self.state.changed_files.add(str(item))

    def evaluate_autostop(self, evaluation: Evaluation) -> AutoStopDecision:
        budget_stop = self._check_budget_exhausted()
        if budget_stop.should_stop:
            return budget_stop

        feedback = (evaluation.feedback or "").strip().lower()
        if feedback and feedback == self.state.previous_feedback:
            self.state.stagnation_count += 1
        else:
            self.state.stagnation_count = 0

        if self.state.previous_passed is True and evaluation.passed is False:
            self.state.evaluation_regressions += 1
        elif evaluation.passed:
            self.state.evaluation_regressions = 0

        self.state.previous_feedback = feedback
        self.state.previous_passed = evaluation.passed

        if self.state.loops >= self.budget.max_loops:
            return AutoStopDecision(
                should_stop=True,
                stop_type="iteration_limit",
                reason=f"max loops reached ({self.state.loops}/{self.budget.max_loops})",
                ui_notice="反復上限に到達したため自動停止しました。",
            )

        if self.state.stagnation_count >= 2:
            return AutoStopDecision(
                should_stop=True,
                stop_type="stagnation",
                reason="evaluation feedback stagnated for 3 cycles",
                ui_notice="進捗停滞を検知したため自動停止しました。",
            )

        if self.state.evaluation_regressions >= 2:
            return AutoStopDecision(
                should_stop=True,
                stop_type="evaluation_regression",
                reason="evaluation quality regressed repeatedly",
                ui_notice="評価悪化が続いたため自動停止しました。",
            )

        return AutoStopDecision(should_stop=False)

    def _check_budget_exhausted(self) -> AutoStopDecision:
        if self.state.commands >= self.budget.max_commands:
            return AutoStopDecision(
                should_stop=True,
                stop_type="budget_exhausted",
                reason=f"command budget exhausted ({self.state.commands}/{self.budget.max_commands})",
                ui_notice="コマンド実行予算を使い切ったため停止しました。",
            )
        if len(self.state.changed_files) >= self.budget.max_changed_files:
            return AutoStopDecision(
                should_stop=True,
                stop_type="budget_exhausted",
                reason=(
                    f"changed file budget exhausted "
                    f"({len(self.state.changed_files)}/{self.budget.max_changed_files})"
                ),
                ui_notice="変更ファイル数の上限に到達したため停止しました。",
            )
        if self.state.tokens_used >= self.budget.max_tokens:
            return AutoStopDecision(
                should_stop=True,
                stop_type="budget_exhausted",
                reason=f"token budget exhausted ({self.state.tokens_used}/{self.budget.max_tokens})",
                ui_notice="トークン予算を使い切ったため停止しました。",
            )
        return AutoStopDecision(should_stop=False)

    def _is_path_allowed(self, path: str) -> bool:
        candidate = PurePosixPath(path)
        normalized = str(candidate)
        for allowed in self.capability.allowed_paths:
            base = str(PurePosixPath(allowed))
            if normalized == base or normalized.startswith(f"{base}/"):
                return True
        return False
