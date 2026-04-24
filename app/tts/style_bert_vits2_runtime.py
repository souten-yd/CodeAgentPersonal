from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from .engine_registry import TTSEngineRuntime
from .style_bert_vits2_paths import resolve_style_bert_vits2_models_dir

_STYLE_BERT_VITS2_DEFAULT_REPO_DIR = "/app/Style-Bert-VITS2"
_STYLE_BERT_VITS2_DEFAULT_VENV_DIR = "/app/Style-Bert-VITS2/.venv"
_STYLE_BERT_VITS2_WEIGHT_EXTENSIONS = (".safetensors", ".pth", ".pt", ".onnx")
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
    requested = str(req.get("device", "")).strip().lower()
    if requested in {"cpu", "cuda", "mps"}:
        return requested
    # Style-Bert-VITS2 は未指定時に CPU を既定にする（GPU 非搭載環境での 500 を回避）
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

    # JP-Extra モデルは JP 以外を許可しない
    if "jp-extra" in version:
        return "JP"

    if raw in {"", "auto", "ja", "jp", "jpn", "japanese", "日本語", "jp-extra"}:
        return "JP"
    if raw in {"en", "eng", "english"}:
        return "EN"
    if raw in {"zh", "cn", "chinese", "中国語"}:
        return "ZH"

    # 安全側に倒して JP
    return "JP"


