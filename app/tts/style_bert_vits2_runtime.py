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

_STYLE_BERT_VITS2_DEFAULT_REPO_DIR = "/app/Style-Bert-VITS2"
_STYLE_BERT_VITS2_DEFAULT_VENV_DIR = "/app/Style-Bert-VITS2/.venv"
_STYLE_BERT_VITS2_WEIGHT_EXTENSIONS = (".safetensors", ".pth", ".pt", ".onnx")
_WORKER_STDERR_TAIL_LINES = 120
_logger = logging.getLogger("style_bert_vits2")


def _repo_dir() -> str:
    return os.environ.get("CODEAGENT_STYLE_BERT_VITS2_REPO_DIR", _STYLE_BERT_VITS2_DEFAULT_REPO_DIR)


def _venv_dir() -> str:
    return os.environ.get("CODEAGENT_STYLE_BERT_VITS2_VENV_DIR", _STYLE_BERT_VITS2_DEFAULT_VENV_DIR)


def _python_path() -> str:
    return os.path.join(_venv_dir(), "bin", "python")


def _models_dir() -> str:
    return resolve_style_bert_vits2_models_dir()


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
            disabled_markers = {"", "-1", "none", "void"}
            has_cuda_visibility = cuda_visible not in disabled_markers or nvidia_visible not in disabled_markers
            has_cuda_dir = os.path.isdir("/usr/local/cuda")
            if has_cuda_visibility or has_cuda_dir:
                return "auto"

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


class StyleBertVITS2Runtime(TTSEngineRuntime):
    engine_key = "style_bert_vits2"

    def __init__(self) -> None:
        self._worker_lock = threading.Lock()
        self._worker_proc: subprocess.Popen | None = None
        self._worker_script_path: str | None = None
        self._worker_stderr_tail: collections.deque[str] = collections.deque(maxlen=_WORKER_STDERR_TAIL_LINES)
        self._stderr_thread: threading.Thread | None = None

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
            self._stop_worker_locked()
        return {"status": "unloaded", "engine_key": self.engine_key}

    def prepare(self, req: dict | None = None) -> dict:
        req = req or {}
        self._ensure_worker_started()
        model = str(req.get("model", "")).strip()
        if not model:
            return {"status": "ready", "engine_key": self.engine_key, "preloaded": False}
        warmup_started = time.perf_counter()
        preload_payload = self._build_payload(req, model=model, text="事前ロードです。")
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

    def _build_payload(self, req: dict, *, model: str, text: str) -> dict:
        model_path, config_path, style_vec_path = _resolve_model_paths(model)
        requested_language = str(req.get("language", "")).strip() or None
        normalized_language = _normalize_sbv2_language(requested_language)
        return {
            "text": text,
            "model_name": model,
            "model_path": model_path,
            "config_path": config_path,
            "style_vec_path": style_vec_path,
            "out_path": str(req.get("out_path", "")).strip() or None,
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
        }

    def _stderr_reader(self, stderr_pipe) -> None:
        try:
            while True:
                line = stderr_pipe.readline()
                if not line:
                    break
                self._worker_stderr_tail.append(line.rstrip("\n"))
        except Exception:
            pass

    def _stop_worker_locked(self) -> None:
        proc = self._worker_proc
        self._worker_proc = None
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

        if self._worker_script_path:
            try:
                os.remove(self._worker_script_path)
            except OSError:
                pass
            self._worker_script_path = None

    @staticmethod
    def _worker_code() -> str:
        return r'''
import base64
import io
import inspect
import json
import time
import traceback
import warnings
import wave
from pathlib import Path

import numpy as np
from style_bert_vits2.constants import Languages
from style_bert_vits2.tts_model import TTSModel

warnings.filterwarnings("ignore", category=FutureWarning, module="torch.nn.utils.weight_norm")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pyopenjtalk")

loaded_model = None
loaded_signature = None


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
    hp = getattr(loaded_model, "hyper_parameters", None)
    model_version = str(getattr(hp, "version", "") or "")
    is_jp_extra = "jp-extra" in model_version.lower()

    language_map = {"JP": Languages.JP, "EN": Languages.EN, "ZH": Languages.ZH}
    language = language_map.get(str(req.get("normalized_language") or "JP").strip().upper(), Languages.JP)
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
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(wav_bytes)
    encode_elapsed_ms = int((time.perf_counter() - encode_started) * 1000)
    total_elapsed_ms = int((time.perf_counter() - total_started) * 1000)
    text_value = str(req.get("text", ""))

    return {
        "ok": True,
        "audio_b64": base64.b64encode(wav_bytes).decode("ascii"),
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
    req = json.loads(line)
    try:
        print(json.dumps(synth(req), ensure_ascii=False), flush=True)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}, ensure_ascii=False), flush=True)
'''

    def _ensure_worker_started(self) -> None:
        with self._worker_lock:
            if self._worker_proc and self._worker_proc.poll() is None:
                return
            self._stop_worker_locked()

            py = _python_path()
            if not os.path.isfile(py):
                raise RuntimeError(f"Style-Bert-VITS2 python not found: {py}")

            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as tf:
                tf.write(self._worker_code())
                self._worker_script_path = tf.name

            self._worker_proc = subprocess.Popen(
                [py, self._worker_script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            if self._worker_proc.stderr:
                self._stderr_thread = threading.Thread(target=self._stderr_reader, args=(self._worker_proc.stderr,), daemon=True)
                self._stderr_thread.start()

    def _send_to_worker(self, payload: dict) -> dict:
        self._ensure_worker_started()
        with self._worker_lock:
            proc = self._worker_proc
            if proc is None or proc.stdin is None or proc.stdout is None:
                raise RuntimeError("Style-Bert-VITS2 worker unavailable")
            proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                stderr_tail = "\n".join(self._worker_stderr_tail)
                raise RuntimeError(f"Style-Bert-VITS2 worker returned no output.\n{stderr_tail}")
            return json.loads(line)

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

        payload = self._build_payload(req, model=model, text=text)
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
            "worker_running": bool(self._worker_proc and self._worker_proc.poll() is None),
        }
