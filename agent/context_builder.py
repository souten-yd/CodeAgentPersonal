from __future__ import annotations


class ContextBuilder:
    """Planner へ渡すコンテキスト構築インターフェース。"""

    def build(self, objective: str, runtime_state: dict) -> dict:
        raise NotImplementedError