class StyleBertVITS2Runtime(TTSEngineRuntime):
    engine_key = "style_bert_vits2"

    def load_stream(self, req: dict, *, emit):
        status = self.status()
        if status["available"]:
            emit({"type": "status", "engine_key": self.engine_key, "detail": "Style-Bert-VITS2 runtime ready."})
        else:
            emit({"type": "error", "engine_key": self.engine_key, "detail": status.get("detail") or "runtime unavailable"})

    def unload(self, req: dict) -> dict:
        return {"status": "unloaded", "engine_key": self.engine_key}

    def synthesize(self, req: dict) -> tuple[bytes, str]:
        request_id = str(req.get("request_id") or uuid.uuid4().hex[:8])
        text = str(req.get("text", "")).strip()
        if not text:
            raise ValueError("text required")

        py = _python_path()
        if not os.path.isfile(py):
            raise RuntimeError(f"Style-Bert-VITS2 python not found: {py}")

        model = str(req.get("model", "")).strip()
        model_path, config_path, style_vec_path = _resolve_model_paths(model)
        device = _pick_device(req)
        _logger.info(
            "[Style-Bert-VITS2][synthesize:%s] start model=%s text_len=%d device=%s repo=%s venv_python=%s models_dir=%s",
            request_id,
            model,
            len(text),
            device,
            _repo_dir(),
            py,
            _models_dir(),
        )

        requested_language = str(req.get("language", "")).strip() or None
        normalized_language = _normalize_sbv2_language(requested_language)

        payload = {
            "text": text,
            "model_path": model_path,
            "config_path": config_path,
            "style_vec_path": style_vec_path,
            "out_path": str(req.get("out_path", "")).strip() or None,
            "device": device,
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

        _logger.info(
            "[Style-Bert-VITS2][synthesize:%s] payload path types model=%s config=%s style=%s",
            request_id,
            type(payload.get("model_path")).__name__,
            type(payload.get("config_path")).__name__,
            type(payload.get("style_vec_path")).__name__,
        )

        worker_code = r'''
import base64
import io
import inspect
import json
import traceback
import wave
from pathlib import Path

import numpy as np
from style_bert_vits2.constants import Languages
from style_bert_vits2.tts_model import TTSModel

req = json.loads(input())
try:
    model_path = Path(req["model_path"])
    config_path = Path(req["config_path"])
    style_vec_path = Path(req["style_vec_path"])
    out_path = Path(req["out_path"]) if req.get("out_path") else None

    path_errors = []
    if not model_path.exists():
        path_errors.append(f"model_path missing: {model_path} (type={type(req.get('model_path')).__name__})")
    if model_path.exists() and model_path.suffix.lower() not in {".safetensors", ".onnx", ".pth", ".pt"}:
        path_errors.append(f"model_path suffix invalid: {model_path.suffix!r} path={model_path}")
    if not config_path.exists():
        path_errors.append(f"config_path missing: {config_path} (type={type(req.get('config_path')).__name__})")
    if not style_vec_path.exists():
        path_errors.append(f"style_vec_path missing: {style_vec_path} (type={type(req.get('style_vec_path')).__name__})")
    if path_errors:
        raise FileNotFoundError(" | ".join(path_errors))

    model = TTSModel(
        model_path=model_path,
        config_path=config_path,
        style_vec_path=style_vec_path,
        device=req.get("device", "cuda"),
    )
    hp = getattr(model, "hyper_parameters", None)
    model_version = ""
    if hp is not None:
        model_version = str(getattr(hp, "version", "") or "")
    is_jp_extra = "jp-extra" in model_version.lower()

    line_split_raw = req.get("line_split", True)
    if isinstance(line_split_raw, str):
        line_split = line_split_raw.strip().lower() in {"1", "true", "yes", "on"}
    else:
        line_split = bool(line_split_raw)

    requested_language = req.get("requested_language")
    normalized_language = req.get("normalized_language") or "JP"
    language_map = {
        "JP": Languages.JP,
        "EN": Languages.EN,
        "ZH": Languages.ZH,
    }
    language = language_map.get(str(normalized_language).strip().upper(), Languages.JP)
    # 安全策: JP-Extra は必ず JP
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
        "line_split": line_split,
        "split_interval": float(req.get("split_interval", 0.5)),
    }
    if req.get("assist_text"):
        kwargs["assist_text"] = req["assist_text"]
        kwargs["assist_text_weight"] = float(req.get("assist_text_weight", 1.0))

    infer_signature = inspect.signature(model.infer)
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

    infer_result = model.infer(**kwargs)
    if isinstance(infer_result, tuple) and len(infer_result) == 2:
        sample_rate, audio = infer_result
    else:
        audio = infer_result
        hp = getattr(model, "hyper_parameters", None)
        data = getattr(hp, "data", None)
        sample_rate = getattr(data, "sampling_rate", None) or 44100
    audio_arr = np.asarray(audio)
    if audio_arr.dtype != np.int16:
        audio_arr = np.clip(audio_arr, -32768, 32767).astype(np.int16)

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
    print(json.dumps({"ok": True, "audio_b64": base64.b64encode(wav_bytes).decode("ascii")}))
except Exception as e:
    print(json.dumps({
        "ok": False,
        "error": f"{type(e).__name__}: {e}",
        "traceback": traceback.format_exc(),
        "requested_language": req.get("requested_language"),
        "normalized_language": req.get("normalized_language"),
        "model_path": req.get("model_path"),
        "config_path": req.get("config_path"),
        "model_version": model_version if "model_version" in locals() else "",
        "is_jp_extra": is_jp_extra if "is_jp_extra" in locals() else False,
    }))
'''

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as tf:
            tf.write(worker_code)
            script_path = tf.name

        try:
            proc = subprocess.run(
                [py, script_path],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            try:
                os.remove(script_path)
            except OSError:
                pass

        _logger.info(
            "[Style-Bert-VITS2][synthesize:%s] worker_exit code=%s stdout_lines=%d stderr_lines=%d",
            request_id,
            proc.returncode,
            len((proc.stdout or "").splitlines()),
            len((proc.stderr or "").splitlines()),
        )
        if proc.stdout:
            _logger.info("[Style-Bert-VITS2][synthesize:%s] worker_stdout_tail:\n%s", request_id, "\n".join((proc.stdout or "").splitlines()[-40:]))
        if proc.stderr:
            _logger.error("[Style-Bert-VITS2][synthesize:%s] worker_stderr_tail:\n%s", request_id, "\n".join((proc.stderr or "").splitlines()[-40:]))

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"Style-Bert-VITS2 worker failed (code={proc.returncode}): {detail}")

        output_raw = (proc.stdout or "").strip().splitlines()
        if not output_raw:
            raise RuntimeError("Style-Bert-VITS2 worker returned no output")

        try:
            output = json.loads(output_raw[-1])
        except Exception as e:
            raise RuntimeError(f"Style-Bert-VITS2 worker invalid output: {output_raw[-1]} ({e})")

        if not output.get("ok"):
            err = output.get("error") or "unknown error"
            tb = output.get("traceback") or ""
            _logger.error(
                "[Style-Bert-VITS2][synthesize:%s] worker_error requested_language=%r normalized_language=%r model_path=%s config_path=%s model_version=%r is_jp_extra=%s",
                request_id,
                output.get("requested_language"),
                output.get("normalized_language"),
                output.get("model_path"),
                output.get("config_path"),
                output.get("model_version"),
                output.get("is_jp_extra"),
            )
            raise RuntimeError(f"Style-Bert-VITS2 synth failed: {err}\n{tb}")

        b64 = output.get("audio_b64")
        if not b64:
            raise RuntimeError("Style-Bert-VITS2 synth failed: empty audio payload")
        _logger.info(
            "[Style-Bert-VITS2][synthesize:%s] success bytes=%d model=%s",
            request_id,
            len(b64),
            model,
        )
        return base64.b64decode(b64), "audio/wav"

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
        }
