from __future__ import annotations

import base64
import collections
import json
import logging
import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .engine_registry import TTSEngineRuntime
from .style_bert_vits2_paths import resolve_style_bert_vits2_models_dir
from .text_normalizer import looks_japanese, normalize_text_for_sbv2_jp_extra

_STYLE_BERT_VITS2_DEFAULT_REPO_DIR = "/app/Style-Bert-VITS2"
_STYLE_BERT_VITS2_DEFAULT_VENV_DIR = "/app/Style-Bert-VITS2/.venv"
_STYLE_BERT_VITS2_WEIGHT_EXTENSIONS = (".safetensors", ".pth", ".pt", ".onnx")
_STYLE_BERT_VITS2_IGNORED_MODEL_DIRS = {"__pycache__", "cache", ".cache", "tmp", "temp", "logs"}
_WORKER_STDERR_TAIL_LINES = 120
_logger = logging.getLogger("style_bert_vits2")
_TEXT_LOG_INFO_LIMIT = 500
_TEXT_LOG_DEBUG_LIMIT = 50000


def _repo_dir() -> str:
    return os.environ.get("CODEAGENT_STYLE_BERT_VITS2_REPO_DIR", _STYLE_BERT_VITS2_DEFAULT_REPO_DIR)


def _venv_dir() -> str:
    return os.environ.get("CODEAGENT_STYLE_BERT_VITS2_VENV_DIR", _STYLE_BERT_VITS2_DEFAULT_VENV_DIR)


def _python_path() -> str:
    return os.path.join(_venv_dir(), "bin", "python")


def _models_dir() -> str:
    return resolve_style_bert_vits2_models_dir()


def _worker_count() -> int:
    raw = str(os.environ.get("CODEAGENT_STYLE_BERT_VITS2_WORKERS", "1")).strip()
    try:
        value = int(raw)
    except Exception:
        _logger.warning(
            "[Style-Bert-VITS2] invalid CODEAGENT_STYLE_BERT_VITS2_WORKERS=%r; fallback to 1 (recommended default)",
            raw,
        )
        return 1
    return max(1, value)


def _validate_model_assets(model_path: Path, config_path: Path, style_vec_path: Path, *, source: str) -> None:
    errors: list[str] = []
    if not model_path.exists():
        errors.append(f"model_path missing: {model_path} (source={source})")
    if model_path.exists() and not model_path.is_file():
        errors.append(f"model_path is not a file: {model_path} (source={source})")
    if model_path.exists() and model_path.suffix.lower() not in _STYLE_BERT_VITS2_WEIGHT_EXTENSIONS:
        errors.append(
            f"model_path suffix invalid: {model_path.suffix!r} path={model_path} expected={_STYLE_BERT_VITS2_WEIGHT_EXTENSIONS}"
        )
    if not config_path.exists():
        errors.append(f"config_path missing: {config_path}")
    if config_path.exists() and not config_path.is_file():
        errors.append(f"config_path is not a file: {config_path}")
    if not style_vec_path.exists():
        errors.append(f"style_vec_path missing: {style_vec_path}")
    if style_vec_path.exists() and not style_vec_path.is_file():
        errors.append(f"style_vec_path is not a file: {style_vec_path}")

    if errors:
        for msg in errors:
            _logger.error("[Style-Bert-VITS2] path validation error: %s", msg)
        raise RuntimeError("Style-Bert-VITS2 model validation failed: " + " | ".join(errors))


def _resolve_model_paths(model_id: str) -> tuple[str, str, str]:
    model = (model_id or "").strip()
    if not model:
        raise ValueError("model required when engine=style_bert_vits2")
    if model.startswith(".") or model.lower() in _STYLE_BERT_VITS2_IGNORED_MODEL_DIRS:
        raise ValueError(f"invalid Style-Bert-VITS2 model selection: {model!r}")

    model_dir: Path
    weight_path: Path | None = None

    model_candidate = Path(model).expanduser()
    if model_candidate.is_file():
        weight_path = model_candidate
        model_dir = model_candidate.parent
        source = "model_path"
    else:
        model_dir = Path(_models_dir()) / model
        source = "model_id"
        if not model_dir.is_dir():
            raise RuntimeError(f"Style-Bert-VITS2 model not found: {model}")

    config_path = model_dir / "config.json"
    style_path = model_dir / "style_vectors.npy"

    if weight_path is None:
        for candidate in sorted(model_dir.rglob("*")):
            if candidate.is_file() and candidate.suffix.lower() in _STYLE_BERT_VITS2_WEIGHT_EXTENSIONS:
                weight_path = candidate
                break
    if weight_path is None:
        raise RuntimeError(f"Style-Bert-VITS2 weight file missing in: {model_dir}")

    _validate_model_assets(weight_path, config_path, style_path, source=source)
    return str(weight_path), str(config_path), str(style_path)


def _pick_device(req: dict) -> str:
    valid_devices = {"cpu", "cuda", "mps"}
    auto_values = {"", "auto"}
    disabled_markers = {"", "-1", "none", "void"}

    requested = str(req.get("device", "")).strip().lower()
    if requested in valid_devices:
        return requested

    if requested in auto_values:
        env_device = str(os.environ.get("CODEAGENT_STYLE_BERT_VITS2_DEVICE", "")).strip().lower()
        if env_device in valid_devices:
            return env_device
        if env_device in auto_values:
            cuda_visible = str(os.environ.get("CUDA_VISIBLE_DEVICES", "")).strip().lower()
            nvidia_visible = str(os.environ.get("NVIDIA_VISIBLE_DEVICES", "")).strip().lower()
            has_cuda_visibility = cuda_visible not in disabled_markers or nvidia_visible not in disabled_markers
            has_cuda_dir = os.path.isdir("/usr/local/cuda")
            torch_cuda_available = False
            try:
                import torch

                torch_cuda_available = bool(torch.cuda.is_available())
            except Exception:
                torch_cuda_available = False
            if has_cuda_visibility or has_cuda_dir or torch_cuda_available:
                return "cuda"

    return "cpu"


