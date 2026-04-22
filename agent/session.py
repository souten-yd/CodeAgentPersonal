from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any
import re
import time
import uuid


@dataclass(slots=True)
class QueuedTask:
    id: str
    title: str
    detail: str
    priority: float
    confidence: float
    source_turn_id: str
    created_at: float = field(default_factory=time.time)
    status: str = "queued"


@dataclass(slots=True)
class AgentSession:
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
        extracted = self._extract_tasks(text=text, intent=intent, turn_id=turn_id)

        self.conversation_state["turns"].append(
            {
                "id": turn_id,
                "role": "user",
                "text": text,
                "intent": intent,
                "timestamp": time.time(),
            }
        )
        self.conversation_state["last_intent"] = intent
        counts = self.conversation_state.setdefault("intent_counts", {})
        counts[intent] = int(counts.get(intent, 0)) + 1

        self.inferred_tasks.extend(extracted)
        for task in extracted:
            self.execution_queue.append(
                QueuedTask(
                    id=task["id"],
                    title=task["title"],
                    detail=task["detail"],
                    priority=task["priority"],
                    confidence=task["confidence"],
                    source_turn_id=turn_id,
                )
            )
        if intent == "task_request" and text:
            self._update_goals(text)

        return {
            "turn_id": turn_id,
            "intent": intent,
            "extracted_tasks": extracted,
            "queued_count": len(self.execution_queue),
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
            if len(executable) >= max_tasks:
                deferred.append(task)
                continue
            if task.priority >= min_priority and task.confidence >= min_confidence:
                task.status = "ready"
                executable.append(task)
            else:
                task.status = "deferred"
                deferred.append(task)
        self.execution_queue.extendleft(reversed(deferred))
        return executable

    def _classify_intent(self, text: str) -> str:
        lower = text.lower()
        if not lower:
            return "chitchat"
        if any(k in lower for k in ("やって", "して", "実装", "fix", "build", "run", "作成", "更新")):
            return "task_request"
        if any(k in lower for k in ("?", "？", "どう", "what", "why", "教えて")):
            return "question"
        return "chitchat"

    def _extract_tasks(self, *, text: str, intent: str, turn_id: str) -> list[dict[str, Any]]:
        if intent != "task_request":
            return []
        chunks = [part.strip(" ・\t") for part in re.split(r"[。\n]+", text) if part.strip()]
        tasks: list[dict[str, Any]] = []
        for idx, chunk in enumerate(chunks[:5]):
            confidence = 0.85 if len(chunk) >= 8 else 0.6
            priority = 0.8 if idx == 0 else max(0.45, 0.75 - idx * 0.1)
            tasks.append(
                {
                    "id": f"task-{turn_id[:8]}-{idx+1}",
                    "title": chunk[:80],
                    "detail": chunk,
                    "priority": round(priority, 2),
                    "confidence": round(confidence, 2),
                }
            )
        return tasks

    def _update_goals(self, text: str) -> None:
        goal = text[:120]
        if goal and goal not in self.goals:
            self.goals.append(goal)
