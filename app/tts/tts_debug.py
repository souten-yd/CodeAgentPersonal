from __future__ import annotations

import json
import os
import traceback
from pathlib import Path


def _is_runpod_runtime() -> bool:
    has_workspace = Path("/workspace").is_dir()
    has_runpod_env = bool(os.environ.get("RUNPOD_POD_ID") or os.environ.get("RUNPOD_API_KEY"))
    forced = os.environ.get("CODEAGENT_RUNTIME", "").strip().lower()
    if forced in {"runpod", "rp"}:
        return has_workspace or has_runpod_env
    if forced in {"local", "default", "docker"}:
        return False
    return has_workspace or has_runpod_env


def resolve_tts_debug_log_path() -> Path:
    explicit = os.environ.get("CODEAGENT_TTS_DEBUG_LOG_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    ca_data_dir = os.environ.get("CODEAGENT_CA_DATA_DIR", "").strip()
    if ca_data_dir:
        return Path(ca_data_dir).expanduser() / "tts_debug.jsonl"

    if _is_runpod_runtime():
        return Path("/workspace/ca_data/tts_debug.jsonl")

    return Path(__file__).resolve().parents[2] / "ca_data" / "tts_debug.jsonl"


def read_recent_tts_debug_entries(limit: int = 20) -> list[dict]:
    try:
        n = max(1, min(int(limit), 500))
    except Exception:
        n = 20

    path = resolve_tts_debug_log_path()
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as f:
            rows = [ln.strip() for ln in f if ln.strip()]
        out: list[dict] = []
        for ln in rows[-n:]:
            try:
                out.append(json.loads(ln))
            except Exception:
                out.append({"ok": False, "error": "invalid_jsonl_entry", "raw": ln[:500]})
        return out
    except Exception as e:
        return [{"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}]


def write_tts_debug_entry(entry: dict) -> None:
    try:
        path = resolve_tts_debug_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(entry or {}), ensure_ascii=False) + "\n")
    except Exception:
        return
