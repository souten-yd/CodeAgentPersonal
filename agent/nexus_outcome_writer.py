from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.atlas_journal import AtlasJournal
from agent.atlas_nexus_research_schema import AtlasNexusContextPack
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunState
from agent.atlas_plan_pool_schema import AtlasPlanPool
from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyResult
from agent.debug_loop_schema import AtlasDebugAttempt, AtlasDebugLoopState
from agent.nexus_outcome_schema import AtlasNexusOutcome, AtlasNexusOutcomeWriteResult, _utc_now_iso


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value and value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


class NexusOutcomeWriter:
    def __init__(
        self,
        nexus_client: object | None = None,
        journal: AtlasJournal | None = None,
    ):
        self.nexus_client = nexus_client
        self.journal = journal

    def write_outcome(self, outcome: AtlasNexusOutcome) -> AtlasNexusOutcomeWriteResult:
        json_path, markdown_path = self.save_to_journal(outcome)
        nexus_saved, nexus_record_id, nexus_warnings = self.save_to_nexus(outcome)
        journal_saved = bool(json_path and markdown_path)

        warnings: list[str] = []
        errors: list[str] = []
        if not journal_saved:
            warnings.append("journal_unavailable")
        warnings.extend(nexus_warnings)
        warnings.extend(outcome.warnings)
        errors.extend(outcome.errors)

        if journal_saved and nexus_saved:
            status = "saved"
        elif journal_saved or nexus_saved:
            status = "saved_with_warnings"
        else:
            status = "skipped" if self.journal is None and self.nexus_client is None else "failed"

        outcome.status = status
        outcome.updated_at = _utc_now_iso()
        outcome.warnings = _unique(warnings)
        outcome.errors = _unique(errors)
        if journal_saved:
            json_path, markdown_path = self.save_to_journal(outcome)

        return AtlasNexusOutcomeWriteResult(
            outcome_id=outcome.outcome_id,
            status=status,
            nexus_saved=nexus_saved,
            journal_saved=journal_saved,
            nexus_record_id=nexus_record_id,
            json_path=json_path,
            markdown_path=markdown_path,
            warnings=outcome.warnings,
            errors=outcome.errors,
            metadata={"project": outcome.project, "pool_id": outcome.pool_id, "source": outcome.source},
        )

    def save_to_journal(self, outcome: AtlasNexusOutcome) -> tuple[str, str]:
        if self.journal is None:
            return "", ""

        base_dir = self.journal.plan_pool_dir(outcome.pool_id) if outcome.pool_id else self.journal.workspace_dir()
        outcome_dir = base_dir / "outcomes"
        outcome_dir.mkdir(parents=True, exist_ok=True)
        json_path = outcome_dir / f"{outcome.outcome_id}.json"
        markdown_path = outcome_dir / f"{outcome.outcome_id}.md"

        json_path.write_text(json.dumps(_model_dump(outcome), ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(self._outcome_markdown(outcome), encoding="utf-8")
        return str(json_path), str(markdown_path)

    def save_to_nexus(self, outcome: AtlasNexusOutcome) -> tuple[bool, str, list[str]]:
        if self.nexus_client is None:
            return False, "", ["nexus_client_unavailable"]

        outcome_dict = _model_dump(outcome)
        for method_name in ["save_outcome", "save_memory", "add_memory"]:
            method = getattr(self.nexus_client, method_name, None)
            if method is None:
                continue
            try:
                result = method(outcome_dict)
            except Exception as exc:  # noqa: BLE001 - writer must not stop Atlas flows on client failure.
                return False, "", [f"nexus_outcome_save_failed: {exc}"]
            return True, self._record_id_from_result(result), []

        return False, "", ["nexus_client_has_no_supported_method"]

    def outcome_from_pipeline_state(
        self,
        pool: AtlasPlanPool | None,
        state: AtlasPipelineRunState,
    ) -> AtlasNexusOutcome:
        if state.status == "completed":
            outcome_type = "success"
            title = "Atlas pipeline completed"
        elif state.status in {"failed", "blocked"}:
            outcome_type = "failure"
            title = f"Atlas pipeline {state.status}"
        elif state.status in {"paused", "completed_with_warnings"}:
            outcome_type = "warning"
            title = f"Atlas pipeline {state.status}"
        else:
            outcome_type = "pipeline_summary"
            title = f"Atlas pipeline {state.status}"

        related_files: list[str] = []
        if pool:
            for item in pool.items:
                related_files.extend(item.target_files)

        recent_errors = state.errors[-5:]
        recent_warnings = state.warnings[-5:]
        summary_lines = [
            f"status: {state.status}",
            f"completed: {len(state.completed_item_ids)}",
            f"failed: {len(state.failed_item_ids)}",
            f"blocked: {len(state.blocked_item_ids)}",
            f"current_item_id: {state.current_item_id or 'none'}",
        ]
        if recent_errors:
            summary_lines.append("errors: " + "; ".join(recent_errors))
        if recent_warnings:
            summary_lines.append("warnings: " + "; ".join(recent_warnings))

        metadata: dict[str, Any] = {"pipeline_state": _model_dump(state)}
        if pool:
            metadata["pool_summary"] = {
                "pool_id": pool.pool_id,
                "root_goal": pool.root_goal,
                "status": pool.status,
                "total_items": len(pool.items),
                "completed_count": len(pool.completed_item_ids),
                "failed_count": len(pool.failed_item_ids),
                "blocked_count": len(pool.blocked_item_ids),
            }

        return AtlasNexusOutcome(
            outcome_type=outcome_type,
            source="pipeline",
            pool_id=state.pool_id,
            item_id=state.current_item_id,
            run_id=state.run_id,
            title=title,
            summary="\n".join(summary_lines),
            related_files=_unique(related_files),
            tags=_unique(["atlas", "pipeline", state.status]),
            metadata=metadata,
            warnings=state.warnings,
            errors=state.errors,
        )

    def outcome_from_debug_attempt(self, attempt: AtlasDebugAttempt) -> AtlasNexusOutcome:
        outcome_type = "debug_lesson" if attempt.status == "retry_allowed" else "failure"
        return AtlasNexusOutcome(
            outcome_type=outcome_type,
            source="debug_loop",
            pool_id=attempt.pool_id,
            item_id=attempt.item_id,
            run_id=attempt.run_id,
            title=f"Atlas debug lesson: {attempt.root_cause_category}",
            summary=attempt.error_summary,
            root_cause=attempt.root_cause,
            solution=attempt.proposed_fix,
            reusable_lesson=attempt.reusable_lesson,
            related_files=attempt.related_files,
            tags=_unique(["atlas", "debug_loop", attempt.root_cause_category, attempt.status]),
            debug_attempt_id=attempt.attempt_id,
            metadata={"attempt": _model_dump(attempt)},
            warnings=attempt.warnings,
            errors=attempt.errors,
        )

    def outcome_from_debug_loop(self, loop_state: AtlasDebugLoopState) -> AtlasNexusOutcome:
        if not loop_state.attempts:
            return AtlasNexusOutcome(
                outcome_type="warning",
                source="debug_loop",
                pool_id=loop_state.pool_id,
                item_id=loop_state.item_id,
                run_id=loop_state.run_id,
                title="Atlas debug loop has no attempts",
                summary=f"status: {loop_state.status}",
                tags=_unique(["atlas", "debug_loop", loop_state.status]),
                metadata={"loop_state": _model_dump(loop_state), "attempts": []},
                warnings=_unique(loop_state.warnings + ["debug_loop_has_no_attempts"]),
                errors=loop_state.errors,
            )

        latest = loop_state.attempts[-1]
        outcome = self.outcome_from_debug_attempt(latest)
        outcome.metadata["loop_state"] = _model_dump(loop_state)
        outcome.metadata["attempts"] = [_model_dump(attempt) for attempt in loop_state.attempts]
        outcome.warnings = _unique(outcome.warnings + loop_state.warnings)
        outcome.errors = _unique(outcome.errors + loop_state.errors)
        return outcome

    def outcome_from_safe_apply_result(self, result: AtlasSafeApplyResult) -> AtlasNexusOutcome:
        if result.status in {"applied", "simulated"}:
            outcome_type = "safe_apply_result"
        elif result.status in {"blocked", "failed"}:
            outcome_type = "failure"
        else:
            outcome_type = "warning"

        solution = ""
        if "approval_missing" in result.categories:
            solution = "Record required approval before applying."
        elif "non_low_risk" in result.categories:
            solution = "Re-plan as lower-risk or request approval."

        summary_lines = [
            f"decision: {result.decision}",
            f"status: {result.status}",
            "reasons: " + ("; ".join(result.reasons) if result.reasons else "none"),
        ]
        return AtlasNexusOutcome(
            outcome_type=outcome_type,
            source="safe_apply",
            pool_id=result.pool_id,
            item_id=result.item_id,
            title=f"Atlas safe apply {result.status}",
            summary="\n".join(summary_lines),
            solution=solution,
            tags=_unique(["atlas", "safe_apply", result.status, result.decision]),
            metadata={"safe_apply_result": _model_dump(result)},
            warnings=result.warnings,
            errors=result.errors,
        )

    def outcome_from_context_pack(self, context_pack: AtlasNexusContextPack) -> AtlasNexusOutcome:
        reusable_lesson = "\n".join(context_pack.recommendations) if context_pack.recommendations else context_pack.summary
        return AtlasNexusOutcome(
            outcome_type="research_context",
            source="research",
            title=f"Atlas research context: {context_pack.purpose}",
            summary=context_pack.summary,
            reusable_lesson=reusable_lesson,
            context_pack_id=context_pack.context_pack_id,
            confidence=context_pack.confidence,
            tags=_unique(["atlas", "research", context_pack.purpose, context_pack.status]),
            metadata={"context_pack": _model_dump(context_pack), "context_status": context_pack.status},
            warnings=context_pack.warnings,
            errors=context_pack.errors,
        )

    @staticmethod
    def _record_id_from_result(result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("record_id") or result.get("id") or "")
        return str(getattr(result, "record_id", "") or getattr(result, "id", "") or "")

    @staticmethod
    def _markdown_list(values: list[str]) -> str:
        if not values:
            return "- None"
        return "\n".join(value if value.startswith("- ") else f"- {value}" for value in values)

    def _outcome_markdown(self, outcome: AtlasNexusOutcome) -> str:
        return f"""# Atlas Nexus Outcome

- Outcome ID: {outcome.outcome_id}
- Type: {outcome.outcome_type}
- Source: {outcome.source}
- Status: {outcome.status}
- Project: {outcome.project}
- Pool ID: {outcome.pool_id or 'None'}
- Item ID: {outcome.item_id or 'None'}
- Run ID: {outcome.run_id or 'None'}

## Title

{outcome.title}

## Summary

{outcome.summary or 'None'}

## Root Cause

{outcome.root_cause or 'None'}

## Solution

{outcome.solution or 'None'}

## Reusable Lesson

{outcome.reusable_lesson or 'None'}

## Related Files

{self._markdown_list(outcome.related_files)}

## Tags

{self._markdown_list(outcome.tags)}

## Warnings

{self._markdown_list(outcome.warnings)}

## Errors

{self._markdown_list(outcome.errors)}
"""
