from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class TTSEngineRuntime:
    """TTSエンジン実装の共通インターフェース。"""

    engine_key: str

    def load_stream(self, req: dict, *, emit: Callable[[dict], None]) -> None:
        raise NotImplementedError

    def unload(self, req: dict) -> dict:
        raise NotImplementedError

    def synthesize(self, req: dict) -> tuple[bytes, str]:
        raise NotImplementedError

    async def voices(self, req: dict) -> dict:
        return {"voices": []}

    def status(self) -> dict:
        return {}


@dataclass
class EngineRegistry:
    _engines: dict[str, TTSEngineRuntime]
    _aliases: dict[str, str]

    def resolve_engine_key(self, raw_engine: str | None = None, raw_engine_key: str | None = None) -> str:
        key = (raw_engine_key or raw_engine or "style_bert_vits2").strip().lower()
        key = self._aliases.get(key, key)
        return key

    def get(self, raw_engine: str | None = None, raw_engine_key: str | None = None) -> TTSEngineRuntime:
        key = self.resolve_engine_key(raw_engine=raw_engine, raw_engine_key=raw_engine_key)
        if key not in self._engines:
            raise KeyError(key)
        return self._engines[key]

    def register(self, runtime: TTSEngineRuntime, aliases: list[str] | None = None) -> None:
        self._engines[runtime.engine_key] = runtime
        for alias in aliases or []:
            self._aliases[alias] = runtime.engine_key

    def collect_status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, runtime in self._engines.items():
            payload[key] = runtime.status()
        return payload
