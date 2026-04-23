from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any, Literal

from agent.types import Action, ToolResult

ErrorType = Literal[
    "timeout",
    "arg",
    "runtime",
    "not_found",
    "json_output_failed",
    "target_closed",
    "edit_old_str_not_found",
    "command_not_found",
    "unknown",
]


class Executor:
    """Action 実行インターフェース + エラーポリシー."""

    ERROR_CLASSIFICATION_TABLE: dict[str, dict[str, Any]] = {
        "json_output_failed": {
            "patterns": ("json出力失敗", "json parse", "json形式", "json only", "expecting value"),
            "max_retries": 2,
            "fallback_action": "prompt_json_minimal_and_replan",
            "abort_condition": "同一分類が連続2回以上",
        },
        "target_closed": {
            "patterns": ("targetclosederror", "target closed", "browser has been closed"),
            "max_retries": 1,
            "fallback_action": "switch_run_browser_to_static_html_validation",
            "abort_condition": "同一分類が連続2回以上",
        },
        "edit_old_str_not_found": {
            "patterns": ("old_str not found",),
            "max_retries": 1,
            "fallback_action": "reload_file_and_apply_small_patch",
            "abort_condition": "同一分類が連続2回以上",
        },
        "command_not_found": {
            "patterns": ("command not found", "not recognized as an internal or external command"),
            "max_retries": 1,
            "fallback_action": "inspect_runtime_and_use_alternative_tool",
            "abort_condition": "同一分類が連続2回以上",
        },
        "timeout": {
            "patterns": ("timeout", "timed out", "deadline exceeded"),
            "max_retries": 2,
            "fallback_action": "split_task_or_reduce_scope",
            "abort_condition": "同一分類が連続2回以上",
        },
        "not_found": {
            "patterns": ("not found", "unknown tool", "no such tool"),
            "max_retries": 0,
            "fallback_action": "replan_with_supported_toolset",
            "abort_condition": "初回から同一ツール再実行禁止",
        },
        "arg": {
            "patterns": ("invalid", "missing required", "bad argument", "schema"),
            "max_retries": 1,
            "fallback_action": "correct_arguments_and_retry",
            "abort_condition": "同一分類が連続2回以上",
        },
        "runtime": {
            "patterns": tuple(),
            "max_retries": 1,
            "fallback_action": "replan_task_level",
            "abort_condition": "同一分類が連続2回以上",
        },
        "unknown": {
            "patterns": tuple(),
            "max_retries": 0,
            "fallback_action": "replan_task_level",
            "abort_condition": "原因不明",
        },
    }

    FALLBACK_TRANSITIONS_BY_TOOL: dict[str, dict[str, str]] = {
        "run_browser": {
            "target_closed": "static_html_validation",
            "timeout": "static_html_validation",
            "runtime": "static_html_validation",
        },
        "edit_file": {
            "edit_old_str_not_found": "reload_then_small_patch",
            "arg": "reload_then_small_patch",
            "runtime": "reload_then_small_patch",
        },
    }

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
                classification_streak=1,
                transition_to="replan_task_level",
                max_retries_for_error=0,
            )

        current = action
        retry_count = 0
        seen_retry_fingerprints = {original_fingerprint}
        last_error_type: ErrorType | None = None
        same_error_streak = 0

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
                    classification_streak=0,
                    transition_to="none",
                    max_retries_for_error=self.max_retries,
                )

            err_type = self.classify_error(result.error)
            if err_type == last_error_type:
                same_error_streak += 1
            else:
                same_error_streak = 1
            last_error_type = err_type

            short_reason = self._short_reason(err_type, result.error)
            classification_policy = self.ERROR_CLASSIFICATION_TABLE.get(err_type, self.ERROR_CLASSIFICATION_TABLE["runtime"])
            max_retries_for_error = min(self.max_retries, int(classification_policy.get("max_retries", self.max_retries)))

            if same_error_streak >= 2:
                transition = self._resolve_transition(action.tool, err_type)
                self._last_failed_fingerprint = original_fingerprint
                return self._policy_fail(
                    action=action,
                    error_type=err_type,
                    short_reason=f"{short_reason} / 同一分類連続のため同一ツール再実行禁止",
                    raw_error=result.error,
                    retry_count=retry_count,
                    replan_recommended=True,
                    blocked_repeat=True,
                    classification_streak=same_error_streak,
                    transition_to=transition,
                    max_retries_for_error=max_retries_for_error,
                )

            if retry_count >= max_retries_for_error:
                transition = self._resolve_transition(action.tool, err_type)
                self._last_failed_fingerprint = original_fingerprint
                return self._policy_fail(
                    action=action,
                    error_type=err_type,
                    short_reason=short_reason,
                    raw_error=result.error,
                    retry_count=retry_count,
                    replan_recommended=True,
                    blocked_repeat=False,
                    classification_streak=same_error_streak,
                    transition_to=transition,
                    max_retries_for_error=max_retries_for_error,
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
                    classification_streak=same_error_streak,
                    transition_to="replan_task_level",
                    max_retries_for_error=max_retries_for_error,
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
        if not msg:
            return "unknown"

        for error_type, conf in self.ERROR_CLASSIFICATION_TABLE.items():
            patterns = conf.get("patterns") or ()
            if any(p in msg for p in patterns):
                return error_type  # type: ignore[return-value]

        return "runtime"

    def _resolve_transition(self, tool: str, error_type: ErrorType) -> str:
        by_tool = self.FALLBACK_TRANSITIONS_BY_TOOL.get(tool, {})
        return by_tool.get(error_type, self.ERROR_CLASSIFICATION_TABLE.get(error_type, {}).get("fallback_action", "replan_task_level"))

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
        classification_streak: int,
        transition_to: str,
        max_retries_for_error: int,
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
            classification_streak=classification_streak,
            transition_to=transition_to,
            max_retries_for_error=max_retries_for_error,
        )

    def _attach_policy(
        self,
        result: ToolResult,
        error_type: ErrorType,
        short_reason: str,
        retry_count: int,
        replan_recommended: bool,
        blocked_repeat: bool,
        classification_streak: int,
        transition_to: str,
        max_retries_for_error: int,
    ) -> ToolResult:
        base_output: dict[str, Any]
        if isinstance(result.output, dict):
            base_output = dict(result.output)
        else:
            base_output = {"value": result.output}

        classification_policy = self.ERROR_CLASSIFICATION_TABLE.get(error_type, self.ERROR_CLASSIFICATION_TABLE["runtime"])
        remaining_retries = max(0, int(max_retries_for_error) - int(retry_count))
        base_output["_policy"] = {
            "error_type": error_type,
            "short_reason": short_reason,
            "retry_count": retry_count,
            "max_retries": self.max_retries,
            "max_retries_for_error": max_retries_for_error,
            "remaining_retries": remaining_retries,
            "replan_recommended": replan_recommended,
            "blocked_repeat": blocked_repeat,
            "classification_result": error_type,
            "classification_streak": classification_streak,
            "transition_to": transition_to,
            "fallback_action": classification_policy.get("fallback_action"),
            "abort_condition": classification_policy.get("abort_condition"),
            "task_execution_log": {
                "classification_result": error_type,
                "transition_to": transition_to,
                "remaining_retries": remaining_retries,
            },
        }
        result.output = base_output
        return result
