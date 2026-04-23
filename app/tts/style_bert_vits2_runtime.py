from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .engine_registry import TTSEngineRuntime

_STYLE_BERT_VITS2_DEFAULT_REPO_DIR = "/app/Style-Bert-VITS2"
_STYLE_BERT_VITS2_DEFAULT_VENV_DIR = "/app/Style-Bert-VITS2/.venv"
_STYLE_BERT_VITS2_DEFAULT_BASE_DIR = "/workspace/ca_data/tts/style_bert_vits2"
_STYLE_BERT_VITS2_DEFAULT_MODELS_DIR = os.path.join(_STYLE_BERT_VITS2_DEFAULT_BASE_DIR, "models")
_STYLE_BERT_VITS2_WEIGHT_EXTENSIONS = (".safetensors", ".pth", ".pt", ".onnx")


def _repo_dir() -> str:
    return os.environ.get("CODEAGENT_STYLE_BERT_VITS2_REPO_DIR", _STYLE_BERT_VITS2_DEFAULT_REPO_DIR)


def _venv_dir() -> str:
    return os.environ.get("CODEAGENT_STYLE_BERT_VITS2_VENV_DIR", _STYLE_BERT_VITS2_DEFAULT_VENV_DIR)


def _python_path() -> str:
    return os.path.join(_venv_dir(), "bin", "python")


def _models_dir() -> str:
    return os.environ.get("CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR", _STYLE_BERT_VITS2_DEFAULT_MODELS_DIR)


def _resolve_model_paths(model_id: str) -> tuple[str, str, str]:
    model = (model_id or "").strip()
    if not model:
        raise ValueError("model required when engine=style_bert_vits2")

    model_dir = Path(_models_dir()) / model
    if not model_dir.is_dir():
        raise RuntimeError(f"Style-Bert-VITS2 model not found: {model}")

    config_path = model_dir / "config.json"
    style_path = model_dir / "style_vectors.npy"
    if not config_path.is_file():
        raise RuntimeError(f"Style-Bert-VITS2 config.json missing: {config_path}")
    if not style_path.is_file():
        raise RuntimeError(f"Style-Bert-VITS2 style_vectors.npy missing: {style_path}")

    weight_path: Path | None = None
    for candidate in sorted(model_dir.rglob("*")):
        if candidate.is_file() and candidate.suffix.lower() in _STYLE_BERT_VITS2_WEIGHT_EXTENSIONS:
            weight_path = candidate
            break
    if weight_path is None:
        raise RuntimeError(f"Style-Bert-VITS2 weight file missing in: {model_dir}")

    return str(weight_path), str(config_path), str(style_path)


def _pick_device(req: dict) -> str:
    requested = str(req.get("device", "")).strip().lower()
    if requested in {"cpu", "cuda", "mps"}:
        return requested
    return "cuda"


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
        text = str(req.get("text", "")).strip()
        if not text:
            raise ValueError("text required")

        py = _python_path()
        if not os.path.isfile(py):
            raise RuntimeError(f"Style-Bert-VITS2 python not found: {py}")

        model = str(req.get("model", "")).strip()
        model_path, config_path, style_vec_path = _resolve_model_paths(model)
        device = _pick_device(req)

        payload = {
            "text": text,
            "model_path": model_path,
            "config_path": config_path,
            "style_vec_path": style_vec_path,
            "device": device,
            "speaker_id": _to_optional_int(req.get("speaker_id"), 0),
            "speaker": str(req.get("speaker_name", "")).strip() or str(req.get("speaker", "")).strip() or None,
            "style": str(req.get("style", "")).strip() or "Neutral",
            "style_weight": _to_optional_float(req.get("style_weight"), 1.0),
            "sdp_ratio": _to_optional_float(req.get("sdp_ratio"), 0.2),
            "noise": _to_optional_float(req.get("noise"), 0.6),
            "noise_w": _to_optional_float(req.get("noise_w"), 0.8),
            "length": _to_optional_float(req.get("length"), 1.0),
            "line_split": bool(req.get("line_split", True)),
            "split_interval": _to_optional_float(req.get("split_interval"), 0.5),
            "assist_text": str(req.get("assist_text", "")).strip() or None,
            "assist_text_weight": _to_optional_float(req.get("assist_text_weight"), 1.0),
        }

        worker_code = r'''
import base64
import io
import json
import traceback
import wave

import numpy as np
from style_bert_vits2.tts_model import TTSModel

req = json.loads(input())
try:
    model = TTSModel(
        model_path=req["model_path"],
        config_path=req["config_path"],
        style_vec_path=req["style_vec_path"],
        device=req.get("device", "cuda"),
    )
    kwargs = {
        "text": req["text"],
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

    speaker = req.get("speaker")
    if speaker:
        kwargs["speaker"] = speaker
    else:
        kwargs["speaker_id"] = int(req.get("speaker_id", 0))

    sample_rate, audio = model.infer(**kwargs)
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
    print(json.dumps({"ok": True, "audio_b64": base64.b64encode(wav_bytes).decode("ascii")}))
except Exception as e:
    print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}))
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
            raise RuntimeError(f"Style-Bert-VITS2 synth failed: {err}\n{tb}")

        b64 = output.get("audio_b64")
        if not b64:
            raise RuntimeError("Style-Bert-VITS2 synth failed: empty audio payload")
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
