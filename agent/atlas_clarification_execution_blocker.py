from __future__ import annotations

from typing import Any


def clarification_execution_block_reasons(pool: Any) -> list[str]:
    metadata = getattr(pool, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    reasons: list[str] = []

    def add(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    if metadata.get("clarification_required"):
        add("clarification_required")

    try:
        pending_count = int(metadata.get("pending_question_count") or 0)
    except (TypeError, ValueError):
        pending_count = 0
    if pending_count > 0:
        add("clarification_pending_questions")

    questions = metadata.get("clarification_questions")
    if isinstance(questions, list) and any(
        isinstance(question, dict) and str(question.get("status") or "pending") != "answered"
        for question in questions
    ):
        add("clarification_questions_unanswered")

    clarification_answers = metadata.get("clarification_answers")
    has_clarification_answers = bool(clarification_answers) if isinstance(clarification_answers, list) else False
    has_revised_plan = bool(metadata.get("revised_plan_snapshot"))
    has_gate_rerun_evidence = bool(
        metadata.get("gate_rerun_performed_after_clarification")
        or metadata.get("gate_rerun_after_clarification")
        or metadata.get("gate_rerun_evidence_after_clarification")
        or (
            metadata.get("rerun_critique_gate_after_clarification")
            and metadata.get("rerun_safety_gate_after_clarification")
        )
    )

    if metadata.get("plan_revision_required_after_clarification"):
        add("plan_revision_required_after_clarification")
    if metadata.get("gate_rerun_required_after_clarification"):
        add("gate_rerun_required_after_clarification")
    if has_clarification_answers and not has_revised_plan:
        add("missing_revised_plan_snapshot_after_clarification")
    if has_clarification_answers and not has_gate_rerun_evidence:
        add("missing_gate_rerun_evidence_after_clarification")
    return reasons
