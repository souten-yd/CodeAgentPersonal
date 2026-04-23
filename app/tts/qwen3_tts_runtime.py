from __future__ import annotations

from typing import Any, Callable

from .engine_registry import TTSEngineRuntime


class Qwen3TTSRuntime(TTSEngineRuntime):
    engine_key = "qwen3_tts"

    def __init__(
        self,
        *,
        available: Callable[[], bool],
        import_error: Callable[[], str],
        default_model_id: Callable[[], str],
        resolve_model_id: Callable[[str | None], str],
        load_fn: Callable[[str, str], dict],
        unload_fn: Callable[[], dict],
        synthesize_fn: Callable[..., bytes],
        status_fn: Callable[[], dict],
        debug_error_fn: Callable[..., Any],
        settings_set: Callable[[str, Any], None],
        runtime_device: Callable[[], str],
    ) -> None:
        self._available = available
        self._import_error = import_error
        self._default_model_id = default_model_id
        self._resolve_model_id = resolve_model_id
        self._load_fn = load_fn
        self._unload_fn = unload_fn
        self._synthesize_fn = synthesize_fn
        self._status_fn = status_fn
        self._debug_error_fn = debug_error_fn
        self._settings_set = settings_set
        self._runtime_device = runtime_device

    def load_stream(self, req: dict, *, emit: Callable[[dict], None]) -> None:
        device = str(req.get("device", "cuda")) if req.get("device") in ("cpu", "cuda") else "cuda"
        model_id = self._resolve_model_id(req.get("model_id", self._default_model_id()))

        if not self._available():
            emit({
                "type": "error",
                "detail": (
                    "qwen_tts API / torch / soundfile がインストールされていないか、"
                    "Qwen3TTSModel の import に失敗しました。"
                    f" detail={self._import_error()} / install: pip install -U qwen-tts"
                ),
            })
            return

        emit({"type": "loading", "message": f"Qwen3 TTS モデル ({model_id}) をロード中です。初回はダウンロードに数分かかる場合があります..."})
        try:
            result = self._load_fn(model_id, device)
            self._settings_set("qwen3tts_model_id", model_id)
            emit({"type": "done", **result, "engine_key": self.engine_key})
        except Exception as e:
            self._debug_error_fn("qwen3tts", "load", e, detail={"model_id": model_id, "device": device}, device=device)
            emit({"type": "error", "detail": str(e)})

    def unload(self, req: dict) -> dict:
        result = self._unload_fn()
        return {**result, "engine": "qwen3tts", "engine_key": self.engine_key}

    def synthesize(self, req: dict) -> tuple[bytes, str]:
        text = str(req.get("text", "")).strip()
        speed = float(req.get("speed", 1.0))
        ref_text = str(req.get("ref_text", "") or "")
        language = str(req.get("language", "Auto") or "Auto")
        ref_b64 = str(req.get("ref_audio_base64", "") or "").strip()
        ref_bytes = None
        if ref_b64:
            try:
                import base64 as _b64
                ref_bytes = _b64.b64decode(ref_b64)
            except Exception as e:
                raise ValueError("ref_audio_base64 が不正です。参照音声を再登録してください。") from e
        try:
            wav = self._synthesize_fn(
                text,
                speed,
                ref_audio_bytes=ref_bytes,
                ref_text=ref_text,
                language=language,
            )
        except Exception as e:
            self._debug_error_fn(
                "qwen3tts",
                "inference",
                e,
                detail={"text_length": len(text), "speed": speed},
                device=self._runtime_device(),
            )
            raise
        return wav, "audio/wav"

    async def voices(self, req: dict) -> dict:
        return {"voices": [], "engine_key": self.engine_key}

    def status(self) -> dict:
        src = self._status_fn()
        return {
            "available": src.get("qwen3tts_available"),
            "loaded": src.get("qwen3tts_loaded"),
            "model_id": src.get("qwen3tts_model_id"),
            "selected_model_id": src.get("qwen3tts_selected_model_id"),
            "device": src.get("qwen3tts_device"),
            "actual_device": src.get("qwen3tts_actual_device"),
            "dtype": src.get("qwen3tts_dtype"),
            "actual_dtype": src.get("qwen3tts_actual_dtype"),
            "attention": src.get("qwen3tts_attention"),
            "actual_attention": src.get("qwen3tts_actual_attn_backend"),
            "missing_requirements": src.get("qwen3tts_missing_requirements"),
            "install_status": src.get("qwen3tts_install_status"),
        }
