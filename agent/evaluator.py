from __future__ import annotations

from agent.types import Evaluation, Plan, ToolResult


class Evaluator:
    """実行結果の評価インターフェース + エラーポリシー反映。"""

    def evaluate(self, plan: Plan, history: list[ToolResult]) -> Evaluation:
        if not history:
            return Evaluation(passed=False, feedback="not_started", done=False)

        latest = history[-1]
        policy = self._extract_policy(latest)

        if latest.success:
            return Evaluation(
                passed=True,
                feedback="step_succeeded",
                done=False,
            )

        short_reason = policy.get("short_reason") or (latest.error or "execution failed")
        replan_recommended = bool(policy.get("replan_recommended"))
        blocked_repeat = bool(policy.get("blocked_repeat"))

        if replan_recommended or blocked_repeat:
            return Evaluation(
                passed=False,
                feedback=f"unrecoverable: {short_reason}",
                done=False,
            )

        retry_count = int(policy.get("retry_count", 0))
        max_retries = int(policy.get("max_retries", 0))
        return Evaluation(
            passed=False,
            feedback=f"retry_pending({retry_count}/{max_retries}): {short_reason}",
            done=False,
        )

    def _extract_policy(self, result: ToolResult) -> dict:
        if not isinstance(result.output, dict):
            return {}
        policy = result.output.get("_policy")
        if isinstance(policy, dict):
            return policy
        return {}
