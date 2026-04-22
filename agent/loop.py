from __future__ import annotations

from agent.context_builder import ContextBuilder
from agent.evaluator import Evaluator
from agent.executor import Executor
from agent.memory import MemoryStore
from agent.planner import Planner
from agent.types import Evaluation, ToolResult


class AgentLoop:
    """Planner/Executor/Evaluator を疎結合で接続する最小ループ。"""

    def __init__(
        self,
        planner: Planner,
        executor: Executor,
        evaluator: Evaluator,
        context_builder: ContextBuilder,
        memory: MemoryStore,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.evaluator = evaluator
        self.context_builder = context_builder
        self.memory = memory

    def run_once(self, objective: str, runtime_state: dict) -> tuple[Evaluation, list[ToolResult]]:
        context = self.context_builder.build(objective=objective, runtime_state=runtime_state)
        plan = self.planner.create_plan(objective=objective, context=context)

        history: list[ToolResult] = []
        action = self.planner.choose_next_action(plan=plan, history=history)
        if action is not None:
            history.append(self.executor.execute(action))

        evaluation = self.evaluator.evaluate(plan=plan, history=history)
        return evaluation, history
