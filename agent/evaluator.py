from __future__ import annotations

from agent.types import Evaluation, Plan, ToolResult


class Evaluator:
    """実行結果を層別 DoD で評価し、必要時は最小層のみ再計画を指示する。"""

    def evaluate(self, plan: Plan, history: list[ToolResult]) -> Evaluation:
        if not history:
            return Evaluation(passed=False, feedback="not_started", done=False)

        latest = history[-1]
        policy = self._extract_policy(latest)

        if latest.success:
            self._refresh_layer_status(plan)
            if self._program_done(plan):
                return Evaluation(passed=True, feedback="program_done", done=True)
            return Evaluation(passed=True, feedback="task_succeeded", done=False)

        short_reason = policy.get("short_reason") or (latest.error or "execution failed")
        blocked_repeat = bool(policy.get("blocked_repeat"))
        replan_recommended = bool(policy.get("replan_recommended"))
        replan_level = self._infer_replan_level(policy=policy, blocked_repeat=blocked_repeat, replan_recommended=replan_recommended)

        retry_count = int(policy.get("retry_count", 0))
        max_retries = int(policy.get("max_retries", 0))
        if replan_level != "none":
            return Evaluation(
                passed=False,
                feedback=f"replan_{replan_level}: {short_reason}",
                done=False,
                replan_level=replan_level,
            )

        return Evaluation(
            passed=False,
            feedback=f"retry_pending({retry_count}/{max_retries}): {short_reason}",
            done=False,
            replan_level="none",
        )

    def _infer_replan_level(self, policy: dict, blocked_repeat: bool, replan_recommended: bool) -> str:
        if not (blocked_repeat or replan_recommended):
            return "none"
        level = str(policy.get("replan_level", "task")).lower().strip()
        if level in {"task", "epic", "program"}:
            return level
        return "task"

    def _refresh_layer_status(self, plan: Plan) -> None:
        for epic in plan.epics:
            epic_done = bool(epic.tasks) and all(task.definition_of_done.satisfied for task in epic.tasks)
            epic.definition_of_done.satisfied = epic_done
            epic.status = "done" if epic_done else "in_progress"
        if plan.program is None:
            return
        program_done = bool(plan.epics) and all(epic.definition_of_done.satisfied for epic in plan.epics)
        plan.program.definition_of_done.satisfied = program_done
        plan.program.status = "done" if program_done else "in_progress"

    def _program_done(self, plan: Plan) -> bool:
        if plan.program is None:
            return False
        return plan.program.definition_of_done.satisfied

    def _extract_policy(self, result: ToolResult) -> dict:
        if not isinstance(result.output, dict):
            return {}
        policy = result.output.get("_policy")
        if isinstance(policy, dict):
            return policy
        return {}
