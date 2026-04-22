from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


VoiceEventType = Literal["interruption", "barge-in", "partial_transcript"]


@dataclass(slots=True)
class VoiceTurnEvent:
    type: VoiceEventType
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationTurn:
    text: str
    role: Literal["user", "assistant"] = "user"
    audio: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
