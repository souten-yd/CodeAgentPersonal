from __future__ import annotations

from .engine_registry import TTSEngineRuntime


class StyleBertVITS2Runtime(TTSEngineRuntime):
    """将来実装用のプレースホルダ。

    Qwen3互換レスポンスに加えて、style/emotion/speaker_name など拡張フィールドを
    返しやすい構造を提供する。
    """

    engine_key = "style_bert_vits2"

    def load_stream(self, req: dict, *, emit):
        emit({
            "type": "error",
            "engine_key": self.engine_key,
            "detail": "Style-Bert-VITS2 runtime is not configured yet.",
        })

    def unload(self, req: dict) -> dict:
        return {"status": "unloaded", "engine_key": self.engine_key}

    def synthesize(self, req: dict) -> tuple[bytes, str]:
        raise RuntimeError("Style-Bert-VITS2 runtime is not configured yet.")

    async def voices(self, req: dict) -> dict:
        return {
            "voices": [],
            "engine_key": self.engine_key,
            "extensions": {"style": [], "emotion": [], "speaker_name": None},
        }

    def status(self) -> dict:
        return {"available": False, "loaded": False, "engine_key": self.engine_key}
