#!/usr/bin/env python3
"""Qwen3-TTS health check.

Checks:
- import qwen_tts
- sox command availability
- flash_attn import availability
- Qwen3TTSModel.from_pretrained with preferred attention backend fallback
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import traceback


def _to_dtype_name(dtype: object) -> str:
    return str(dtype)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-id",
        default=os.environ.get("QWEN3_TTS_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-0.6B-Base"),
        help="Qwen3-TTS model id to load",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Set local_files_only=True when loading the model",
    )
    parser.add_argument(
        "--full-load",
        action="store_true",
        help="Run full model load verification (slow/heavy). Default is import-only lightweight checks.",
    )
    args = parser.parse_args()

    report: dict[str, object] = {
        "ok": False,
        "model_id": args.model_id,
        "qwen3tts_sox_available": shutil.which("sox") is not None,
        "qwen3tts_flash_attn_available": False,
        "qwen3tts_attn_backend": "",
        "qwen3tts_dtype": "",
        "qwen3tts_device": "",
    }

    try:
        import qwen_tts
        import torch
        import torchaudio  # noqa: F401
        from qwen_tts import Qwen3TTSModel

        flash_attn_available = False
        try:
            import flash_attn  # noqa: F401
            flash_attn_available = True
        except Exception:
            flash_attn_available = False

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        selected_attn = "flash_attention_2" if device == "cuda" else "sdpa"
        if device == "cuda" and not flash_attn_available:
            selected_attn = "sdpa"

        report.update(
            {
                "ok": True,
                "qwen_tts": getattr(qwen_tts, "__version__", "unknown"),
                "torch": torch.__version__,
                "torchaudio": torchaudio.__version__,
                "cuda_available": torch.cuda.is_available(),
                "qwen3tts_flash_attn_available": flash_attn_available,
                "qwen3tts_attn_backend": selected_attn,
                "qwen3tts_dtype": _to_dtype_name(dtype),
                "qwen3tts_device": device,
                "check_mode": "full_load" if args.full_load else "import_only",
            }
        )
        if args.full_load:
            attn_candidates = ["flash_attention_2", "sdpa", "eager"] if device == "cuda" else ["sdpa", "eager"]
            if device == "cuda" and not flash_attn_available:
                attn_candidates = ["sdpa", "eager"]
            model = None
            selected_attn = ""
            load_errors: list[str] = []
            for attn_impl in attn_candidates:
                try:
                    model = Qwen3TTSModel.from_pretrained(
                        args.model_id,
                        device_map="cuda:0" if device == "cuda" else "cpu",
                        dtype=dtype,
                        attn_implementation=attn_impl,
                        local_files_only=args.local_files_only,
                    )
                    selected_attn = attn_impl
                    break
                except Exception as exc:
                    load_errors.append(f"{attn_impl}: {type(exc).__name__}: {exc}")
            if model is None:
                raise RuntimeError("; ".join(load_errors) if load_errors else "failed to load model")
            report.update(
                {
                    "qwen3tts_attn_backend": selected_attn,
                    "model_class": model.__class__.__name__,
                    "full_load_ok": True,
                }
            )
    except Exception as exc:
        report.update(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "hint": (
                    "Install/update with: pip install -U qwen-tts && "
                    "python -m pip install -U flash-attn --no-build-isolation"
                ),
            }
        )

    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
