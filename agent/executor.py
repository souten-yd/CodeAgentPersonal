from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any, Literal

from agent.types import Action, ToolResult

ErrorType = Literal["timeout", "arg", "runtime", "not_found", "unknown"]


class Executor:
    """Action 実行インターフェース + エラーポリシー."""

    def __init__(self, max_retries: int = 2) -> None:
        # 追加再試行回数。合計試行回数は max_retries + 1。
        self.max_retries = max(0, int(max_retries))
        self._last_failed_fingerprint: str | None = None

    def execute(self, action: Action) -> ToolResult:
        original_fingerprint = self._fingerprint(action)
        if self._last_failed_fingerprint == original_fingerprint:
            return self._policy_fail(
                action=action,
                error_type="arg",
                short_reason="同一 action+args の失敗反復をブロック",
                raw_error="blocked repeated action with identical args",
                retry_count=0,
                replan_recommended=True,
                blocked_repeat=True,
            )

        current = action
        retry_count = 0
        last_failure: ToolResult | None = None
        seen_retry_fingerprints = {original_fingerprint}

        while True:
            result = self._execute_once(current)
            if result.success:
                self._last_failed_fingerprint = None
                return self._attach_policy(
                    result=result,
                    error_type="unknown",
                    short_reason="ok",
                    retry_count=retry_count,
                    replan_recommended=False,
                    blocked_repeat=False,
                )

            last_failure = result
            err_type = self.classify_error(result.error)
            short_reason = self._short_reason(err_type, result.error)

            if retry_count >= self.max_retries:
                self._last_failed_fingerprint = original_fingerprint
                return self._policy_fail(
                    action=action,
                    error_type=err_type,
                    short_reason=short_reason,
                    raw_error=result.error,
                    retry_count=retry_count,
                    replan_recommended=True,
                    blocked_repeat=False,
                )

            retry_count += 1
            current = self._build_retry_action(current, retry_count, result)
            retry_fingerprint = self._fingerprint(current)
            if retry_fingerprint in seen_retry_fingerprints:
                self._last_failed_fingerprint = original_fingerprint
                return self._policy_fail(
                    action=action,
                    error_type="arg",
                    short_reason="再試行時の引数変更が無く中断",
                    raw_error="retry args were not changed",
                    retry_count=retry_count,
                    replan_recommended=True,
                    blocked_repeat=True,
                )
            seen_retry_fingerprints.add(retry_fingerprint)

    def _execute_once(self, action: Action) -> ToolResult:
        raise NotImplementedError

    def _build_retry_action(self, action: Action, retry_count: int, last_result: ToolResult) -> Action:
        updated_input = copy.deepcopy(action.input)
        retry_meta = updated_input.get("_retry", {})
        if not isinstance(retry_meta, dict):
            retry_meta = {}
        retry_meta.update(
            {
                "count": retry_count,
                "prev_error": (last_result.error or "")[:120],
                "policy": "mutate_args_before_retry",
            }
        )
        updated_input["_retry"] = retry_meta
        return replace(action, input=updated_input)

    def classify_error(self, error: str | None) -> ErrorType:
        msg = (error or "").lower()
        if any(t in msg for t in ("timeout", "timed out", "deadline exceeded")):
            return "timeout"
        if any(t in msg for t in ("not found", "unknown tool", "no such tool")):
            return "not_found"
        if any(t in msg for t in ("invalid", "missing required", "bad argument", "schema")):
            return "arg"
        if msg:
            return "runtime"
        return "unknown"

    def _short_reason(self, error_type: ErrorType, error: str | None) -> str:
        detail = (error or "").strip()
        detail = detail[:80]
        if detail:
            return f"{error_type}: {detail}"
        return f"{error_type}: execution failed"

    def _fingerprint(self, action: Action) -> str:
        try:
            normalized = json.dumps(action.input, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            normalized = repr(action.input)
        return f"{action.tool}|{normalized}"

    def _policy_fail(
        self,
        action: Action,
        error_type: ErrorType,
        short_reason: str,
        raw_error: str | None,
        retry_count: int,
        replan_recommended: bool,
        blocked_repeat: bool,
    ) -> ToolResult:
        result = ToolResult(
            action_id=action.id,
            success=False,
            error=raw_error or short_reason,
        )
        return self._attach_policy(
            result=result,
            error_type=error_type,
            short_reason=short_reason,
            retry_count=retry_count,
            replan_recommended=replan_recommended,
            blocked_repeat=blocked_repeat,
        )

    def _attach_policy(
        self,
        result: ToolResult,
        error_type: ErrorType,
        short_reason: str,
        retry_count: int,
        replan_recommended: bool,
        blocked_repeat: bool,
    ) -> ToolResult:
        base_output: dict[str, Any]
        if isinstance(result.output, dict):
            base_output = dict(result.output)
        else:
            base_output = {"value": result.output}
        base_output["_policy"] = {
            "error_type": error_type,
            "short_reason": short_reason,
            "retry_count": retry_count,
            "max_retries": self.max_retries,
            "replan_recommended": replan_recommended,
            "blocked_repeat": blocked_repeat,
        }
        result.output = base_output
        return result
