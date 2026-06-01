from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_clarification_schema import AtlasClarificationAnswer, AtlasClarificationSession
from agent.atlas_journal import AtlasJournal


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            label = str(option.get("label") or option.get("option_id") or f"Finding {i}")
            detail = str(option.get("description") or option.get("detail") or option.get("summary") or label)
            findings.append(
                {
                    "kind": "finding",
                    "title": f"Clarify {label}",
                    "prompt": f"How should Atlas address this finding: {label}?",
                    "reason": detail,
                    "source_finding": dict(option),
                }
            )
        for i, signal in enumerate(ambiguity_signals or [], start=1):
            text = str(signal or "").strip()
            if not text:
                continue
            findings.append(
                {
                    "kind": "ambiguity",
                    "title": f"Clarify ambiguity {i}",
                    "prompt": f"How should Atlas resolve this ambiguity: {text}?",
                    "reason": text,
                    "source_finding": {"ambiguity_signal": text},
                }
            )

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
                    "options": self._default_question_options(finding["kind"]),
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
    def _default_question_options(kind: str) -> list[dict]:
        return [
            {
                "option_id": "safest_recommended",
                "label": "Safest recommended approach",
                "description": "Revise the plan to address this issue before implementation.",
                "effect": {"plan_revision": True, "risk": "reduced"},
            },
            {
                "option_id": "minimal_scope",
                "label": "Minimal-scope approach",
                "description": "Constrain the work to the smallest safe change that satisfies the requirement.",
                "effect": {"scope": "minimal", "plan_revision": True},
            },
            {
                "option_id": "defer_or_change_scope",
                "label": "Defer or change scope",
                "description": "Remove or defer the uncertain part from this plan.",
                "effect": {"scope": "deferred", "plan_revision": True},
            },
            {
                "option_id": "custom",
                "label": "自由入力 / Custom",
                "description": "Provide a custom answer for this question.",
                "requires_text": True,
                "effect": {"custom_answer": True, "source": kind},
            },
        ]

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
