from __future__ import annotations

from abc import ABC, abstractmethod

from agent.io.types import ConversationTurn


class ConversationIO(ABC):
    """Conversation 入出力の抽象。UI/音声差分を吸収する。"""

    @abstractmethod
    def receive_turn(self) -> ConversationTurn:
        """入力ターンを受信する。"""

    @abstractmethod
    def send_turn(self, turn: ConversationTurn) -> dict:
        """出力ターンを送信する。"""
