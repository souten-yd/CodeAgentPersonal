from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any
import re
import time
import uuid

from agent.task_inference import infer_task_candidates


@dataclass(slots=True)
class QueuedTask:
    id: str
    title: str
    detail: str
    priority: float
    confidence: float
    source_turn_id: str
    rationale: str = ""
    inputs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    execution_snapshot: dict[str, Any] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    revision_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "proposed"


@dataclass(slots=True)
class AgentSession:
    project_key: str = "default"
    conversation_state: dict[str, Any] = field(
        default_factory=lambda: {
            "turns": [],
            "last_intent": "chitchat",
            "intent_counts": {},
        }
    )
    goals: list[str] = field(default_factory=list)
    inferred_tasks: list[dict[str, Any]] = field(default_factory=list)
    execution_queue: deque[QueuedTask] = field(default_factory=deque)

    def ingest_user_turn(self, message: str) -> dict[str, Any]:
        text = (message or "").strip()
        turn_id = str(uuid.uuid4())
        intent = self._classify_intent(text)

        turn = {
            "id": turn_id,
            "role": "user",
            "text": text,
            "intent": intent,
            "timestamp": time.time(),
        }
        self.conversation_state["turns"].append(turn)
        self.conversation_state["last_intent"] = intent
        counts = self.conversation_state.setdefault("intent_counts", {})
        counts[intent] = int(counts.get(intent, 0)) + 1

        extracted = self._extract_tasks(turn_id=turn_id)
        self.inferred_tasks.extend(extracted)
        for task in extracted:
            if not self._passes_safety_policy(task):
                continue
            if float(task.get("confidence", 0.0)) < 0.6:
                continue
            aliases = self._build_task_aliases(task["title"], index=len(self.execution_queue))
            self.execution_queue.append(
                QueuedTask(
                    id=task["id"],
                    title=task["title"],
                    detail=task["detail"],
                    priority=task["priority"],
                    confidence=task["confidence"],
                    source_turn_id=turn_id,
                    rationale=task.get("rationale", ""),
                    inputs=list(task.get("inputs", [])),
                    dependencies=list(task.get("dependencies", [])),
                    execution_snapshot=task.get("execution_snapshot", {}),
                    aliases=aliases,
                    status="proposed",
                )
            )

        revision = self._infer_revision_from_text(text)
        revised_task = None
        if revision:
            revised_task = self.revise_task(
                revision["task_name"],
                revision["instruction"],
                source_turn_id=turn_id,
            )

        if intent == "task_request" and text:
            self._update_goals(text)

        return {
            "turn_id": turn_id,
            "intent": intent,
            "extracted_tasks": extracted,
            "queued_count": len(self.execution_queue),
            "revised_task_id": revised_task.id if revised_task else None,
        }

    def append_assistant_turn(self, message: str) -> None:
        self.conversation_state["turns"].append(
            {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "text": (message or "").strip(),
                "timestamp": time.time(),
            }
        )

    def pop_executable_tasks(
        self,
        *,
        max_tasks: int = 1,
        min_priority: float = 0.4,
        min_confidence: float = 0.5,
    ) -> list[QueuedTask]:
        executable: list[QueuedTask] = []
        deferred: deque[QueuedTask] = deque()
        while self.execution_queue:
            task = self.execution_queue.popleft()
            if task.status not in {"accepted", "ready"}:
                deferred.append(task)
                continue
            if len(executable) >= max_tasks:
                deferred.append(task)
                continue
            if task.priority >= min_priority and task.confidence >= min_confidence:
                task.status = "running"
                executable.append(task)
            else:
                task.status = "deferred"
                deferred.append(task)
        self.execution_queue.extendleft(reversed(deferred))
        return executable

    def list_tasks(self) -> list[QueuedTask]:
        return list(self.execution_queue)

    def decide_task(self, task_id: str, decision: str) -> QueuedTask | None:
        normalized = (decision or "").strip().lower()
        next_status = {
            "accept": "accepted",
            "reject": "rejected",
            "defer": "deferred",
        }.get(normalized)
        if next_status is None:
            return None
        for task in self.execution_queue:
            if task.id != task_id:
                continue
            if task.status in {"running", "done", "failed"}:
                return task
            task.status = next_status
            return task
        return None

    def find_task_by_name_or_alias(self, name_or_alias: str) -> QueuedTask | None:
        query = (name_or_alias or "").strip().lower()
        if not query:
            return None
        for task in self.execution_queue:
            if task.id.lower() == query:
                return task
            title = task.title.lower()
            if query in title or title in query:
                return task
            for alias in task.aliases:
                alias_lower = alias.lower()
                if query == alias_lower or query in alias_lower or alias_lower in query:
                    return task
        return None

    def revise_task(self, name_or_alias: str, instruction: str, *, source_turn_id: str = "") -> QueuedTask | None:
        task = self.find_task_by_name_or_alias(name_or_alias)
        note = (instruction or "").strip()
        if task is None or not note:
            return None
        before = {"title": task.title, "detail": task.detail, "status": task.status}
        task.detail = f"{task.detail}\n[revise] {note}".strip()
        if task.status in {"rejected", "failed", "cancelled"}:
            task.status = "proposed"
        task.revision_history.append(
            {
                "source_turn_id": source_turn_id,
                "instruction": note,
                "before": before,
                "after": {"title": task.title, "detail": task.detail, "status": task.status},
                "updated_at": time.time(),
            }
        )
        return task

    def _classify_intent(self, text: str) -> str:
        lower = text.lower()
        if not lower:
            return "chitchat"
        if any(k in lower for k in ("やって", "して", "実装", "fix", "build", "run", "作成", "更新")):
            return "task_request"
        if any(k in lower for k in ("?", "？", "どう", "what", "why", "教えて")):
            return "question"
        return "chitchat"

    def _extract_tasks(self, *, turn_id: str) -> list[dict[str, Any]]:
        candidates = infer_task_candidates(self.conversation_state.get("turns", []), max_candidates=5)
        tasks: list[dict[str, Any]] = []
        turns = list(self.conversation_state.get("turns", []))
        execution_snapshot = {
            "frozen_turn_ids": [str(t.get("id", "")) for t in turns],
            "frozen_turns": [
                {
                    "id": str(t.get("id", "")),
                    "role": str(t.get("role", "")),
                    "text": str(t.get("text", "")),
                    "intent": str(t.get("intent", "")),
                    "timestamp": t.get("timestamp"),
                }
                for t in turns
            ],
            "captured_at": time.time(),
        }

        for idx, candidate in enumerate(candidates):
            safe_project = re.sub(r"[^a-zA-Z0-9._-]", "-", (self.project_key or "default")).strip("-") or "default"
            tasks.append(
                {
                    "id": f"task-{safe_project}-{turn_id[:8]}-{idx + 1}",
                    "title": candidate.title,
                    "detail": candidate.inputs[0] if candidate.inputs else candidate.title,
                    "priority": round(0.8 if idx == 0 else max(0.45, 0.75 - idx * 0.1), 2),
                    "confidence": round(candidate.confidence, 2),
                    "rationale": candidate.rationale,
                    "inputs": list(candidate.inputs),
                    "dependencies": list(candidate.dependencies),
                    "execution_snapshot": execution_snapshot,
                }
            )
        return tasks

    def _passes_safety_policy(self, task: dict[str, Any]) -> bool:
        text = f"{task.get('title', '')}\n{task.get('detail', '')}".lower()
        blocked = (
            "rm -rf /",
            "drop table",
            "delete from",
            "credential",
            "password dump",
            "malware",
        )
        return not any(pattern in text for pattern in blocked)

    def _update_goals(self, text: str) -> None:
        goal = text[:120]
        if goal and goal not in self.goals:
            self.goals.append(goal)

    def _build_task_aliases(self, title: str, *, index: int) -> list[str]:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        aliases = {title.strip(), f"task-{index + 1}", f"タスク{index + 1}"}
        if index < len(letters):
            letter = letters[index]
            aliases.add(f"task {letter}")
            aliases.add(f"タスク{letter}")
        return [a for a in aliases if a]

    def _infer_revision_from_text(self, text: str) -> dict[str, str] | None:
        normalized = (text or "").strip()
        if not normalized:
            return None
        patterns = [
            r"(?P<task>タスク[\wA-Za-z一-龥ぁ-んァ-ヶー]+)\s*を\s*(?P<instruction>詳細化|修正|更新|見直し)",
            r"(?P<task>task[\s\-]?[A-Za-z0-9]+)\s*(?P<instruction>revise|update|refine)",
        ]
        for pattern in patterns:
            m = re.search(pattern, normalized, flags=re.IGNORECASE)
            if not m:
                continue
            task_name = str(m.groupdict().get("task", "")).strip()
            instruction = str(m.groupdict().get("instruction", "")).strip()
            if task_name and instruction:
                return {"task_name": task_name, "instruction": instruction}
        return None
