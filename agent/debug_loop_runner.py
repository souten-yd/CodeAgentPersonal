from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.atlas_journal import AtlasJournal
from agent.debug_loop_schema import (
    AtlasDebugAttempt,
    AtlasDebugInput,
    AtlasDebugLoopState,
    AtlasDebugRootCauseCategory,
    _utc_now_iso,
)


def _model_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


class DebugLoopRunner:
    """Analyze Atlas pipeline failures and prepare journaled retry plans.

    This runner is intentionally limited to classification, summaries, and retry
    planning. It does not generate patches, apply changes, execute test commands,
    or add API/UI behavior.
    """

    def __init__(self, max_retries: int = 2, journal: AtlasJournal | None = None):
        self.max_retries = max(0, max_retries)
        self.journal = journal

    def analyze_failure(self, debug_input: AtlasDebugInput, retry_count: int = 0) -> AtlasDebugAttempt:
        category = self._classify_root_cause(debug_input)
        status = "proposed"
        retry_recommended = False
        retry_block_reason = ""

        if retry_count >= self.max_retries:
            status = "max_retries_reached"
            retry_block_reason = "Maximum debug retry count has been reached."
        elif category in {"policy_blocked", "approval_missing", "command_blocked"}:
            status = "retry_blocked"
            retry_block_reason = self._block_reason_for_category(category)
        elif category in {"syntax_error", "import_error", "test_failure", "executor_error", "unknown"}:
            status = "retry_allowed"
            retry_recommended = True
        elif category in {"timeout", "missing_file", "invalid_config"}:
            status = "retry_allowed"
            retry_recommended = True
        else:
            status = "retry_allowed"
            retry_recommended = True

        root_cause = self._build_root_cause(debug_input, category)
        proposed_fix = self._build_proposed_fix(category)
        reusable_lesson = self._build_reusable_lesson(category)
        metadata = dict(debug_input.metadata)
        metadata.update(
            {
                "debug_input_status": debug_input.status,
                "debug_input_returncode": debug_input.returncode,
                "source_error_summary": debug_input.error_summary,
            }
        )

        return AtlasDebugAttempt(
            attempt_id=f"atlas_debug_attempt_{uuid4().hex}",
            pool_id=debug_input.pool_id,
            item_id=debug_input.item_id,
            run_id=debug_input.run_id,
            source_type=debug_input.source_type,
            status=status,
            retry_count=retry_count,
            max_retries=self.max_retries,
            root_cause_category=category,
            error_summary=debug_input.error_summary or self._short_log(debug_input.stderr or debug_input.stdout),
            root_cause=root_cause,
            proposed_fix=proposed_fix,
            retry_recommended=retry_recommended,
            retry_block_reason=retry_block_reason,
            related_files=self._extract_related_files(debug_input),
            reusable_lesson=reusable_lesson,
            warnings=_as_list(debug_input.metadata.get("warnings")),
            errors=_as_list(debug_input.metadata.get("errors")),
            metadata=metadata,
        )

    def should_retry(self, attempt: AtlasDebugAttempt) -> bool:
        return (
            attempt.retry_recommended is True
            and attempt.status == "retry_allowed"
            and attempt.retry_count < attempt.max_retries
        )

    def create_loop_state(self, pool_id: str, item_id: str = "", run_id: str = "") -> AtlasDebugLoopState:
        return AtlasDebugLoopState(
            loop_id=f"atlas_debug_loop_{uuid4().hex}",
            pool_id=pool_id,
            item_id=item_id,
            run_id=run_id,
            max_retries=self.max_retries,
        )

    def add_attempt(self, loop_state: AtlasDebugLoopState, attempt: AtlasDebugAttempt) -> AtlasDebugLoopState:
        loop_state.attempts.append(attempt)
        loop_state.status = attempt.status
        loop_state.updated_at = _utc_now_iso()
        loop_state.warnings.extend(attempt.warnings)
        loop_state.errors.extend(attempt.errors)
        return loop_state

    def summarize_test_result(
        self,
        pool_id: str,
        item_id: str,
        run_id: str,
        test_result: Any,
    ) -> AtlasDebugInput:
        payload = _model_to_dict(test_result)
        status = str(payload.get("status", ""))
        command = str(payload.get("command", ""))
        errors = _as_list(payload.get("errors"))
        blocked_reason = str(payload.get("blocked_reason", ""))
        stderr = str(payload.get("stderr", ""))
        stdout = str(payload.get("stdout", ""))
        return AtlasDebugInput(
            pool_id=pool_id,
            item_id=item_id,
            run_id=run_id,
            source_type="test_command",
            error_summary=self._compact_summary(
                [f"test command {status}" if status else "test command result", blocked_reason, *errors, stderr, stdout]
            ),
            stdout=stdout,
            stderr=stderr,
            returncode=payload.get("returncode"),
            status=status,
            metadata={
                "command": command,
                "errors": errors,
                "warnings": _as_list(payload.get("warnings")),
                "blocked_reason": blocked_reason,
                "duration_seconds": payload.get("duration_seconds", 0.0),
            },
        )

    def summarize_batch_result(
        self,
        pool_id: str,
        item_id: str,
        run_id: str,
        batch_result: Any,
    ) -> AtlasDebugInput:
        results = _as_list(_get_value(batch_result, "results", []))
        selected = None
        for result in results:
            if _get_value(result, "status", "") in {"failed", "blocked", "timed_out"}:
                selected = result
                break
        if selected is not None:
            summary = self.summarize_test_result(pool_id, item_id, run_id, selected)
            summary.metadata["batch_counts"] = self._batch_counts(batch_result)
            return summary

        counts = self._batch_counts(batch_result)
        return AtlasDebugInput(
            pool_id=pool_id,
            item_id=item_id,
            run_id=run_id,
            source_type="test_command",
            error_summary=(
                "test command batch completed with "
                f"passed={counts['passed_count']} failed={counts['failed_count']} "
                f"blocked={counts['blocked_count']} timed_out={counts['timed_out_count']}"
            ),
            status="passed" if counts["failed_count"] == 0 and counts["blocked_count"] == 0 else "failed",
            metadata={"batch_counts": counts},
        )

    def summarize_safe_apply_result(
        self,
        pool_id: str,
        item_id: str,
        run_id: str,
        safe_apply_result: Any,
    ) -> AtlasDebugInput:
        payload = _model_to_dict(safe_apply_result)
        status = str(payload.get("status", ""))
        decision = str(payload.get("decision", ""))
        reasons = _as_list(payload.get("reasons"))
        categories = _as_list(payload.get("categories"))
        errors = _as_list(payload.get("errors"))
        warnings = _as_list(payload.get("warnings"))
        return AtlasDebugInput(
            pool_id=pool_id,
            item_id=item_id,
            run_id=run_id,
            source_type="safe_apply",
            error_summary=self._compact_summary([f"change application {status}", decision, *categories, *reasons, *errors]),
            status=status,
            metadata={
                "decision": decision,
                "reasons": reasons,
                "categories": categories,
                "errors": errors,
                "warnings": warnings,
                "applied": payload.get("applied", False),
                "simulated": payload.get("simulated", False),
                "executor_result": payload.get("executor_result", {}),
            },
        )

    def summarize_pipeline_state(self, pool_id: str, state: Any) -> AtlasDebugInput:
        payload = _model_to_dict(state)
        run_id = str(payload.get("run_id", ""))
        status = str(payload.get("status", ""))
        failed_item_ids = _as_list(payload.get("failed_item_ids"))
        blocked_item_ids = _as_list(payload.get("blocked_item_ids"))
        item_results = _as_list(payload.get("item_results"))
        latest_item = self._latest_problem_item(item_results) or (item_results[-1] if item_results else {})
        latest_payload = _model_to_dict(latest_item)
        item_id = str(latest_payload.get("item_id") or payload.get("current_item_id", ""))
        errors = _as_list(payload.get("errors")) + _as_list(latest_payload.get("errors"))
        warnings = _as_list(payload.get("warnings")) + _as_list(latest_payload.get("warnings"))
        return AtlasDebugInput(
            pool_id=pool_id,
            item_id=item_id,
            run_id=run_id,
            source_type="pipeline",
            error_summary=self._compact_summary(
                [f"pipeline {status}", f"failed_items={failed_item_ids}", f"blocked_items={blocked_item_ids}", *errors]
            ),
            status=status,
            metadata={
                "failed_item_ids": failed_item_ids,
                "blocked_item_ids": blocked_item_ids,
                "errors": errors,
                "warnings": warnings,
                "latest_item_result": latest_payload,
            },
        )

    def write_debug_notes(self, loop_state: AtlasDebugLoopState) -> Path | None:
        if self.journal is None:
            return None
        if not loop_state.run_id:
            loop_state.run_id = "debug_loop"
        path = self.journal.pipeline_run_dir(loop_state.pool_id, loop_state.run_id) / "debug_notes.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._render_debug_notes(loop_state), encoding="utf-8")
        latest = loop_state.attempts[-1] if loop_state.attempts else None
        self.journal.append_event(
            loop_state.pool_id,
            loop_state.run_id,
            {
                "event_id": f"atlas_debug_event_{uuid4().hex}",
                "run_id": loop_state.run_id,
                "event_type": "debug_attempt_recorded",
                "item_id": loop_state.item_id,
                "message": "Debug attempt recorded" if latest else "Debug loop notes written",
                "metadata": {
                    "loop_id": loop_state.loop_id,
                    "attempt_id": latest.attempt_id if latest else "",
                    "status": loop_state.status,
                    "root_cause_category": latest.root_cause_category if latest else "",
                },
                "created_at": _utc_now_iso(),
            },
        )
        return path

    def _classify_root_cause(self, debug_input: AtlasDebugInput) -> AtlasDebugRootCauseCategory:
        metadata = debug_input.metadata
        categories = " ".join(str(item) for item in _as_list(metadata.get("categories"))).lower()
        blocked_reason = str(metadata.get("blocked_reason", "")).lower()
        combined = "\n".join(
            [
                debug_input.error_summary,
                debug_input.stdout,
                debug_input.stderr,
                debug_input.status,
                categories,
                blocked_reason,
                " ".join(str(item) for item in _as_list(metadata.get("errors"))),
                " ".join(str(item) for item in _as_list(metadata.get("reasons"))),
            ]
        ).lower()

        if debug_input.source_type == "safe_apply" and debug_input.status == "blocked":
            if "approval_missing" in categories or "requires approval" in combined or "approval" in combined:
                return "approval_missing"
            return "policy_blocked"
        if "syntaxerror" in combined or "invalid syntax" in combined:
            return "syntax_error"
        if "modulenotfounderror" in combined or "importerror" in combined:
            return "import_error"
        if "not allowlisted" in combined or "not_allowlisted" in combined or "forbidden token" in combined or "blocked_reason" in combined:
            return "command_blocked"
        if "requires approval" in combined or "approval_missing" in combined or "approval" in combined:
            return "approval_missing"
        if "blocked by policy" in combined or "policy_blocked" in combined or "policy" in combined:
            return "policy_blocked"
        if "timed out" in combined or "timeoutexpired" in combined or debug_input.status == "timed_out":
            return "timeout"
        if "no such file" in combined or "filenotfounderror" in combined:
            return "missing_file"
        if "invalid config" in combined or "invalid_config" in combined:
            return "invalid_config"
        if "executor_error" in combined or "executor error" in combined:
            return "executor_error"
        if "failed" in combined or "assertionerror" in combined or "assert " in combined or "assert\n" in combined:
            return "test_failure"
        return "unknown"

    def _block_reason_for_category(self, category: str) -> str:
        if category == "approval_missing":
            return "Retry is blocked until the required approval is recorded."
        if category == "policy_blocked":
            return "Retry is blocked because the policy gate rejected the operation."
        if category == "command_blocked":
            return "Retry is blocked because the command safety gate rejected the command."
        return "Retry is blocked by a non-retriable condition."

    def _build_root_cause(self, debug_input: AtlasDebugInput, category: str) -> str:
        evidence = self._short_log(debug_input.stderr or debug_input.stdout or debug_input.error_summary)
        base = {
            "syntax_error": "The failure appears to be a syntax error in generated or edited code.",
            "import_error": "The failure appears to be caused by an import or missing module problem.",
            "test_failure": "The failure appears to be an assertion or test expectation mismatch.",
            "command_blocked": "The command was rejected by the allowlist or forbidden-token guard.",
            "timeout": "The operation appears to have exceeded its timeout.",
            "policy_blocked": "The operation was blocked by Atlas policy constraints.",
            "approval_missing": "The operation requires approval before retry can continue.",
            "executor_error": "The executor reported an internal execution failure.",
            "missing_file": "The failure indicates a referenced file or path is missing.",
            "invalid_config": "The failure indicates invalid configuration or incompatible options.",
            "unknown": "The failure cause is not yet specific enough to classify confidently.",
        }.get(category, "The failure needs additional investigation.")
        return f"{base} Evidence: {evidence}" if evidence else base

    def _build_proposed_fix(self, category: str) -> str:
        return {
            "syntax_error": "Inspect the syntax traceback and make the smallest code edit that restores valid Python syntax.",
            "import_error": "Verify the import path/module name and make the smallest import or dependency adjustment.",
            "test_failure": "Compare the assertion failure with expected behavior and make the smallest behavior or test-data fix.",
            "command_blocked": "Do not retry automatically; choose an allowlisted verification command or request explicit policy changes.",
            "timeout": "Review logs and reduce work size, increase explicit timeout policy, or isolate the slow step before retry.",
            "policy_blocked": "Do not bypass policy; re-plan toward a lower-risk allowed change or request approval where appropriate.",
            "approval_missing": "Record the required approval before any retry or application step.",
            "executor_error": "Inspect executor diagnostics and make the smallest configuration or input correction.",
            "missing_file": "Confirm the expected path and create, restore, or update references to the missing file.",
            "invalid_config": "Review configuration values and make the smallest valid configuration update.",
            "unknown": "ログを確認して最小修正案を作る。",
        }.get(category, "Review the failure log and prepare the smallest safe correction.")

    def _build_reusable_lesson(self, category: str) -> str:
        return {
            "syntax_error": "Run syntax checks before planning another apply attempt.",
            "import_error": "Confirm imports are available in the target runtime before retrying.",
            "test_failure": "Use the failing assertion as the acceptance criterion for the next minimal fix.",
            "command_blocked": "Keep verification commands inside the TestCommandRunner allowlist.",
            "timeout": "Keep retry plans bounded and timeout-aware.",
            "policy_blocked": "Policy blocks require re-planning, not automatic bypass.",
            "approval_missing": "Approval-gated actions must wait for explicit approval.",
            "executor_error": "Executor diagnostics should be preserved with the retry plan.",
            "missing_file": "Validate file references before retrying pipeline execution.",
            "invalid_config": "Configuration validation should precede retry planning.",
            "unknown": "Unclassified failures should be summarized before expanding the fix scope.",
        }.get(category, "Capture the smallest useful lesson for future retries.")

    def _extract_related_files(self, debug_input: AtlasDebugInput) -> list[str]:
        related = debug_input.metadata.get("related_files", [])
        return [str(item) for item in _as_list(related) if str(item)]

    def _batch_counts(self, batch_result: Any) -> dict[str, int]:
        return {
            "passed_count": int(_get_value(batch_result, "passed_count", 0) or 0),
            "failed_count": int(_get_value(batch_result, "failed_count", 0) or 0),
            "blocked_count": int(_get_value(batch_result, "blocked_count", 0) or 0),
            "timed_out_count": int(_get_value(batch_result, "timed_out_count", 0) or 0),
            "skipped_count": int(_get_value(batch_result, "skipped_count", 0) or 0),
        }

    def _latest_problem_item(self, item_results: list[Any]) -> Any | None:
        for item in reversed(item_results):
            if _get_value(item, "status", "") in {"failed", "blocked"}:
                return item
        return None

    def _compact_summary(self, parts: list[Any], limit: int = 240) -> str:
        text = " | ".join(str(part).strip() for part in parts if str(part).strip())
        return self._short_log(text, limit=limit)

    def _short_log(self, text: str, limit: int = 240) -> str:
        normalized = " ".join(str(text).split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 3]}..."

    def _render_debug_notes(self, loop_state: AtlasDebugLoopState) -> str:
        latest = loop_state.attempts[-1] if loop_state.attempts else None
        rows = [
            "| Attempt ID | Source | Status | Retry | Category | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for attempt in loop_state.attempts:
            rows.append(
                "| {attempt_id} | {source} | {status} | {retry_count}/{max_retries} | {category} | {summary} |".format(
                    attempt_id=self._md_cell(attempt.attempt_id),
                    source=attempt.source_type,
                    status=attempt.status,
                    retry_count=attempt.retry_count,
                    max_retries=attempt.max_retries,
                    category=attempt.root_cause_category,
                    summary=self._md_cell(attempt.error_summary),
                )
            )
        return f"""# Atlas Debug Notes

- Loop ID: {loop_state.loop_id}
- Pool ID: {loop_state.pool_id}
- Item ID: {loop_state.item_id}
- Run ID: {loop_state.run_id}
- Status: {loop_state.status}

## Attempts

{chr(10).join(rows)}

## Latest Root Cause

{latest.root_cause if latest else 'None'}

## Proposed Fix

{latest.proposed_fix if latest else 'None'}

## Reusable Lesson

{latest.reusable_lesson if latest else 'None'}

## Warnings

{self._markdown_list(loop_state.warnings)}

## Errors

{self._markdown_list(loop_state.errors)}
"""

    def _markdown_list(self, values: list[str]) -> str:
        if not values:
            return "- None"
        return "\n".join(f"- {value}" for value in values)

    def _md_cell(self, value: str) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
