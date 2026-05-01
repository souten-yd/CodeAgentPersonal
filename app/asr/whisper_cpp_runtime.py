import json
import os
import shlex
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path


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


def resolve_whisper_cpp_binary() -> Path | None:
    env_bin = (os.environ.get("CODEAGENT_WHISPER_CPP_BIN") or "").strip()
    if env_bin:
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


def _default_threads() -> int:
    cpu = os.cpu_count() or 4
    return min(8, max(4, (cpu + 1) // 2))


def _ensure_wav(input_bytes: bytes, audio_format: str, temp_dir: Path) -> Path:
    fmt = (audio_format or "wav").lower()
    src = temp_dir / f"input.{fmt}"
    src.write_bytes(input_bytes)
    if fmt == "wav":
        with wave.open(str(src), "rb"):
            pass
        return src
    ffmpeg = resolve_ffmpeg_binary()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed; non-wav input requires ffmpeg (webm/m4a/mp3 etc.)")
    out = temp_dir / "input.wav"
    cmd = [str(ffmpeg), "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(out)]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {cp.stderr.strip()[:400]}")
    return out


def _extract_text(work_dir: Path, stdout: str) -> tuple[str, str]:
    json_files = list(work_dir.glob("*.json"))
    if json_files:
        try:
            data = json.loads(json_files[0].read_text(encoding="utf-8", errors="ignore"))
            text = data.get("text") or "".join((s.get("text", "") for s in data.get("segments", [])))
            return (" ".join(text.split())).strip(), data.get("language", "auto")
        except Exception:
            pass
    txt_files = list(work_dir.glob("*.txt"))
    if txt_files:
        return (" ".join(txt_files[0].read_text(encoding="utf-8", errors="ignore").split())).strip(), "auto"
    return (" ".join((stdout or "").split())).strip(), "auto"


def transcribe_with_whisper_cpp(audio_bytes: bytes, audio_format: str = "webm", language: str = "auto") -> dict:
    binary = resolve_whisper_cpp_binary()
    if not binary:
        raise RuntimeError("whisper.cpp binary is not found. Set CODEAGENT_WHISPER_CPP_BIN or install to ca_data/bin/whisper.cpp-vulkan")
    model = resolve_whisper_cpp_model()
    if not model.exists():
        raise RuntimeError(f"whisper.cpp ggml model is required and not found: {model}")

    with tempfile.TemporaryDirectory(prefix="whisper_cpp_") as td:
        work = Path(td)
        wav_path = _ensure_wav(audio_bytes, audio_format, work)
        threads = int((os.environ.get("CODEAGENT_WHISPER_CPP_THREADS") or _default_threads()))
        output_base = work / "result"
        cmd = [str(binary), "-m", str(model), "-f", str(wav_path), "-l", (language or "auto"), "-np", "-t", str(threads), "-of", str(output_base), "-otxt"]
        extra = (os.environ.get("CODEAGENT_WHISPER_CPP_EXTRA_ARGS") or "").strip()
        if extra:
            cmd.extend(shlex.split(extra))
        cp = subprocess.run(cmd, capture_output=True, text=True)
        if cp.returncode != 0:
            raise RuntimeError(f"whisper.cpp failed: {cp.stderr.strip()[:600]}")
        text, detected_language = _extract_text(work, cp.stdout)
        return {
            "text": text,
            "language": detected_language if language == "auto" else language,
            "duration": 0.0,
            "engine": "whisper_cpp",
            "backend": _detect_backend(),
            "binary": str(binary),
            "model": str(model),
        }
