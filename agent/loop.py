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
        history: list[ToolResult] = []
        loop_limit = max(1, int(runtime_state.get("loop_limit", 10)))
        evaluation = Evaluation(passed=False, feedback="not_started", done=False)

        context = self.context_builder.build(objective=objective, runtime_state=runtime_state)
        plan = self.planner.create_plan(objective=objective, context=context)

        iteration = 0
        while iteration < loop_limit:
            action = self.planner.choose_next_action(plan=plan, history=history)
            if action is None:
                evaluation = self.evaluator.evaluate(plan=plan, history=history)
                self._update_memory(objective=objective, history=history, evaluation=evaluation, plan=plan)
                if evaluation.done:
                    break
                if self._is_unrecoverable(evaluation):
                    context = self.context_builder.build(objective=objective, runtime_state=runtime_state)
                    plan = self.planner.create_plan(objective=objective, context=context)
                    continue
                break

            history.append(self.executor.execute(action))
            evaluation = self.evaluator.evaluate(plan=plan, history=history)
            self._update_memory(objective=objective, history=history, evaluation=evaluation, plan=plan)
            iteration += 1

            if evaluation.done:
                break
            if self._is_unrecoverable(evaluation):
                context = self.context_builder.build(objective=objective, runtime_state=runtime_state)
                plan = self.planner.create_plan(objective=objective, context=context)

        return evaluation, history

    def _is_unrecoverable(self, evaluation: Evaluation) -> bool:
        feedback = (evaluation.feedback or "").lower()
        return "回復不能" in evaluation.feedback or "unrecoverable" in feedback

    def _update_memory(self, objective: str, history: list[ToolResult], evaluation: Evaluation, plan) -> None:
        payload = {
            "objective": objective,
            "plan": plan,
            "history": list(history),
            "evaluation": evaluation,
        }
        update = getattr(self.memory, "update", None)
        if callable(update):
            update(payload)
            return
        self.memory.save(payload)
