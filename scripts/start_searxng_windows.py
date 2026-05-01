#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _probe(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
        return False


def main() -> int:
    if os.name != "nt":
        print("[SearXNG][windows] Windows専用です。")
        return 0

    base_dir = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    bind = env.get("SEARXNG_BIND_ADDRESS", "127.0.0.1").strip() or "127.0.0.1"
    port = env.get("SEARXNG_PORT", "8088").strip() or "8088"
    health_url = f"http://{bind}:{port}/search?format=json&q=healthcheck"

    if _probe(health_url):
        print(f"[SearXNG][windows] Already running: {health_url}")
        return 0

    repo_dir = Path(env.get("CODEAGENT_SEARXNG_REPO_DIR", str(base_dir / "third_party" / "searxng"))).expanduser()
    venv_dir = Path(env.get("CODEAGENT_SEARXNG_VENV_DIR", str(base_dir / "search_envs" / "searxng"))).expanduser()
    config_dir = Path(env.get("CODEAGENT_SEARXNG_CONFIG_DIR", str(base_dir / "ca_data" / "searxng"))).expanduser()
    log_file = Path(env.get("CODEAGENT_SEARXNG_LOG_FILE", str(config_dir / "searxng.log"))).expanduser()
    settings_file = config_dir / "settings.yml"
    py_exe = venv_dir / "Scripts" / "python.exe"

    if not py_exe.exists():
        print("[SearXNG][windows][WARN] venv python not found. Run scripts/setup_searxng_windows.py")
        return 0

    env["SEARXNG_SETTINGS_PATH"] = str(settings_file)
    config_dir.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    commands: list[tuple[list[str], Path]] = []
    webapp_file = repo_dir / "searx" / "webapp.py"
    if webapp_file.exists():
        commands.append(([str(py_exe), "searx/webapp.py"], repo_dir))
    commands.append(([str(py_exe), "-m", "searx.webapp"], repo_dir if repo_dir.exists() else base_dir))

    with log_file.open("a", encoding="utf-8") as log:
        proc = None
        for cmd, cwd in commands:
            print("[SearXNG][windows] Starting:", " ".join(cmd), f"(cwd={cwd})")
            try:
                proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            except Exception as exc:
                print(f"[SearXNG][windows][WARN] failed to start candidate: {exc}")
                proc = None
                continue

            for _ in range(8):
                if _probe(health_url):
                    print(f"[SearXNG][windows] Ready: {health_url}")
                    return 0
                if proc.poll() is not None:
                    break
                time.sleep(1)

            if proc.poll() is None:
                proc.terminate()
            print("[SearXNG][windows][WARN] start candidate failed health probe; trying next candidate.")

    print("[SearXNG][windows][WARN] failed to start SearXNG. Check log:", log_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
