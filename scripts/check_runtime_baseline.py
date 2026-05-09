#!/usr/bin/env python3
"""Lightweight runtime baseline checks for Runpod/CUDA recovery.

This script intentionally calls only lightweight status/diagnostic endpoints.
It does not force LLM generation, ASR transcription, or TTS synthesis.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


ENDPOINTS = {
    "health": "/health",
    "cuda_debug": "/runtime/cuda-debug",
    "audio_runtime_debug": "/audio/runtime/debug",
    "voice_status": "/voice/status",
    "models_db_status": "/models/db/status",
    "llm_ctx": "/llm/ctx",
    "llm_props": "/llm/props",
    "nexus_web_status": "/nexus/web/status",
    "echo_save_status": "/echo/save-status",
}


def fetch_json(base_url: str, path: str, timeout: float) -> tuple[int, Any]:
    url = base_url.rstrip("/") + path
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local operator tool
        status = getattr(response, "status", response.getcode())
        payload = response.read().decode("utf-8")
    try:
        return status, json.loads(payload)
    except json.JSONDecodeError:
        return status, {"raw": payload}


def boolish(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "1", "yes", "ok", "ready"}


def check_payloads(payloads: dict[str, tuple[int, Any]]) -> list[CheckResult]:
    results: list[CheckResult] = []

    for name, (status, _body) in payloads.items():
        results.append(CheckResult(name, status == 200, f"HTTP {status}"))

    health = payloads.get("health", (0, {}))[1]
    health_ok = boolish(health.get("ok")) or health.get("status") in {"ok", "healthy"}
    results.append(CheckResult("health_ok", health_ok, f"health={health}"))

    cuda = payloads.get("cuda_debug", (0, {}))[1]
    if "runpod_detected" in cuda:
        results.append(
            CheckResult(
                "runpod_detected",
                cuda.get("runpod_detected") is True,
                f"runpod_detected={cuda.get('runpod_detected')}",
            )
        )
    else:
        results.append(CheckResult("runpod_detected", False, "missing runpod_detected"))

    if "intended_backend" in cuda:
        results.append(
            CheckResult(
                "intended_backend_cuda",
                cuda.get("intended_backend") == "cuda",
                f"intended_backend={cuda.get('intended_backend')}",
            )
        )
    else:
        results.append(CheckResult("intended_backend_cuda", False, "missing intended_backend"))

    model_status = payloads.get("models_db_status", (0, {}))[1]
    llm_ctx = payloads.get("llm_ctx", (0, {}))[1]
    llm_props = payloads.get("llm_props", (0, {}))[1]
    explainable_model = any(
        str(value).lower() in {"loading", "ready", "loaded", "ok", "unavailable"}
        for body in (model_status, llm_ctx, llm_props)
        for value in (body.values() if isinstance(body, dict) else [])
    ) or bool(llm_ctx) or bool(llm_props)
    results.append(
        CheckResult(
            "llm_status_explainable",
            explainable_model,
            "LLM ready/loading is not forced; ctx/props/model status must be explainable",
        )
    )

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payloads: dict[str, tuple[int, Any]] = {}
    fetch_errors: list[CheckResult] = []

    for name, path in ENDPOINTS.items():
        try:
            payloads[name] = fetch_json(args.base_url, path, args.timeout)
        except HTTPError as exc:
            payloads[name] = (exc.code, {"error": str(exc)})
        except (OSError, URLError) as exc:
            fetch_errors.append(CheckResult(name, False, repr(exc)))

    results = fetch_errors + check_payloads(payloads)
    ok = all(result.ok for result in results)

    if args.json:
        print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
    else:
        for result in results:
            mark = "OK" if result.ok else "FAIL"
            print(f"[{mark}] {result.name}: {result.detail}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
