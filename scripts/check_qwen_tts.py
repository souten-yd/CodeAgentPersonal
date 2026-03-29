#!/usr/bin/env python3
"""Qwen3-TTS health check.

This script validates qwen_tts import and model loading via
`Qwen3TTSModel.from_pretrained(...)`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-id",
        default=os.environ.get("QWEN3_TTS_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-0.6B-Base"),
        help="Qwen3-TTS model id to load",
    )
    args = parser.parse_args()

    report: dict[str, object] = {"ok": False}
    try:
        import qwen_tts
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        from qwen_tts import Qwen3TTSModel

        model = Qwen3TTSModel.from_pretrained(args.model_id)
        report = {
            "ok": True,
            "qwen_tts": getattr(qwen_tts, "__version__", "unknown"),
            "torch": torch.__version__,
            "torchaudio": torchaudio.__version__,
            "cuda_available": __import__("torch").cuda.is_available(),
            "check": "model_load",
            "model_id": args.model_id,
            "model_class": model.__class__.__name__,
        }
    except Exception as exc:
        report = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "hint": "Install/update with: pip install -U qwen-tts",
            "model_id": args.model_id,
        }

    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
