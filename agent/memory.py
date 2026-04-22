from __future__ import annotations


class MemoryStore:
    """エージェント記憶の読み書きインターフェース。"""

    def recall(self, objective: str, limit: int = 5) -> list[dict]:
        raise NotImplementedError

    def save(self, item: dict) -> None:
        raise NotImplementedError
