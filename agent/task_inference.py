from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import re


@dataclass(slots=True)
class TaskCandidate:
    title: str
    rationale: str
    inputs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = round(float(self.confidence), 2)
        return payload


def infer_task_candidates(turns: list[dict[str, Any]], max_candidates: int = 3) -> list[TaskCandidate]:
    """会話履歴から実行候補タスクを抽出する。"""
    if not turns:
        return []

    user_turns = [t for t in turns if t.get("role") == "user" and str(t.get("text", "")).strip()]
    if not user_turns:
        return []

    latest_user_text = str(user_turns[-1].get("text", "")).strip()
    if not latest_user_text:
        return []

    chunks = [part.strip(" ・\t") for part in re.split(r"[。\n]+", latest_user_text) if part.strip()]
    if not chunks:
        return []

    recent_context = "\n".join(str(t.get("text", "")).strip() for t in user_turns[-3:])
    candidates: list[TaskCandidate] = []
    for idx, chunk in enumerate(chunks[:max_candidates]):
        confidence = _estimate_confidence(chunk=chunk, idx=idx, turns=user_turns)
        candidates.append(
            TaskCandidate(
                title=chunk[:80],
                rationale=f"latest_user_turn:{chunk[:140]}",
                inputs=[chunk],
                dependencies=_extract_dependencies(chunk),
                confidence=confidence,
            )
        )

    if not candidates and recent_context:
        candidates.append(
            TaskCandidate(
                title=latest_user_text[:80],
                rationale="fallback_from_recent_context",
                inputs=[recent_context[-300:]],
                dependencies=[],
                confidence=0.35,
            )
        )
    return candidates


def _extract_dependencies(text: str) -> list[str]:
    deps: list[str] = []
    lowered = text.lower()
    if any(k in lowered for k in ("docker", "container")):
        deps.append("docker")
    if any(k in lowered for k in ("api", "endpoint", "fastapi")):
        deps.append("api")
    if any(k in lowered for k in ("test", "pytest", "unittest", "検証")):
        deps.append("tests")
    if any(k in lowered for k in ("db", "sqlite", "database")):
        deps.append("database")
    return deps


def _estimate_confidence(*, chunk: str, idx: int, turns: list[dict[str, Any]]) -> float:
    score = 0.3
    if len(chunk) >= 8:
        score += 0.2
    if any(k in chunk.lower() for k in ("実装", "fix", "build", "run", "追加", "変更", "作成", "update")):
        score += 0.3
    if idx == 0:
        score += 0.1
    if len(turns) >= 2:
        score += 0.05
    return max(0.0, min(score, 0.99))
