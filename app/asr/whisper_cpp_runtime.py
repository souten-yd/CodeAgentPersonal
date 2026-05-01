import json
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

import requests

MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin?download=true"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_whisper_cpp_dir() -> Path:
    return _repo_root() / "ca_data" / "bin" / "whisper.cpp-vulkan"


def _default_model_path() -> Path:
    return _repo_root() / "ca_data" / "asr_models" / "whisper_cpp" / "ggml-large-v3-turbo.bin"


def _detect_backend() -> str:
    backend = (os.environ.get("CODEAGENT_WHISPER_CPP_BACKEND") or "").strip().lower()
    if backend in {"vulkan", "cpu"}:
        return backend
    return "vulkan" if os.name == "nt" else "cpu"


def _invalid_ellipsis_path(v: str) -> bool:
    return "..." in v or "…" in v


def resolve_whisper_cpp_binary() -> Path | None:
    env_bin = (os.environ.get("CODEAGENT_WHISPER_CPP_BIN") or "").strip()
    if env_bin and not _invalid_ellipsis_path(env_bin):
        p = Path(env_bin)
        return p if p.exists() else None
    root = Path((os.environ.get("CODEAGENT_WHISPER_CPP_DIR") or "").strip() or _default_whisper_cpp_dir())
    if not root.exists():
        return None
    for name in ("whisper-cli.exe", "main.exe", "whisper.exe", "whisper-cli", "main", "whisper"):
        hits = list(root.rglob(name))
        if hits:
            return hits[0]
    return None


def resolve_whisper_cpp_server_binary() -> Path | None:
    root = Path((os.environ.get("CODEAGENT_WHISPER_CPP_DIR") or "").strip() or _default_whisper_cpp_dir())
    if not root.exists():
        return None
    for name in ("whisper-server.exe", "whisper-server"):
        hits = list(root.rglob(name))
        if hits:
            return hits[0]
    return None


def resolve_whisper_cpp_model() -> Path:
    return Path((os.environ.get("CODEAGENT_WHISPER_CPP_MODEL") or "").strip() or _default_model_path())


def resolve_ffmpeg_binary() -> Path | None:
    env_bin = (os.environ.get("CODEAGENT_FFMPEG_BIN") or "").strip()
    if env_bin:
        p = Path(env_bin)
        if p.exists():
            return p
    ffmpeg_root = _repo_root() / "ca_data" / "bin" / "ffmpeg"
    if ffmpeg_root.exists():
        for name in ("ffmpeg.exe", "ffmpeg"):
            hits = list(ffmpeg_root.rglob(name))
            if hits:
                return hits[0]
    sys_ffmpeg = shutil.which("ffmpeg")
    return Path(sys_ffmpeg) if sys_ffmpeg else None


