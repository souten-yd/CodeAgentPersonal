from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_clarification_schema import AtlasClarificationAnswer, AtlasClarificationSession
from agent.atlas_journal import AtlasJournal


from agent.atlas_time_utils import utc_now_iso as _utc_now_iso


class AtlasClarificationService:
    def __init__(self, *, journal: AtlasJournal | None = None):
        self.journal = journal

    def build_question_queue(
        self,
        *,
        ambiguity_signals: list[str] | None = None,
        options: list[dict] | None = None,
    ) -> list[dict]:
        """Normalize independent clarification findings into one question each."""
        findings: list[dict] = []
        for i, option in enumerate(options or [], start=1):
            if not isinstance(option, dict):
                continue
            findings.append(self._finding_from_option(option, i))
        for i, signal in enumerate(ambiguity_signals or [], start=1):
            text = str(signal or "").strip()
            if not text:
                continue
            findings.append(self._finding_from_ambiguity(text, i))

        total = len(findings)
        questions: list[dict] = []
        for i, finding in enumerate(findings, start=1):
            questions.append(
                {
                    "question_id": f"clar_q_{i}",
                    "index": i,
                    "total": total,
                    "title": finding["title"],
                    "prompt": finding["prompt"],
                    "reason": finding["reason"],
                    "source_finding": finding["source_finding"],
                    "user_facing_issue_summary": finding["user_facing_issue_summary"],
                    "why_it_matters": finding["why_it_matters"],
                    "detected_signal_metadata": finding["detected_signal_metadata"],
                    "recommended_option_id": "safest_recommended",
                    "remediation_options_generated_by": "template_fallback",
                    "options": self._default_question_options(finding),
                    "status": "pending",
                }
            )
        return questions

    def apply_answer_to_question_queue(
        self,
        *,
        questions: list[dict],
        answers: list[dict] | None = None,
        question_id: str = "",
        option_id: str = "",
        answer_text: str = "",
        note: str = "",
    ) -> dict:
        normalized_questions = [dict(q) for q in (questions or []) if isinstance(q, dict)]
        if not normalized_questions:
            return {
                "questions": [],
                "answers": list(answers or []),
                "latest_decision": {},
                "pending_count": 0,
                "answered_count": 0,
                "all_answered": True,
                "current_question_index": 0,
            }

        target_id = question_id or self._first_pending_question_id(normalized_questions)
        target = next((q for q in normalized_questions if str(q.get("question_id") or "") == target_id), None)
        if target is None:
            target = next((q for q in normalized_questions if str(q.get("status") or "pending") == "pending"), normalized_questions[0])
            target_id = str(target.get("question_id") or "")
        selected = next(
            (dict(o) for o in target.get("options") or [] if str(o.get("option_id") or "") == str(option_id or "")),
            {},
        )
        answer_record = {
            "question_id": target_id,
            "option_id": option_id,
            "answer_text": answer_text or note,
            "note": note,
            "selected_option": selected,
            "selected_option_impact": self._selected_option_impact(selected),
            "source_finding": dict(target.get("source_finding") or {}),
            "reason": str(target.get("reason") or ""),
            "answered_at": _utc_now_iso(),
        }
        for q in normalized_questions:
            if str(q.get("question_id") or "") == target_id:
                q["status"] = "answered"
                q["selected_option_id"] = option_id
                q["answer_text"] = answer_text or note
                q["answered_at"] = answer_record["answered_at"]
        merged_answers = [a for a in list(answers or []) if str(a.get("question_id") or "") != target_id]
        merged_answers.append(answer_record)
        pending = [q for q in normalized_questions if str(q.get("status") or "pending") != "answered"]
        answered_count = len(normalized_questions) - len(pending)
        return {
            "questions": normalized_questions,
            "answers": merged_answers,
            "latest_decision": answer_record,
            "pending_count": len(pending),
            "answered_count": answered_count,
            "all_answered": not pending,
            "current_question_index": int(pending[0].get("index") or answered_count + 1) if pending else answered_count,
        }

    @staticmethod
    def _finding_from_option(option: dict, index: int) -> dict:
        raw_label = str(option.get("label") or option.get("option_id") or f"Finding {index}").strip()
        detail = str(option.get("description") or option.get("detail") or option.get("summary") or raw_label).strip()
        text = f"{raw_label} {detail}"
        title = AtlasClarificationService._issue_title(raw_label, detail)
        return {
            "kind": "finding",
            "title": title,
            "prompt": f"Choose how Atlas should revise the plan for: {title}",
            "reason": detail,
            "source_finding": dict(option),
            "user_facing_issue_summary": AtlasClarificationService._issue_summary(title, detail),
            "why_it_matters": AtlasClarificationService._why_it_matters(text),
            "detected_signal_metadata": {"type": "critique_finding", "raw_label": raw_label, "source": dict(option)},
        }

    @staticmethod
    def _finding_from_ambiguity(signal: str, index: int) -> dict:
        title = AtlasClarificationService._issue_title(f"ambiguity_{index}", signal)
        return {
            "kind": "ambiguity",
            "title": title,
            "prompt": f"Choose how Atlas should resolve this ambiguity: {title}",
            "reason": signal,
            "source_finding": {"ambiguity_signal": signal},
            "user_facing_issue_summary": AtlasClarificationService._issue_summary(title, signal),
            "why_it_matters": AtlasClarificationService._why_it_matters(signal),
            "detected_signal_metadata": {"type": "ambiguity_signal", "signal": signal},
        }

    @staticmethod
    def _issue_title(label: str, detail: str) -> str:
        text = f"{label} {detail}".lower()
        if "game" in text and ("over" in text or "restart" in text or "collision" in text or "loop" in text):
            return "Game-over and restart behavior is missing"
        if "missing_steps" in text or "implementation steps" in text:
            return "Implementation steps need clarification"
        if "requirement" in text and "align" in text:
            return "Requirement alignment needs clarification"
        if "maintainability" in text:
            return "Maintainability concern needs clarification"
        if "security" in text or "credential" in text or "command execution" in text:
            return "Safety-sensitive scope needs clarification"
        cleaned = str(detail or label).strip().rstrip(".")
        if not cleaned:
            return "Clarification is required"
        return cleaned[:1].upper() + cleaned[1:120]

    @staticmethod
    def _issue_summary(title: str, detail: str) -> str:
        if title == "Game-over and restart behavior is missing":
            return (
                "Atlas detected that the plan does not yet define how the game ends, "
                "how the game-over screen appears, or how the player restarts after a collision."
            )
        return f"Atlas needs a concrete decision before revising the plan: {detail}".strip()

    @staticmethod
    def _why_it_matters(text: str) -> str:
        lowered = str(text or "").lower()
        if "game" in lowered and ("over" in lowered or "restart" in lowered or "collision" in lowered or "loop" in lowered):
            return (
                "Without this, Atlas may implement collision detection but leave the game unable "
                "to transition into a clear game-over or restart state."
            )
        if "security" in lowered or "credential" in lowered or "command execution" in lowered:
            return "This can change the safety profile and must be resolved before implementation."
        return "Without a concrete choice, Atlas may revise or implement the plan in a way that does not match the intended scope."

    @staticmethod
    def _default_question_options(finding: dict) -> list[dict]:
        title = str(finding.get("title") or "this clarification")
        game_over = title == "Game-over and restart behavior is missing"
        if game_over:
            safe_summary = "Add a simple game state model playing -> game_over -> restart; on collision, stop play, show Game Over, and allow Space or click to restart."
            minimal_summary = "Add only collision-triggered game-over state and restart handling, without changing unrelated gameplay."
            defer_summary = "Remove or defer the unclear game-over/restart behavior from this plan and continue with the remaining scoped work."
        else:
            safe_summary = f"Revise the plan to address {title} before implementation."
            minimal_summary = f"Constrain the revision for {title} to the smallest safe implementation scope."
            defer_summary = f"Remove or defer the uncertain part for {title} from this plan."
        return [
            {
                "option_id": "safest_recommended",
                "label": "Recommended safe fix" if game_over else "Safest recommended approach",
                "description": safe_summary,
                "plan_change_summary": safe_summary,
                "implementation_scope": "small_state_model" if game_over else "focused_revision",
                "risk_level": "low",
                "gate_rerun_required": True,
                "can_continue_after_answer": False,
                "requires_text": False,
                "recommended": True,
                "effect": {"plan_revision": True, "risk": "reduced"},
            },
            {
                "option_id": "minimal_scope",
                "label": "Minimal fix" if game_over else "Minimal-scope approach",
                "description": minimal_summary,
                "plan_change_summary": minimal_summary,
                "implementation_scope": "minimal",
                "risk_level": "low",
                "gate_rerun_required": True,
                "can_continue_after_answer": False,
                "requires_text": False,
                "effect": {"scope": "minimal", "plan_revision": True},
            },
            {
                "option_id": "defer_or_change_scope",
                "label": "Defer/remove" if game_over else "Defer or change scope",
                "description": defer_summary,
                "plan_change_summary": defer_summary,
                "implementation_scope": "deferred",
                "risk_level": "low",
                "gate_rerun_required": True,
                "can_continue_after_answer": False,
                "requires_text": False,
                "effect": {"scope": "deferred", "plan_revision": True},
            },
            {
                "option_id": "custom",
                "label": "Custom",
                "description": "Provide a custom answer for this question.",
                "plan_change_summary": "Use the user's custom clarification as the plan revision input.",
                "implementation_scope": "custom",
                "risk_level": "unknown",
                "gate_rerun_required": True,
                "can_continue_after_answer": False,
                "requires_text": True,
                "effect": {"custom_answer": True, "source": str(finding.get("kind") or "")},
            },
        ]

    @staticmethod
    def _selected_option_impact(selected: dict) -> dict:
        return {
            key: selected.get(key)
            for key in (
                "plan_change_summary",
                "implementation_scope",
                "risk_level",
                "gate_rerun_required",
                "can_continue_after_answer",
            )
            if key in selected
        }

    @staticmethod
    def _first_pending_question_id(questions: list[dict]) -> str:
        for question in questions:
            if str(question.get("status") or "pending") != "answered":
                return str(question.get("question_id") or "")
        return str((questions[0] if questions else {}).get("question_id") or "")

    def create_session_from_plan_response(self, original_input: str, response: dict, request_payload: dict) -> AtlasClarificationSession:
        session_id = f"clar_{uuid4().hex[:12]}"
        return AtlasClarificationSession(
            session_id=session_id,
            workspace_id=str(request_payload.get("workspace_id") or "default"),
            original_input=original_input,
            project_path=str(request_payload.get("project_path") or ""),
            project_name=str(request_payload.get("project_name") or "CodeAgentPersonal"),
            planner_mode=str(request_payload.get("planner_mode") or "auto"),
            requirement_mode=str(request_payload.get("requirement_mode") or "ask_when_needed"),
            planning_depth=str(request_payload.get("planning_depth") or "standard"),
            automation_level=str(request_payload.get("automation_level") or "plan_then_ask"),
            execution_strategy=str(request_payload.get("execution_strategy") or "sequential"),
            questions=list(response.get("questions") or []),
            requirement=dict(response.get("requirement") or {}),
            status="waiting_for_clarification",
            warnings=list(response.get("warnings") or []),
            errors=list(response.get("errors") or []),
            metadata=dict(request_payload.get("metadata") or {}),
        )

    def merge_answers_into_input(self, original_input: str, questions: list[dict], answers: list[AtlasClarificationAnswer]) -> str:
        qmap = {str(q.get('question_id') or q.get('id') or ''): q for q in (questions or [])}
        lines = ["", "Clarification answers:"]
        for ans in answers or []:
            q = qmap.get(ans.question_id, {})
            text = str(q.get("prompt") or q.get("question") or ans.question_id)
            if ans.skipped:
                val = "skipped / use assumptions"
            elif isinstance(ans.answer, list):
                val = ", ".join(str(v) for v in ans.answer)
            else:
                val = str(ans.answer)
            lines.append(f"- {text}: {val}")
        return (original_input or "").rstrip() + "\n" + "\n".join(lines) + "\n"

    def merge_answers_into_requirement(self, requirement: dict, answers: list[AtlasClarificationAnswer]) -> dict:
        merged = deepcopy(requirement or {})
        answered = list(merged.get("answered_questions") or [])
        open_q = list(merged.get("open_questions") or [])
        for ans in answers or []:
            payload = {"question_id": ans.question_id, "answer": ans.answer, "skipped": bool(ans.skipped), "metadata": dict(ans.metadata or {})}
            answered.append(payload)
            open_q = [q for q in open_q if str(q.get("question_id") or q.get("id") or "") != ans.question_id]
        merged["answered_questions"] = answered
        merged["open_questions"] = open_q
        return merged

    def save_session(self, session: AtlasClarificationSession) -> str:
        if self.journal is None:
            return ""
        base = self.journal.workspace_dir() / "clarifications"
        base.mkdir(parents=True, exist_ok=True)
        json_path = base / f"{session.session_id}.json"
        md_path = base / f"{session.session_id}.md"
        session.updated_at = _utc_now_iso()
        json_path.write_text(json.dumps(session.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(f"# Atlas Clarification Session\n\n- session_id: {session.session_id}\n- status: {session.status}\n", encoding="utf-8")
        return str(json_path)

    def load_session(self, session_id: str, workspace_id: str = "default") -> AtlasClarificationSession | None:
        if self.journal is None:
            return None
        base = self.journal.root_dir / "atlas" / "workspaces" / (workspace_id or "default") / "clarifications"
        path = base / f"{session_id}.json"
        if not path.exists():
            return None
        return AtlasClarificationSession.model_validate(json.loads(path.read_text(encoding="utf-8")))
