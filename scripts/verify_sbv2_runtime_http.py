#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_MODEL = "koharune-ami"
DEFAULT_TEXT = "これはStyle-Bert-VITS2の動作確認です。"


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    started = time.perf_counter()
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        _join_url(base_url, path),
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                data = {"raw": raw.decode("utf-8", errors="replace")[:2000]}
            return {
                "ok": 200 <= int(resp.status) < 300,
                "status": int(resp.status),
                "elapsed_ms": elapsed_ms,
                "data": data,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {"raw": raw.decode("utf-8", errors="replace")[:2000]}
        return {
            "ok": False,
            "status": int(exc.code),
            "elapsed_ms": elapsed_ms,
            "data": data,
            "error": str(exc),
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "ok": False,
            "status": 0,
            "elapsed_ms": elapsed_ms,
            "data": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def _summarize_policy(data: dict[str, Any]) -> dict[str, Any]:
    policy = data.get("sbv2_runtime_policy") or {}
    if not isinstance(policy, dict):
        return {}

    allowed_keys = [
        "engine",
        "default_model",
        "device",
        "runtime_profile",
        "prefer_safetensors",
        "allow_onnx",
        "prefer_onnx",
        "force_pytorch_jit_zero",
        "dummy_warmup_enabled",
        "import_time_side_effects_allowed",
    ]
    return {key: policy.get(key) for key in allowed_keys if key in policy}


def _summarize_synthesize(data: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ["ok", "engine", "model", "duration", "elapsed_ms", "audio_format"]:
        if key in data:
            summary[key] = data.get(key)

    audio_b64 = data.get("audio_base64") or data.get("audio")
    if isinstance(audio_b64, str):
        summary["audio_base64_chars"] = len(audio_b64)
        try:
            summary["audio_bytes"] = len(base64.b64decode(audio_b64, validate=False))
        except Exception:
            summary["audio_bytes"] = None

    if "error" in data:
        summary["error"] = str(data.get("error"))[:1000]
    if "detail" in data:
        summary["detail"] = str(data.get("detail"))[:1000]
    return summary


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    report: dict[str, Any] = {
        "script": "verify_sbv2_runtime_http",
        "base_url": args.base_url,
        "model": args.model,
        "device": args.device or "",
        "steps": {},
        "summary": {
            "ok": False,
            "policy_ok": False,
            "prepare_ok": False,
            "synthesize_ok": False,
        },
    }

    debug = _request_json(args.base_url, "/audio/runtime/debug", timeout=args.timeout)
    report["steps"]["audio_runtime_debug"] = debug
    debug_data = debug.get("data") if isinstance(debug.get("data"), dict) else {}
    debug_policy = _summarize_policy(debug_data)
    report["summary"]["debug_policy"] = debug_policy

    prepare_payload: dict[str, Any] = {"model": args.model}
    if args.device:
        prepare_payload["device"] = args.device

    prepare = _request_json(
        args.base_url,
        "/api/tts/style-bert-vits2/prepare",
        method="POST",
        payload=prepare_payload,
        timeout=args.timeout,
    )
    report["steps"]["prepare"] = prepare
    prepare_data = prepare.get("data") if isinstance(prepare.get("data"), dict) else {}
    prepare_policy = _summarize_policy(prepare_data)
    report["summary"]["prepare_policy"] = prepare_policy

    synth_payload: dict[str, Any] = {
        "engine": "style_bert_vits2",
        "model": args.model,
        "text": args.text,
    }
    if args.device:
        synth_payload["device"] = args.device

    synthesize = _request_json(
        args.base_url,
        "/tts/synthesize",
        method="POST",
        payload=synth_payload,
        timeout=args.timeout,
    )
    report["steps"]["synthesize"] = synthesize
    synth_data = synthesize.get("data") if isinstance(synthesize.get("data"), dict) else {}
    report["summary"]["synthesize"] = _summarize_synthesize(synth_data)

    report["summary"]["policy_ok"] = bool(debug_policy or prepare_policy)
    report["summary"]["prepare_ok"] = bool(prepare.get("ok"))
    report["summary"]["synthesize_ok"] = bool(synthesize.get("ok"))
    report["summary"]["ok"] = bool(
        report["summary"]["policy_ok"]
        and report["summary"]["prepare_ok"]
        and report["summary"]["synthesize_ok"]
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SBV2 runtime via HTTP endpoints.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", default="")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    report = build_report(args)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")

    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
