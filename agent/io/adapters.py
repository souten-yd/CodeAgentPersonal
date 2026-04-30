from __future__ import annotations

import base64
import os
from collections import deque
from typing import Any, Callable

from agent.io.base import ConversationIO
from agent.io.types import ConversationTurn, VoiceTurnEvent


class TextIOAdapter(ConversationIO):
    """既存チャットUI向けのテキストI/Oアダプタ。"""

    def __init__(self, message: str) -> None:
        self._message = (message or "").strip()
        self.sent_turns: list[ConversationTurn] = []

    def receive_turn(self) -> ConversationTurn:
        return ConversationTurn(text=self._message, role="user")

    def send_turn(self, turn: ConversationTurn) -> dict:
        self.sent_turns.append(turn)
        return {
            "text": (turn.text or "").strip(),
            "role": turn.role,
            "metadata": dict(turn.metadata or {}),
        }


class VoiceIOAdapter(ConversationIO):
    """ASR/TTSを内包する音声I/Oアダプタ。"""

    def __init__(
        self,
        *,
        message: str,
        audio_base64: str,
        language: str,
        audio_format: str,
        asr_transcribe: Callable[..., dict[str, Any]],
        tts_synthesize: Callable[[str], bytes] | None = None,
        interruption: bool = False,
        barge_in: bool = False,
        partial_transcript: str = "",
    ) -> None:
        self._message = (message or "").strip()
        self._audio_base64 = (audio_base64 or "").strip()
        self._language = (language or "ja").strip() or "ja"
        self._audio_format = (audio_format or "webm").strip() or "webm"
        self._asr_transcribe = asr_transcribe
        self._tts_synthesize = tts_synthesize
        self.voice_events: deque[VoiceTurnEvent] = deque()
        self.sent_turns: list[ConversationTurn] = []

        if interruption:
            self.voice_events.append(VoiceTurnEvent(type="interruption", payload={"active": True}))
        if barge_in:
            self.voice_events.append(VoiceTurnEvent(type="barge-in", payload={"active": True}))
        if partial_transcript:
            self.voice_events.append(
                VoiceTurnEvent(type="partial_transcript", payload={"text": partial_transcript.strip()})
            )

    def receive_turn(self) -> ConversationTurn:
        if self._message:
            return ConversationTurn(text=self._message, role="user", metadata=self._drain_voice_events())
        if not self._audio_base64:
            return ConversationTurn(text="", role="user", metadata=self._drain_voice_events())

        audio = base64.b64decode(self._audio_base64)
        if not audio:
            return ConversationTurn(text="", role="user", metadata=self._drain_voice_events())
        transcribed = self._asr_transcribe(
            audio,
            language=self._language,
            model_name=os.environ.get("CODEAGENT_ASR_DEFAULT_MODEL", "large-v3-turbo"),
            audio_format=self._audio_format,
        )
        text = str((transcribed or {}).get("text", "") or "").strip()
        metadata = {
            "voice": {
                "language": (transcribed or {}).get("language", self._language),
                "duration": (transcribed or {}).get("duration", 0.0),
                "asr": transcribed,
            },
            **self._drain_voice_events(),
        }
        return ConversationTurn(text=text, role="user", audio=audio, metadata=metadata)

    def send_turn(self, turn: ConversationTurn) -> dict:
        self.sent_turns.append(turn)
        payload = {
            "text": (turn.text or "").strip(),
            "role": turn.role,
            "metadata": dict(turn.metadata or {}),
        }
        if callable(self._tts_synthesize) and payload["text"]:
            wav = self._tts_synthesize(payload["text"])
            payload["audio_base64"] = base64.b64encode(wav).decode("ascii") if wav else ""
        return payload

    def _drain_voice_events(self) -> dict[str, Any]:
        events = list(self.voice_events)
        self.voice_events.clear()
        return {
            "voice_events": [
                {
                    "type": event.type,
                    "payload": dict(event.payload or {}),
                }
                for event in events
            ]
        }