def _to_optional_float(v, default: float | None = None) -> float | None:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except Exception:
        return default


def _to_optional_int(v, default: int | None = None) -> int | None:
    if v is None or v == "":
        return default
    try:
        return int(v)
    except Exception:
        return default


def _to_optional_bool(v, default: bool | None = None) -> bool | None:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        normalized = v.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
    try:
        return bool(v)
    except Exception:
        return default


def _normalize_sbv2_language(raw_language: str | None, model_version: str | None = None) -> str:
    raw = (raw_language or "").strip().lower()
    version = (model_version or "").strip().lower()

    if "jp-extra" in version:
        return "JP"

    if raw in {"", "auto", "ja", "jp", "jpn", "japanese", "日本語", "jp-extra"}:
        return "JP"
    if raw in {"en", "eng", "english"}:
        return "EN"
    if raw in {"zh", "cn", "chinese", "中国語"}:
        return "ZH"

    return "JP"


def _read_model_version(config_path: str | None) -> str:
    if not config_path:
        return ""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        version = cfg.get("version")
        return str(version or "").strip()
    except Exception:
        return ""


def _is_jp_extra_model_version(model_version: str | None) -> bool:
    version = str(model_version or "").strip().lower()
    return bool(version and "jp-extra" in version)


def _decide_effective_language(requested_language: str | None, model_version: str | None) -> tuple[str, str, bool]:
    normalized = _normalize_sbv2_language(requested_language, model_version=model_version)
    is_jp_extra = _is_jp_extra_model_version(model_version)
    if is_jp_extra:
        return "JP", normalized, True
    if normalized in {"JP", "EN", "ZH"}:
        return normalized, normalized, False
    return "JP", "JP", False


def _sanitize_preview_text(value: str | None, *, limit: int) -> str:
    text = str(value or "").replace("\n", "\\n")
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _normalize_non_japanese_policy(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"normalize_then_block", "normalize_then_warn", "normalize_then_allow"}:
        return raw
    if raw == "block":
        return "normalize_then_block"
    if raw == "warn":
        return "normalize_then_warn"
    if raw == "allow":
        return "normalize_then_allow"
    return "normalize_then_block"


_SBV2_JP_EXTRA_NORMALIZATION_DEFAULTS = {
    "sbv2_jp_extra_text_normalization": True,
    "sbv2_jp_extra_english_to_katakana": "llm",
    "sbv2_jp_extra_emoji_policy": "skip",
    "sbv2_jp_extra_symbol_policy": "readable",
    "sbv2_jp_extra_url_policy": "skip",
    "sbv2_jp_extra_non_japanese_policy": "normalize_then_block",
}


def _resolve_sbv2_jp_extra_normalization_settings(req: dict) -> dict:
    settings = req.get("settings") or {}
    resolved = {}
    for key, default_value in _SBV2_JP_EXTRA_NORMALIZATION_DEFAULTS.items():
        top_level_value = req.get(key)
        nested_value = settings.get(key) if isinstance(settings, dict) else None
        resolved[key] = (
            top_level_value
            if top_level_value is not None
            else nested_value
            if nested_value is not None
            else default_value
        )

    english_to_katakana = str(resolved.get("sbv2_jp_extra_english_to_katakana") or "llm").strip().lower()
    resolved["sbv2_jp_extra_english_policy"] = english_to_katakana

    emoji_policy = str(resolved.get("sbv2_jp_extra_emoji_policy") or "skip").strip().lower()
    resolved["emoji_policy"] = "keep" if emoji_policy == "keep" else "replace" if emoji_policy == "describe" else "remove"
    resolved["sbv2_jp_extra_emoji_policy"] = resolved["emoji_policy"]

    symbol_policy = str(resolved.get("sbv2_jp_extra_symbol_policy") or "readable").strip().lower()
    resolved["symbol_policy"] = "keep" if symbol_policy == "keep" else "replace" if symbol_policy == "readable" else "remove"
    resolved["sbv2_jp_extra_symbol_policy"] = resolved["symbol_policy"]

    url_policy = str(resolved.get("sbv2_jp_extra_url_policy") or "skip").strip().lower()
    resolved["url_email_policy"] = "replace" if url_policy == "readable" else "remove"
    resolved["sbv2_jp_extra_url_email_policy"] = resolved["url_email_policy"]

    resolved["sbv2_jp_extra_non_japanese_policy"] = _normalize_non_japanese_policy(
        resolved.get("sbv2_jp_extra_non_japanese_policy")
    )
    return resolved


