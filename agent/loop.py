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
                if history:
                    self._store_step_memory(history[-1], evaluation)
                self._update_memory(objective=objective, history=history, evaluation=evaluation, plan=plan)
                if evaluation.done:
                    break
                if self._is_unrecoverable(evaluation):
                    replan_minimal = getattr(self.planner, "replan_minimal", None)
                    if callable(replan_minimal):
                        plan = replan_minimal(plan=plan, level=evaluation.replan_level, failed_action_id=history[-1].action_id if history else None)
                    else:
                        context = self.context_builder.build(objective=objective, runtime_state=runtime_state)
                        plan = self.planner.create_plan(objective=objective, context=context)
                    continue
                break

            result = self.executor.execute(action)
            history.append(result)
            mark_task_result = getattr(self.planner, "mark_task_result", None)
            if callable(mark_task_result):
                mark_task_result(plan, result)
            evaluation = self.evaluator.evaluate(plan=plan, history=history)
            self._store_step_memory(history[-1], evaluation)
            self._update_memory(objective=objective, history=history, evaluation=evaluation, plan=plan)
            iteration += 1

            if evaluation.done:
                break
            if self._is_unrecoverable(evaluation):
                replan_minimal = getattr(self.planner, "replan_minimal", None)
                if callable(replan_minimal):
                    plan = replan_minimal(plan=plan, level=evaluation.replan_level, failed_action_id=history[-1].action_id if history else None)
                else:
                    context = self.context_builder.build(objective=objective, runtime_state=runtime_state)
                    plan = self.planner.create_plan(objective=objective, context=context)

        if evaluation.done:
            self._promote_job_summary(objective=objective, history=history, evaluation=evaluation)

        return evaluation, history


    def _store_step_memory(self, result: ToolResult, evaluation: Evaluation) -> None:
        store_memory = getattr(self.memory, "store_memory", None)
        if not callable(store_memory):
            return
        store_memory(
            key=f"step:{result.action_id}",
            value={"result": result, "evaluation": evaluation},
            scope="short",
        )

    def _promote_job_summary(self, objective: str, history: list[ToolResult], evaluation: Evaluation) -> None:
        store_memory = getattr(self.memory, "store_memory", None)
        if not callable(store_memory):
            return

        last = history[-1] if history else None
        summary = {
            "objective": objective,
            "steps": len(history),
            "final_feedback": evaluation.feedback,
            "passed": evaluation.passed,
            "last_result": last,
        }
        store_memory(key=f"job_summary:{objective[:80]}", value=summary, scope="long")

    def _is_unrecoverable(self, evaluation: Evaluation) -> bool:
        if evaluation.replan_level in {"task", "epic", "program"}:
            return True
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
