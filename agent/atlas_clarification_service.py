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