class StyleBertVITS2Runtime(TTSEngineRuntime):
    engine_key = "style_bert_vits2"

    def __init__(self) -> None:
        self._worker_lock = threading.Lock()
        self._workers = _worker_count()
        self._worker_procs: list[subprocess.Popen | None] = []
        self._worker_script_paths: list[str | None] = []
        self._worker_stderr_tails: list[collections.deque[str]] = []
        self._stderr_threads: list[threading.Thread | None] = []
        self._worker_rr_index = 0
        if self._workers != 1:
            _logger.warning(
                "[Style-Bert-VITS2] CODEAGENT_STYLE_BERT_VITS2_WORKERS=%d. Multi-worker mode may degrade GPU performance due to contention; default/recommended is 1.",
                self._workers,
            )

    def load_stream(self, req: dict, *, emit):
        try:
            self._ensure_worker_started()
        except Exception as e:
            emit({"type": "error", "engine_key": self.engine_key, "detail": f"worker unavailable: {e}"})
            return

        status = self.status()
        if status["available"]:
            emit({"type": "status", "engine_key": self.engine_key, "detail": "Style-Bert-VITS2 runtime ready."})
        else:
            emit({"type": "error", "engine_key": self.engine_key, "detail": status.get("detail") or "runtime unavailable"})

    def unload(self, req: dict) -> dict:
        with self._worker_lock:
            self._stop_workers_locked()
        return {"status": "unloaded", "engine_key": self.engine_key}

    def prepare(self, req: dict | None = None) -> dict:
        req = req or {}
        self._ensure_worker_started()
        model = str(req.get("model", "")).strip()
        if not self._is_prepare_target_model(model):
            return {
                "status": "ready",
                "engine_key": self.engine_key,
                "preloaded": False,
                "reason": "no_valid_model_selected",
            }
        warmup_started = time.perf_counter()
        preload_payload = self._build_payload(req, model=model, text="事前ロードです。", request_id="prepare")
        result = self._send_to_worker(preload_payload)
        warmup_elapsed_ms = int((time.perf_counter() - warmup_started) * 1000)
        return {
            "status": "ready",
            "engine_key": self.engine_key,
            "preloaded": bool(result.get("ok")),
            "device": str(result.get("device") or preload_payload.get("device") or "cpu"),
            "warmup_elapsed_ms": warmup_elapsed_ms,
            "cache_hit": bool(result.get("cache_hit")),
        }

    @staticmethod
    def _is_prepare_target_model(model: str) -> bool:
        if not model:
            return False
        normalized = model.strip()
        if not normalized:
            return False
        lowered = normalized.lower()
        if normalized.startswith(".") or lowered in _STYLE_BERT_VITS2_IGNORED_MODEL_DIRS:
            return False
        return True

    def _build_payload(self, req: dict, *, model: str, text: str, request_id: str | None = None) -> dict:
        model_path, config_path, style_vec_path = _resolve_model_paths(model)
        model_version = _read_model_version(config_path)
        requested_language = str(req.get("language", "")).strip() or str(
            (req.get("settings") or {}).get("echo_tts_sbv2_language", "")
        ).strip() or None
        effective_language, normalized_language, is_jp_extra = _decide_effective_language(requested_language, model_version)
        normalization_result = None
        normalized_text = text
        normalization_settings = _resolve_sbv2_jp_extra_normalization_settings(req)
        if is_jp_extra:
            normalization_result = normalize_text_for_sbv2_jp_extra(text, normalization_settings)
            normalized_text = str(normalization_result.get("text") or "")
        non_japanese_policy = _normalize_non_japanese_policy(
            normalization_settings.get("sbv2_jp_extra_non_japanese_policy")
        )
        return {
            "request_id": str(request_id or ""),
            "text": normalized_text,
            "model_name": model,
            "model_path": model_path,
            "config_path": config_path,
            "style_vec_path": style_vec_path,
            "out_path": str(req.get("out_path", "")).strip() or None,
            "return_mode": str(req.get("return_mode", "b64") or "b64").strip().lower(),
            "device": _pick_device(req),
            "speaker_id": _to_optional_int(req.get("speaker_id"), 0),
            "speaker": str(req.get("speaker_name", "")).strip() or str(req.get("speaker", "")).strip() or None,
            "style": str(req.get("style", "")).strip() or "Neutral",
            "style_weight": _to_optional_float(req.get("style_weight"), 1.0),
            "sdp_ratio": _to_optional_float(req.get("sdp_ratio"), 0.2),
            "noise": _to_optional_float(req.get("noise"), 0.6),
            "noise_w": _to_optional_float(req.get("noise_w"), 0.8),
            "length": _to_optional_float(req.get("length"), 1.0),
            "line_split": _to_optional_bool(req.get("line_split"), True),
            "split_interval": _to_optional_float(req.get("split_interval"), 0.5),
            "assist_text": str(req.get("assist_text", "")).strip() or None,
            "assist_text_weight": _to_optional_float(req.get("assist_text_weight"), 1.0),
            "requested_language": requested_language,
            "normalized_language": normalized_language,
            "effective_language": effective_language,
            "model_version": model_version,
            "is_jp_extra": is_jp_extra,
            "route": str(req.get("route") or "tts/synthesize"),
            "caller": str(req.get("caller") or "manual"),
            "use_translation": bool(req.get("use_translation", False)),
            "text_source": str(req.get("text_source") or "raw"),
            "raw_text": str(req.get("raw_text") or text),
            "translated_text": str(req.get("translated_text") or ""),
            "non_japanese_policy": non_japanese_policy,
            "jp_extra_normalization": normalization_result,
        }

    def build_normalization_preview(self, req: dict | None = None) -> dict:
        req = req or {}
        selected_source = str(req.get("text_source") or "raw").strip().lower()
        if selected_source not in {"raw", "translated"}:
            selected_source = "raw"
        use_translation = bool(req.get("use_translation", False))
        raw_text = str(req.get("raw_text") or req.get("text") or "")
        translated_text = str(req.get("translated_text") or "")
        translated_available = bool(translated_text.strip())

        source = "raw"
        source_reason = "selected"
        if selected_source == "translated" and use_translation and translated_available:
            source = "translated"
        elif selected_source == "translated" and not use_translation:
            source_reason = "fallback_raw_translation_disabled"
        elif selected_source == "translated" and not translated_available:
            source_reason = "fallback_raw_translation_empty"

        original_text = translated_text if source == "translated" else raw_text
        requested_language = str(req.get("language", "")).strip() or str(
            (req.get("settings") or {}).get("echo_tts_sbv2_language", "")
        ).strip() or None
        model = str(req.get("model", "")).strip()
        model_version = ""
        is_jp_extra = False
        normalized_language = _normalize_sbv2_language(requested_language, model_version=model_version)
        effective_language = "JP" if normalized_language == "auto" else normalized_language
        if effective_language not in {"JP", "EN", "ZH"}:
            effective_language = "JP"
        normalization_settings = _resolve_sbv2_jp_extra_normalization_settings(req)
        normalization_result = None
        normalized_text = original_text
        final_text = normalized_text
        looks_japanese_final = looks_japanese(final_text)

        if model:
            try:
                model_path, config_path, style_vec_path = _resolve_model_paths(model)
                model_version = _read_model_version(config_path)
                effective_language, normalized_language, is_jp_extra = _decide_effective_language(
                    requested_language, model_version
                )
                if is_jp_extra:
                    normalization_result = normalize_text_for_sbv2_jp_extra(original_text, normalization_settings)
                    normalized_text = str(normalization_result.get("text") or "")
                final_text = normalized_text
                looks_japanese_final = (
                    bool(normalization_result.get("looks_japanese_after"))
                    if normalization_result and normalization_result.get("looks_japanese_after") is not None
                    else looks_japanese(final_text)
                )
                _ = model_path, style_vec_path
            except Exception:
                # preview should stay available even if model metadata lookup fails
                pass

        operations = normalization_result.get("operations") if normalization_result else []
        operation_labels: list[str] = []
        for op in operations or []:
            if not isinstance(op, dict):
                continue
            op_type = str(op.get("type") or "").strip()
            op_value = op.get("value")
            if op_type and op_value not in (None, ""):
                operation_labels.append(f"{op_type}:{op_value}")
            elif op_type:
                operation_labels.append(op_type)

        return {
            "text_source": source,
            "selected_text_source": selected_source,
            "source_reason": source_reason,
            "use_translation": use_translation,
            "translation_available": translated_available,
            "requested_language": requested_language or "JP",
            "normalized_language": normalized_language,
            "effective_language": effective_language,
            "model_version": model_version,
            "is_jp_extra": is_jp_extra,
            "original_text": original_text,
            "normalized_text": normalized_text,
            "final_preview": final_text,
            "looks_japanese": bool(looks_japanese_final),
            "normalization_operations": operation_labels,
            "normalization_operation_details": operations or [],
        }

    @staticmethod
    def _stderr_reader(stderr_pipe, stderr_tail: collections.deque[str]) -> None:
        try:
            while True:
                line = stderr_pipe.readline()
                if not line:
                    break
                stderr_tail.append(line.rstrip("\n"))
        except Exception:
            pass

    def _stop_worker_locked(self, index: int) -> None:
        proc = self._worker_procs[index]
        self._worker_procs[index] = None
        if proc is None:
            return

        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        script_path = self._worker_script_paths[index]
        if script_path:
            try:
                os.remove(script_path)
            except OSError:
                pass
            self._worker_script_paths[index] = None

    def _stop_workers_locked(self) -> None:
        for idx in range(len(self._worker_procs)):
            self._stop_worker_locked(idx)

    @staticmethod
    def _worker_code() -> str:
        return r'''
import base64
import io
import inspect
import json
import sys
import time
import traceback
import warnings
import wave
from pathlib import Path

_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

import numpy as np
from style_bert_vits2.constants import Languages
from style_bert_vits2.tts_model import TTSModel

warnings.filterwarnings("ignore", category=FutureWarning, module="torch.nn.utils.weight_norm")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pyopenjtalk")

loaded_model = None
loaded_signature = None


def emit_response(payload: dict) -> None:
    _REAL_STDOUT.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()


def synth(req: dict) -> dict:
    global loaded_model, loaded_signature
    total_started = time.perf_counter()
    load_started = total_started
    load_elapsed_ms = 0
    infer_elapsed_ms = 0
    encode_elapsed_ms = 0
    model_path = Path(req["model_path"])
    config_path = Path(req["config_path"])
    style_vec_path = Path(req["style_vec_path"])
    device = str(req.get("device", "cpu") or "cpu").strip().lower()
    if device == "auto":
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
    if device not in {"cpu", "cuda", "mps"}:
        device = "cpu"
    signature = (str(model_path), str(config_path), str(style_vec_path), str(device))
    cache_hit = loaded_model is not None and loaded_signature == signature

    if loaded_model is None or loaded_signature != signature:
        loaded_model = TTSModel(
            model_path=model_path,
            config_path=config_path,
            style_vec_path=style_vec_path,
            device=device,
        )
        loaded_signature = signature
    load_elapsed_ms = int((time.perf_counter() - load_started) * 1000)

    out_path = Path(req["out_path"]) if req.get("out_path") else None
    return_mode = str(req.get("return_mode", "b64") or "b64").strip().lower()
    if return_mode not in {"b64", "file"}:
        return_mode = "b64"
    hp = getattr(loaded_model, "hyper_parameters", None)
    model_version = str(getattr(hp, "version", "") or "")
    is_jp_extra = "jp-extra" in model_version.lower()

    language_map = {"JP": Languages.JP, "EN": Languages.EN, "ZH": Languages.ZH}
    language_code = str(req.get("effective_language") or req.get("normalized_language") or "JP").strip().upper()
    language = language_map.get(language_code, Languages.JP)
    if is_jp_extra:
        language = Languages.JP

    kwargs = {
        "text": req["text"],
        "language": language,
        "style": req.get("style") or "Neutral",
        "style_weight": float(req.get("style_weight", 1.0)),
        "sdp_ratio": float(req.get("sdp_ratio", 0.2)),
        "noise": float(req.get("noise", 0.6)),
        "noise_w": float(req.get("noise_w", 0.8)),
        "length": float(req.get("length", 1.0)),
        "line_split": bool(req.get("line_split", True)),
        "split_interval": float(req.get("split_interval", 0.5)),
    }
    if req.get("assist_text"):
        kwargs["assist_text"] = req["assist_text"]
        kwargs["assist_text_weight"] = float(req.get("assist_text_weight", 1.0))

    infer_signature = inspect.signature(loaded_model.infer)
    infer_params = set(infer_signature.parameters.keys())
    if "language" not in infer_params:
        kwargs.pop("language", None)

    speaker = req.get("speaker")
    if speaker:
        if "speaker" in infer_params:
            kwargs["speaker"] = speaker
        elif "speaker_name" in infer_params:
            kwargs["speaker_name"] = speaker
    elif "speaker_id" in infer_params:
        kwargs["speaker_id"] = int(req.get("speaker_id", 0))

    infer_text = str(req.get("text", ""))
    infer_text_preview = infer_text.replace("\n", "\\n")
    if len(infer_text_preview) > 500:
        infer_text_preview = infer_text_preview[:500] + "…"
    request_id = str(req.get("request_id") or "-")
    sys.stderr.write(
        "[Style-Bert-VITS2][worker_infer] "
        f"id={request_id} "
        f"language={language_code} "
        f"model_version={model_version or '-'} "
        f"is_jp_extra={str(is_jp_extra).lower()} "
        f"text={infer_text_preview!r} "
        f"infer_text_length={len(infer_text)} "
        f"speaker_id={req.get('speaker_id', 0)} "
        f"style={req.get('style') or 'Neutral'}\n"
    )
    sys.stderr.flush()

    infer_started = time.perf_counter()
    infer_result = loaded_model.infer(**kwargs)
    infer_elapsed_ms = int((time.perf_counter() - infer_started) * 1000)
    if isinstance(infer_result, tuple) and len(infer_result) == 2:
        sample_rate, audio = infer_result
    else:
        audio = infer_result
        data = getattr(hp, "data", None)
        sample_rate = getattr(data, "sampling_rate", None) or 44100

    audio_arr = np.asarray(audio)
    if audio_arr.dtype != np.int16:
        audio_arr = np.clip(audio_arr, -32768, 32767).astype(np.int16)

    encode_started = time.perf_counter()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(audio_arr.tobytes())

    wav_bytes = buffer.getvalue()
    audio_b64 = None
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(wav_bytes)
    if return_mode == "b64":
        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
    encode_elapsed_ms = int((time.perf_counter() - encode_started) * 1000)
    total_elapsed_ms = int((time.perf_counter() - total_started) * 1000)
    text_value = str(req.get("text", ""))

    return {
        "ok": True,
        "audio_b64": audio_b64,
        "return_mode": return_mode,
        "out_path": str(out_path) if out_path is not None else "",
        "cache_hit": bool(cache_hit),
        "load_elapsed_ms": load_elapsed_ms,
        "infer_elapsed_ms": infer_elapsed_ms,
        "encode_elapsed_ms": encode_elapsed_ms,
        "total_elapsed_ms": total_elapsed_ms,
        "sample_rate": int(sample_rate),
        "output_bytes": len(wav_bytes),
        "device": str(device),
        "model_name": str(req.get("model_name", "")),
        "text_length": len(text_value),
    }


while True:
    try:
        line = input()
    except EOFError:
        break
    try:
        req = json.loads(line)
        emit_response(synth(req))
    except Exception as e:
        emit_response({"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()})
'''

    def _ensure_worker_started(self) -> None:
        with self._worker_lock:
            py = _python_path()
            if not os.path.isfile(py):
                raise RuntimeError(f"Style-Bert-VITS2 python not found: {py}")
            while len(self._worker_procs) < self._workers:
                self._worker_procs.append(None)
                self._worker_script_paths.append(None)
                self._worker_stderr_tails.append(collections.deque(maxlen=_WORKER_STDERR_TAIL_LINES))
                self._stderr_threads.append(None)

            for idx in range(self._workers):
                proc = self._worker_procs[idx]
                if proc and proc.poll() is None:
                    continue

                self._stop_worker_locked(idx)
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as tf:
                    tf.write(self._worker_code())
                    self._worker_script_paths[idx] = tf.name

                self._worker_procs[idx] = subprocess.Popen(
                    [py, self._worker_script_paths[idx]],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                if self._worker_procs[idx] and self._worker_procs[idx].stderr:
                    self._stderr_threads[idx] = threading.Thread(
                        target=self._stderr_reader,
                        args=(self._worker_procs[idx].stderr, self._worker_stderr_tails[idx]),
                        daemon=True,
                    )
                    self._stderr_threads[idx].start()

    def _next_worker_index_locked(self) -> int:
        if self._workers == 1:
            return 0
        worker_idx = self._worker_rr_index % self._workers
        self._worker_rr_index = (self._worker_rr_index + 1) % self._workers
        return worker_idx

    def _send_once_to_worker(self, payload: dict) -> dict:
        self._ensure_worker_started()
        with self._worker_lock:
            worker_idx = self._next_worker_index_locked()
            proc = self._worker_procs[worker_idx]
            if proc is None or proc.stdin is None or proc.stdout is None:
                raise RuntimeError("Style-Bert-VITS2 worker unavailable")
            proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            invalid_lines: list[str] = []
            for _ in range(3):
                line = proc.stdout.readline()
                if not line:
                    stderr_tail = "\n".join(self._worker_stderr_tails[worker_idx])
                    raise RuntimeError(
                        f"Style-Bert-VITS2 worker returned no output (worker={worker_idx}).\n{stderr_tail}"
                    )
                stripped = line.strip()
                if not stripped:
                    invalid_lines.append("<empty_line>")
                    continue
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError as e:
                    invalid_lines.append(stripped[:300])
                    if len(invalid_lines) >= 3:
                        stderr_tail = "\n".join(self._worker_stderr_tails[worker_idx])
                        raise RuntimeError(
                            "Style-Bert-VITS2 worker protocol error: stdout was not JSON. "
                            f"line={stripped[:300]!r} json_error={e} invalid_lines={invalid_lines}\n{stderr_tail}"
                        ) from e
            stderr_tail = "\n".join(self._worker_stderr_tails[worker_idx])
            raise RuntimeError(
                "Style-Bert-VITS2 worker protocol error: exceeded non-JSON stdout line limit.\n"
                f"invalid_lines={invalid_lines}\n{stderr_tail}"
            )

    def _restart_workers(self) -> None:
        with self._worker_lock:
            self._stop_workers_locked()
        self._ensure_worker_started()

    def _send_to_worker(self, payload: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self._send_once_to_worker(payload)
            except Exception as e:
                last_error = e
                if attempt == 0:
                    self._restart_workers()
                    _logger.warning("[Style-Bert-VITS2] worker_restart=true cache_hit=false retry=1")
                    continue
                raise RuntimeError(f"Style-Bert-VITS2 worker request failed after retry: {e}") from e
        raise RuntimeError(f"Style-Bert-VITS2 worker request failed: {last_error}")

    def _log_sbv2_input(self, request_id: str, model: str, payload: dict, *, raw_text: str, translated_text: str = "", tts_text_source: str = "raw") -> None:
        final_tts_text = str(payload.get("text") or "")
        normalization_result = payload.get("jp_extra_normalization") or {}
        normalization_enabled = bool(payload.get("is_jp_extra"))
        normalization_changed = bool(normalization_result.get("changed")) if normalization_result else False
        normalization_operations = normalization_result.get("operations") or []
        original_tts_text = translated_text if tts_text_source == "translated" and translated_text else raw_text
        normalized_tts_text = str(normalization_result.get("text") or original_tts_text)
        looks_japanese_before = bool(
            normalization_result.get("looks_japanese_before")
            if normalization_result.get("looks_japanese_before") is not None
            else looks_japanese(original_tts_text)
        )
        looks_japanese_after = bool(
            normalization_result.get("looks_japanese_after")
            if normalization_result.get("looks_japanese_after") is not None
            else looks_japanese(final_tts_text)
        )
        raw_preview = _sanitize_preview_text(raw_text, limit=_TEXT_LOG_INFO_LIMIT)
        translated_preview = _sanitize_preview_text(translated_text, limit=_TEXT_LOG_INFO_LIMIT)
        original_tts_text_preview = _sanitize_preview_text(original_tts_text, limit=_TEXT_LOG_INFO_LIMIT)
        normalized_tts_text_preview = _sanitize_preview_text(normalized_tts_text, limit=_TEXT_LOG_INFO_LIMIT)
        final_tts_text_preview = _sanitize_preview_text(final_tts_text, limit=_TEXT_LOG_INFO_LIMIT)
        _logger.info(
            "[Style-Bert-VITS2][input] id=%s route=%s caller=%s engine=%s model=%s model_path=%s model_version=%s is_jp_extra=%s requested_language=%s normalized_language=%s effective_language=%s use_translation=%s text_source=%s raw_text=%r translated_text=%r original_tts_text_preview=%r normalized_tts_text_preview=%r final_tts_text_preview=%r final_tts_text_length=%d normalization_enabled=%s normalization_changed=%s normalization_operations=%s looks_japanese_before=%s looks_japanese_after=%s looks_japanese=%s non_japanese_policy=%s speaker_id=%s speaker=%s style=%s style_weight=%s device=%s line_split=%s length=%s sdp_ratio=%s noise=%s noise_w=%s",
            request_id,
            payload.get("route") or "tts/synthesize",
            payload.get("caller") or "manual",
            self.engine_key,
            model,
            payload.get("model_path"),
            payload.get("model_version") or "",
            str(bool(payload.get("is_jp_extra"))).lower(),
            payload.get("requested_language") or "JP",
            payload.get("normalized_language") or "JP",
            payload.get("effective_language") or "JP",
            str(bool(payload.get("use_translation"))).lower(),
            tts_text_source,
            raw_preview,
            translated_preview,
            original_tts_text_preview,
            normalized_tts_text_preview,
            final_tts_text_preview,
            len(final_tts_text),
            str(normalization_enabled).lower(),
            str(normalization_changed).lower(),
            normalization_operations,
            str(looks_japanese_before).lower(),
            str(looks_japanese_after).lower(),
            str(looks_japanese_after).lower(),
            payload.get("non_japanese_policy") or "normalize_then_block",
            payload.get("speaker_id"),
            payload.get("speaker"),
            payload.get("style"),
            payload.get("style_weight"),
            payload.get("device"),
            payload.get("line_split"),
            payload.get("length"),
            payload.get("sdp_ratio"),
            payload.get("noise"),
            payload.get("noise_w"),
        )
        _logger.debug(
            "[Style-Bert-VITS2][input_debug] id=%s raw_text=%r translated_text=%r original_tts_text_preview=%r normalized_tts_text_preview=%r final_tts_text_preview=%r final_text=%r normalization_enabled=%s normalization_changed=%s normalization_operations=%s looks_japanese_before=%s looks_japanese_after=%s non_japanese_policy=%s",
            request_id,
            _sanitize_preview_text(raw_text, limit=_TEXT_LOG_DEBUG_LIMIT),
            _sanitize_preview_text(translated_text, limit=_TEXT_LOG_DEBUG_LIMIT),
            _sanitize_preview_text(original_tts_text, limit=_TEXT_LOG_DEBUG_LIMIT),
            _sanitize_preview_text(normalized_tts_text, limit=_TEXT_LOG_DEBUG_LIMIT),
            _sanitize_preview_text(final_tts_text, limit=_TEXT_LOG_DEBUG_LIMIT),
            _sanitize_preview_text(final_tts_text, limit=_TEXT_LOG_DEBUG_LIMIT),
            str(normalization_enabled).lower(),
            str(normalization_changed).lower(),
            normalization_operations,
            str(looks_japanese_before).lower(),
            str(looks_japanese_after).lower(),
            payload.get("non_japanese_policy") or "normalize_then_block",
        )
        if normalization_result:
            _logger.info(
                "[Style-Bert-VITS2][normalizer] id=%s changed=%s looks_japanese_before=%s looks_japanese_after=%s warnings=%s operations=%s",
                request_id,
                str(bool(normalization_result.get("changed"))).lower(),
                str(bool(normalization_result.get("looks_japanese_before"))).lower(),
                str(bool(normalization_result.get("looks_japanese_after"))).lower(),
                normalization_result.get("warnings") or [],
                normalization_result.get("operations") or [],
            )
        if payload.get("is_jp_extra") and final_tts_text and not looks_japanese_after:
            _logger.warning(
                "[Style-Bert-VITS2][input_warning] JP-Extra selected but final_tts_text does not look Japanese. text_preview=%r",
                final_tts_text_preview,
            )

    def synthesize(self, req: dict) -> tuple[bytes, str]:
        request_id = str(req.get("request_id") or uuid.uuid4().hex[:8])
        text = str(req.get("text", "")).strip()
        if not text:
            raise ValueError("text required")

        model = str(req.get("model", "")).strip()
        device = _pick_device(req)
        _logger.info(
            "[Style-Bert-VITS2][synthesize:%s] start model=%s text_len=%d device=%s repo=%s venv_python=%s models_dir=%s",
            request_id,
            model,
            len(text),
            device,
            _repo_dir(),
            _python_path(),
            _models_dir(),
        )

        payload = self._build_payload(req, model=model, text=text, request_id=request_id)
        self._log_sbv2_input(
            request_id,
            model,
            payload,
            raw_text=str(payload.get("raw_text") or text),
            translated_text=str(payload.get("translated_text") or ""),
            tts_text_source=str(payload.get("text_source") or "raw"),
        )
        final_tts_text = str(payload.get("text") or "")
        if payload.get("is_jp_extra") and not final_tts_text:
            raise ValueError(json.dumps({"status_code": 422, "error": "読み上げ可能なテキストがありません"}, ensure_ascii=False))
        policy = _normalize_non_japanese_policy(payload.get("non_japanese_policy"))
        normalization_result = payload.get("jp_extra_normalization") or {}
        looks_japanese_after = bool(
            normalization_result.get("looks_japanese_after")
            if normalization_result.get("looks_japanese_after") is not None
            else looks_japanese(final_tts_text)
        )
        if payload.get("is_jp_extra") and final_tts_text and not looks_japanese_after:
            preview = _sanitize_preview_text(final_tts_text, limit=_TEXT_LOG_INFO_LIMIT)
            if policy == "normalize_then_block":
                _logger.error(
                    "[Style-Bert-VITS2][input_blocked] JP-Extra requires Japanese text after normalization. final_text_preview=%r",
                    preview,
                )
                raise ValueError(
                    json.dumps(
                        {
                            "status_code": 422,
                            "error": "JP-Extra model requires Japanese text",
                            "text_preview": preview,
                            "effective_language": payload.get("effective_language") or "JP",
                            "model_version": payload.get("model_version") or "",
                        },
                        ensure_ascii=False,
                    )
                )
            if policy == "normalize_then_warn":
                _logger.warning(
                    "[Style-Bert-VITS2][input_non_japanese_warn] JP-Extra text still looks non-Japanese after normalization; proceeding. final_text_preview=%r",
                    preview,
                )
        output = self._send_to_worker(payload)
        if not output.get("ok"):
            err = output.get("error") or "unknown error"
            raise RuntimeError(f"Style-Bert-VITS2 synth failed: {err}\n{output.get('traceback', '')}")

        b64 = output.get("audio_b64")
        if not b64:
            raise RuntimeError("Style-Bert-VITS2 synth failed: empty audio payload")

        audio_bytes = base64.b64decode(b64)
        _logger.info(
            "[Style-Bert-VITS2][synthesize] id=%s model=%s text_len=%d device=%s cache_hit=%s load_ms=%d infer_ms=%d encode_ms=%d total_ms=%d bytes=%d",
            request_id,
            output.get("model_name") or model,
            int(output.get("text_length") or len(text)),
            output.get("device") or device,
            bool(output.get("cache_hit")),
            int(output.get("load_elapsed_ms") or 0),
            int(output.get("infer_elapsed_ms") or 0),
            int(output.get("encode_elapsed_ms") or 0),
            int(output.get("total_elapsed_ms") or 0),
            int(output.get("output_bytes") or len(audio_bytes)),
        )
        return audio_bytes, "audio/wav"

    def synthesize_batch_item_raw(self, req: dict) -> dict:
        request_id = str(req.get("request_id") or uuid.uuid4().hex[:8])
        text = str(req.get("text", "")).strip()
        if not text:
            raise ValueError("text required")

        model = str(req.get("model", "")).strip()
        if not model:
            raise ValueError("model required when engine=style_bert_vits2")

        payload = self._build_payload(req, model=model, text=text, request_id=request_id)
        self._log_sbv2_input(
            request_id,
            model,
            payload,
            raw_text=str(payload.get("raw_text") or text),
            translated_text=str(payload.get("translated_text") or ""),
            tts_text_source=str(payload.get("text_source") or "raw"),
        )
        final_tts_text = str(payload.get("text") or "")
        if payload.get("is_jp_extra") and not final_tts_text:
            raise ValueError(json.dumps({"status_code": 422, "error": "読み上げ可能なテキストがありません"}, ensure_ascii=False))
        policy = _normalize_non_japanese_policy(payload.get("non_japanese_policy"))
        normalization_result = payload.get("jp_extra_normalization") or {}
        looks_japanese_after = bool(
            normalization_result.get("looks_japanese_after")
            if normalization_result.get("looks_japanese_after") is not None
            else looks_japanese(final_tts_text)
        )
        if payload.get("is_jp_extra") and final_tts_text and not looks_japanese_after:
            preview = _sanitize_preview_text(final_tts_text, limit=_TEXT_LOG_INFO_LIMIT)
            if policy == "normalize_then_block":
                _logger.error(
                    "[Style-Bert-VITS2][input_blocked] JP-Extra requires Japanese text after normalization. final_text_preview=%r",
                    preview,
                )
                raise ValueError(
                    json.dumps(
                        {
                            "status_code": 422,
                            "error": "JP-Extra model requires Japanese text",
                            "text_preview": preview,
                            "effective_language": payload.get("effective_language") or "JP",
                            "model_version": payload.get("model_version") or "",
                        },
                        ensure_ascii=False,
                    )
                )
            if policy == "normalize_then_warn":
                _logger.warning(
                    "[Style-Bert-VITS2][input_non_japanese_warn] JP-Extra text still looks non-Japanese after normalization; proceeding. final_text_preview=%r",
                    preview,
                )
        payload["return_mode"] = str(req.get("return_mode", payload.get("return_mode") or "b64") or "b64").strip().lower()
        output = self._send_to_worker(payload)
        if not output.get("ok"):
            err = output.get("error") or "unknown error"
            raise RuntimeError(f"Style-Bert-VITS2 synth failed: {err}\n{output.get('traceback', '')}")

        return_mode = str(output.get("return_mode") or payload.get("return_mode") or "b64").strip().lower()
        out_path = str(output.get("out_path") or payload.get("out_path") or "").strip()
        audio_b64 = output.get("audio_b64")
        audio_bytes = b""
        if return_mode == "b64":
            if not audio_b64:
                raise RuntimeError("Style-Bert-VITS2 synth failed: empty audio payload")
            audio_bytes = base64.b64decode(audio_b64)
        elif return_mode == "file":
            if not out_path or not os.path.isfile(out_path):
                raise RuntimeError("Style-Bert-VITS2 synth failed: output file missing")
        else:
            raise RuntimeError(f"Style-Bert-VITS2 synth failed: unsupported return_mode={return_mode}")

        _logger.info(
            "[Style-Bert-VITS2][batch_item] id=%s model=%s text_len=%d return_mode=%s cache_hit=%s infer_ms=%d total_ms=%d bytes=%d out_path=%s",
            request_id,
            output.get("model_name") or model,
            int(output.get("text_length") or len(text)),
            return_mode,
            bool(output.get("cache_hit")),
            int(output.get("infer_elapsed_ms") or 0),
            int(output.get("total_elapsed_ms") or 0),
            int(output.get("output_bytes") or len(audio_bytes)),
            out_path or "-",
        )
        return {
            "audio_bytes": audio_bytes,
            "out_path": out_path,
            "return_mode": return_mode,
            "sample_rate": int(output.get("sample_rate") or 0),
            "output_bytes": int(output.get("output_bytes") or len(audio_bytes)),
            "load_elapsed_ms": int(output.get("load_elapsed_ms") or 0),
            "infer_elapsed_ms": int(output.get("infer_elapsed_ms") or 0),
            "encode_elapsed_ms": int(output.get("encode_elapsed_ms") or 0),
            "total_elapsed_ms": int(output.get("total_elapsed_ms") or 0),
            "cache_hit": bool(output.get("cache_hit")),
            "device": str(output.get("device") or payload.get("device") or "cpu"),
            "model_name": str(output.get("model_name") or model),
            "text_length": int(output.get("text_length") or len(text)),
        }

    async def voices(self, req: dict) -> dict:
        model = str(req.get("model", "")).strip()
        voices: list[dict] = []
        styles: list[str] = []
        speaker_name = None
        if model:
            _weight_path, config_path, _style_path = _resolve_model_paths(model)
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                spk2id = cfg.get("spk2id") or {}
                if isinstance(spk2id, dict):
                    voices = [{"name": str(k), "id": int(v)} for k, v in spk2id.items()]
                    if voices:
                        speaker_name = voices[0]["name"]
                style2id = cfg.get("style2id") or {}
                if isinstance(style2id, dict):
                    styles = [str(k) for k in style2id.keys()]
            except Exception:
                voices = []
                styles = []
        return {
            "voices": voices,
            "engine_key": self.engine_key,
            "extensions": {"style": styles, "emotion": [], "speaker_name": speaker_name},
        }

    def status(self) -> dict:
        py = _python_path()
        repo = _repo_dir()
        models = _models_dir()
        has_python = os.path.isfile(py) and os.access(py, os.X_OK)
        has_repo = os.path.isdir(repo)
        has_models = os.path.isdir(models)
        available = has_python and has_repo and has_models
        detail = ""
        if not has_repo:
            detail = f"repo not found: {repo}"
        elif not has_python:
            detail = f"python not found/executable: {py}"
        elif not has_models:
            detail = f"models dir not found: {models}"
        return {
            "available": available,
            "loaded": available,
            "engine_key": self.engine_key,
            "repo_dir": repo,
            "venv_python": py,
            "models_dir": models,
            "detail": detail,
            "worker_running": any(proc and proc.poll() is None for proc in self._worker_procs),
        }
