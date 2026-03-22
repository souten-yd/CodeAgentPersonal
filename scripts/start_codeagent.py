#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AUTO_MODE_KEY = "auto"
AUTO_MODE_NUM = "1"


def detect_runpod() -> bool:
    return bool(os.environ.get("RUNPOD_POD_ID") or os.environ.get("RUNPOD_API_KEY"))


def detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def copy_ui(base_dir: Path) -> None:
    src = base_dir / "ui.html"
    dst = base_dir / "ui" / "index.html"
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("[UI] ui.html copied")


def request_json(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def request_status(url: str, timeout: float = 2.0) -> int | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None


def post_json(url: str, payload: dict, timeout: float = 5.0) -> int | None:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None


def wait_http_200(url: str, timeout_sec: int, label: str) -> bool:
    waited = 0
    while waited < timeout_sec:
        status = request_status(url)
        if status == 200:
            print(f"[OK] {label} ready")
            return True
        time.sleep(2)
        waited += 2
        print(f"  {label} loading... {waited}s")
    return False


def choose_mode() -> tuple[str, str]:
    return AUTO_MODE_KEY, AUTO_MODE_NUM


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CodeAgent launcher (cross-platform)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--primary-port", type=int, default=8080)
    parser.add_argument("--api-timeout", type=int, default=30)
    parser.add_argument("--llm-timeout", type=int, default=180)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent.parent
    runpod = detect_runpod()

    mode_key, mode_num = choose_mode()

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env["CODEAGENT_LLM_PLANNER"] = f"http://127.0.0.1:{args.primary_port}/v1/chat/completions"
    env["CODEAGENT_LLM_EXECUTOR"] = f"http://127.0.0.1:{args.primary_port}/v1/chat/completions"
    env["CODEAGENT_LLM_CHAT"] = f"http://127.0.0.1:{args.primary_port}/v1/chat/completions"
    env["CODEAGENT_LLM_LIGHT"] = f"http://127.0.0.1:{args.primary_port}/v1/chat/completions"
    env["CODEAGENT_LLM_MODE"] = mode_num

    print("==============================================")
    print(" CodeAgent Launcher")
    print(f" Mode    : {mode_key}")
    print(f" Runpod  : {'yes' if runpod else 'no'}")
    print("==============================================")

    copy_ui(base_dir)

    uvicorn_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--log-level",
        "info",
        "--app-dir",
        str(base_dir),
    ]
    print(f"[FastAPI] Starting: {' '.join(uvicorn_cmd)}")
    proc = subprocess.Popen(uvicorn_cmd, cwd=base_dir, env=env)

    try:
        api_ok = wait_http_200(f"http://127.0.0.1:{args.port}/health", args.api_timeout, "FastAPI")
        if not api_ok:
            print("[ERROR] FastAPI did not become ready.")
            proc.terminate()
            return 1

        status = request_json(f"http://127.0.0.1:{args.port}/models/db/status") or {}
        db_exists = bool(status.get("db_exists"))
        db_total = int(status.get("total", 0) or 0)
        benchmarked_total = int(status.get("benchmarked", 0) or 0)

        if db_exists and db_total > 0 and benchmarked_total > 0:
            print(
                f"[ModelDB] Found {db_total} model(s), benchmarked={benchmarked_total}. "
                "Requesting default LLM load..."
            )
            post_json(f"http://127.0.0.1:{args.port}/model/auto-load", {"reason": "launcher_py"})
            llm_ok = wait_http_200(f"http://127.0.0.1:{args.primary_port}/health", args.llm_timeout, "LLM")
            if not llm_ok:
                print(f"[WARN] LLM is still not ready after {args.llm_timeout}s.")
        elif db_exists and db_total > 0:
            print(
                f"[WAIT] model_db has {db_total} model(s) but benchmarked={benchmarked_total}. "
                "Skipping auto planner load until benchmark completes via UI workflow."
            )
        else:
            print("[WAIT] model_db is missing or empty. Skipping LLM startup wait.")

        lan_ip = detect_lan_ip()
        print("\n==============================================")
        print(" CodeAgent ready!")
        print(f"  Local : http://localhost:{args.port}/")
        print(f"  LAN   : http://{lan_ip}:{args.port}/")
        print(f"  Mode  : {mode_num}  Profile: {mode_key}")
        print("==============================================")

        return proc.wait()
    except KeyboardInterrupt:
        print("\n[Launcher] Stopping...")
        proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
