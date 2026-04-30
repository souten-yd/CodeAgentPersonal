#!/usr/bin/env python3
from __future__ import annotations

import collections
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tts.style_bert_vits2_runtime import StyleBertVITS2Runtime


class _FakeStdin:
    def __init__(self) -> None:
        self.buffer: list[str] = []

    def write(self, text: str) -> None:
        self.buffer.append(text)

    def flush(self) -> None:
        return


class _FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0)


class _FakeProc:
    def __init__(self, stdout_lines: list[str]) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(stdout_lines)


def _check_send_once_handles_noise() -> dict:
    runtime = StyleBertVITS2Runtime()
    runtime._ensure_worker_started = lambda: None  # type: ignore[method-assign]
    runtime._workers = 1
    runtime._worker_procs = [_FakeProc(["download 10%\n", '{"ok": true, "cache_hit": true}\n'])]  # type: ignore[list-item]
    runtime._worker_stderr_tails = [collections.deque(maxlen=16)]
    out = runtime._send_once_to_worker({"text": "hello"})
    return {"ok": bool(out.get("ok")), "cache_hit": bool(out.get("cache_hit"))}


def _check_static_guards() -> dict:
    runtime_src = (ROOT / "app/tts/style_bert_vits2_runtime.py").read_text(encoding="utf-8")
    main_src = (ROOT / "main.py").read_text(encoding="utf-8")

    ui_src = (ROOT / "ui.html").read_text(encoding="utf-8")
    return {
        "worker_stdout_redirected": "sys.stdout = sys.stderr" in runtime_src,
        "worker_emit_response": "def emit_response" in runtime_src,
        "models_filter_ignores_cache": "_STYLE_BERT_VITS2_IGNORED_MODEL_DIRS" in main_src and '".cache"' in main_src,
        "protocol_error_to_500": "worker_protocol_error" in main_src,
        "ui_engine_fixed": "return 'style_bert_vits2';" in ui_src,
        "main_tts_api_forces_engine": 'engine = "style_bert_vits2"' in main_src,
    }


def main() -> int:
    report = {
        "A_send_once_noise_guard": _check_send_once_handles_noise(),
        "B_C_D_static_guards": _check_static_guards(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
