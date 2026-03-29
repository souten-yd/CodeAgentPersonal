#!/usr/bin/env python3
"""Minimal Qwen3-TTS health check (no model download required)."""

from __future__ import annotations

import json
import sys


def main() -> int:
    report: dict[str, object] = {"ok": False}
    try:
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        import qwen_tts  # noqa: F401
        import transformers

        from transformers import AutoProcessor, AutoModel  # noqa: F401

        report = {
            "ok": True,
            "torch": __import__("torch").__version__,
            "torchaudio": __import__("torchaudio").__version__,
            "transformers": transformers.__version__,
            "cuda_available": __import__("torch").cuda.is_available(),
            "check": "import_only",
            "note": "No model download performed.",
        }
    except Exception as exc:
        report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