def _ensure_wav(input_bytes: bytes, audio_format: str, temp_dir: Path) -> tuple[Path, float]:
    t0 = time.perf_counter()
    fmt = (audio_format or "wav").lower()
    src = temp_dir / f"input.{fmt}"
    src.write_bytes(input_bytes)
    if fmt == "wav":
        with wave.open(str(src), "rb"):
            pass
        return src, (time.perf_counter() - t0) * 1000
    ffmpeg = resolve_ffmpeg_binary()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed; non-wav input requires ffmpeg (webm/m4a/mp3 etc.)")
    out = temp_dir / "input.wav"
    cp = subprocess.run([str(ffmpeg), "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(out)], capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {cp.stderr.strip()[:400]}")
    return out, (time.perf_counter() - t0) * 1000


class WhisperCppServerRuntime:
    def __init__(self):
        self.lock = threading.RLock()
        self.proc = None
        self.server_url = "http://127.0.0.1:8178"
        self.loaded = False
        self.loading = False
        self.loaded_at = 0.0
        self.request_count = 0
        self.last_error = ""
        self.last_timings = {}
        self.download_status = "idle"
        self.actual_backend = ""

    def status(self) -> dict:
        model = resolve_whisper_cpp_model()
        server_bin = resolve_whisper_cpp_server_binary()
        env_bin = (os.environ.get("CODEAGENT_WHISPER_CPP_BIN") or "").strip()
        warnings = []
        if env_bin and _invalid_ellipsis_path(env_bin):
            warnings.append("invalid CODEAGENT_WHISPER_CPP_BIN contains ellipsis; fallback to auto discovery")
        return {
            "loaded": self.loaded,
            "loading": self.loading,
            "process_pid": self.proc.pid if self.proc and self.proc.poll() is None else None,
            "server_url": self.server_url,
            "model_path": str(model),
            "binary_path": str(server_bin) if server_bin else str(resolve_whisper_cpp_binary() or ""),
            "configured_backend": _detect_backend(),
            "actual_backend": self.actual_backend,
            "gpu_device": "",
            "model_exists": model.exists() and model.stat().st_size >= 1_000_000_000,
            "download_status": self.download_status,
            "last_error": self.last_error,
            "last_timings": self.last_timings,
            "loaded_at": self.loaded_at,
            "request_count": self.request_count,
            "persistent": bool(server_bin),
            "whisper_cpp_server_available": bool(server_bin),
            "warnings": warnings,
        }

    def ensure_model(self):
        model = resolve_whisper_cpp_model()
        if model.exists() and model.stat().st_size >= 1_000_000_000:
            return
        model.parent.mkdir(parents=True, exist_ok=True)
        part = model.with_suffix(model.suffix + ".part")
        self.download_status = "downloading"
        try:
            with requests.get(MODEL_URL, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(part, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            part.replace(model)
            self.download_status = "done"
        except Exception:
            self.download_status = "failed"
            raise

    def load(self, auto=False):
        with self.lock:
            if self.loaded and self.proc and self.proc.poll() is None:
                return self.status()
            self.loading = True
        t0 = time.perf_counter()
        try:
            self.ensure_model()
            server_bin = resolve_whisper_cpp_server_binary()
            if not server_bin:
                self.last_error = "whisper-server not found; fallback to cli"
                self.loading = False
                return self.status()
            model = resolve_whisper_cpp_model()
            port = int(os.environ.get("CODEAGENT_WHISPER_CPP_PORT", "8178"))
            self.server_url = f"http://127.0.0.1:{port}"
            self.proc = subprocess.Popen([str(server_bin), "-m", str(model), "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            deadline = time.time() + 120
            logs = []
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    break
                try:
                    r = requests.get(self.server_url + "/health", timeout=0.8)
                    if r.status_code < 500:
                        self.loaded = True
                        break
                except Exception:
                    pass
                if self.proc.stdout:
                    line = self.proc.stdout.readline().strip()
                    if line:
                        logs.append(line)
                time.sleep(0.25)
            blob = "\n".join(logs[-200:])
            if "Vulkan0" in blob:
                self.actual_backend = "Vulkan0"
            elif "ggml_vulkan" in blob:
                self.actual_backend = "ggml_vulkan"
            if not self.loaded:
                raise RuntimeError("whisper-server failed to become ready")
            self.loaded_at = time.time()
            self.last_timings["model_load_ms"] = (time.perf_counter() - t0) * 1000
            self.last_error = ""
            return self.status()
        finally:
            self.loading = False

    def unload(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
            self.proc = None
            self.loaded = False
            return self.status()

    def transcribe(self, audio_bytes: bytes, audio_format: str = "webm", language: str = "auto") -> dict:
        st = self.load(auto=True)
        if not st.get("persistent"):
            return transcribe_with_whisper_cpp(audio_bytes, audio_format, language)
        with tempfile.TemporaryDirectory(prefix="whisper_cpp_") as td:
            work = Path(td)
            wav_path, ff_ms = _ensure_wav(audio_bytes, audio_format, work)
            t0 = time.perf_counter()
            with open(wav_path, "rb") as f:
                files = {"file": ("audio.wav", f, "audio/wav")}
                data = {"language": language or "auto"}
                r = requests.post(self.server_url + "/inference", files=files, data=data, timeout=180)
                r.raise_for_status()
                payload = r.json()
            req_ms = (time.perf_counter() - t0) * 1000
            self.request_count += 1
            self.last_timings = {"ffmpeg_ms": ff_ms, "server_request_ms": req_ms, "total_ms": ff_ms + req_ms}
            return {
                "text": (payload.get("text") or "").strip(),
                "language": payload.get("language", language),
                "duration": 0.0,
                "engine": "whisper_cpp",
                "backend": _detect_backend(),
                "actual_backend": self.actual_backend,
                "loaded": self.loaded,
                "metrics": self.last_timings,
            }


WHISPER_CPP_SERVER_RUNTIME = WhisperCppServerRuntime()


def transcribe_with_whisper_cpp(audio_bytes: bytes, audio_format: str = "webm", language: str = "auto") -> dict:
    binary = resolve_whisper_cpp_binary()
    if not binary:
        raise RuntimeError("whisper.cpp binary is not found. Set CODEAGENT_WHISPER_CPP_BIN or install to ca_data/bin/whisper.cpp-vulkan")
    model = resolve_whisper_cpp_model()
    if not model.exists():
        raise RuntimeError(f"whisper.cpp ggml model is required and not found: {model}")
    with tempfile.TemporaryDirectory(prefix="whisper_cpp_cli_") as td:
        work = Path(td)
        wav_path, _ = _ensure_wav(audio_bytes, audio_format, work)
        cmd = [str(binary), "-m", str(model), "-f", str(wav_path), "-l", (language or "auto"), "-np", "-otxt", "-of", str(work / "result")]
        extra = (os.environ.get("CODEAGENT_WHISPER_CPP_EXTRA_ARGS") or "").strip()
        if extra:
            cmd.extend(shlex.split(extra))
        cp = subprocess.run(cmd, capture_output=True, text=True)
        if cp.returncode != 0:
            raise RuntimeError(f"whisper.cpp failed: {cp.stderr.strip()[:600]}")
        txt = ""
        out = work / "result.txt"
        if out.exists():
            txt = " ".join(out.read_text(encoding="utf-8", errors="ignore").split())
        return {"text": txt, "language": language, "duration": 0.0, "engine": "whisper_cpp", "backend": _detect_backend(), "loaded": False}
