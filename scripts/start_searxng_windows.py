#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CONTAINER_NAME = "codeagent-searxng"
IMAGE = "searxng/searxng:latest"
HOST_BIND = "127.0.0.1"
HOST_PORT = "8088"
CONTAINER_PORT = "8080"


def _probe(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
        return False


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def _log(log_file: Path, message: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as fp:
        fp.write(f"{message}\n")


def ensure_settings(config_dir: Path) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    settings_file = config_dir / "settings.yml"
    if settings_file.exists():
        return settings_file
    secret = secrets.token_urlsafe(32)
    body = (
        "use_default_settings: true\n\n"
        "server:\n"
        f"  secret_key: \"{secret}\"\n"
        "  bind_address: \"0.0.0.0\"\n"
        "  port: 8080\n"
        "  base_url: false\n\n"
        "search:\n"
        "  safe_search: 0\n\n"
        "ui:\n"
        "  static_use_hash: true\n"
    )
    settings_file.write_text(body, encoding="utf-8")
    return settings_file


def try_install_docker(base_dir: Path, log_file: Path) -> bool:
    winget = _run(["where", "winget"])
    if winget.returncode == 0:
        _log(log_file, "[Docker] Trying winget install Docker Desktop")
        install = _run(
            [
                "winget",
                "install",
                "-e",
                "--id",
                "Docker.DockerDesktop",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ]
        )
        if install.returncode == 0:
            return True
    ps1 = base_dir / "scripts" / "install_docker_windows.ps1"
    if ps1.exists():
        fallback = _run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps1)])
        return fallback.returncode == 0
    _log(log_file, "[Docker][WARN] Docker is not installed. Install Docker Desktop manually.")
    return False


def ensure_docker_engine(log_file: Path) -> bool:
    info = _run(["docker", "info"])
    if info.returncode == 0:
        return True
    _log(log_file, "[Docker] Engine unavailable. Trying to start Docker Desktop.")
    _run(["powershell", "-Command", 'Start-Process "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"'])
    for _ in range(30):
        if _run(["docker", "info"]).returncode == 0:
            return True
        time.sleep(2)
    _log(
        log_file,
        "[Docker][WARN] Docker Engine is not ready. Start Docker Desktop and accept terms, then re-run start.bat.",
    )
    return False


def _is_windows() -> bool:
    return os.name == "nt"


def main() -> int:
    if not _is_windows():
        return 0
    base_dir = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    config_dir = Path(env.get("CODEAGENT_SEARXNG_CONFIG_DIR", str(base_dir / "ca_data" / "searxng"))).expanduser()
    log_file = Path(env.get("CODEAGENT_SEARXNG_LOG_FILE", str(config_dir / "searxng.log"))).expanduser()
    searx_base = (env.get("NEXUS_SEARXNG_URL", "http://127.0.0.1:8088").strip() or "http://127.0.0.1:8088").rstrip("/")
    health_url = f"{searx_base}/search?format=json&q=healthcheck"

    if _probe(health_url):
        print("SearXNG already running")
        return 0

    if _run(["docker", "--version"]).returncode != 0 and not try_install_docker(base_dir, log_file):
        return 0

    if not ensure_docker_engine(log_file):
        return 0

    ensure_settings(config_dir)
    mount_dir = str(config_dir.resolve())
    container = _run(["docker", "inspect", CONTAINER_NAME])
    exists = container.returncode == 0
    if exists:
        data = json.loads(container.stdout or "[]")
        state = (((data[0] if data else {}).get("State") or {}).get("Status") or "").lower()
        ports = json.dumps(((data[0] if data else {}).get("HostConfig") or {}).get("PortBindings") or {})
        binds = json.dumps(((data[0] if data else {}).get("HostConfig") or {}).get("Binds") or [])
        expected_bind = f"{mount_dir}:/etc/searxng"
        recreate = (expected_bind not in binds) or ("8088" not in ports)
        if recreate:
            _run(["docker", "rm", "-f", CONTAINER_NAME])
            exists = False
        elif state == "running":
            if _probe(health_url):
                print("SearXNG already running")
                return 0
        else:
            _run(["docker", "start", CONTAINER_NAME])
    if not exists:
        _run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                CONTAINER_NAME,
                "-p",
                f"{HOST_BIND}:{HOST_PORT}:{CONTAINER_PORT}",
                "-v",
                f"{mount_dir}:/etc/searxng",
                "--restart",
                "unless-stopped",
                IMAGE,
            ]
        )

    for _ in range(60):
        if _probe(health_url):
            print(f"[SearXNG][windows] Ready: {health_url}")
            return 0
        time.sleep(1)

    _log(log_file, "[SearXNG][windows][WARN] startup failed.")
    _log(log_file, _run(["docker", "ps", "-a", "--filter", f"name={CONTAINER_NAME}"]).stdout.strip())
    _log(log_file, _run(["docker", "logs", CONTAINER_NAME, "--tail", "100"]).stdout.strip())
    print(f"[SearXNG][windows][WARN] failed to start. Check log: {log_file}")
    print("[Docker][WARN] Docker Desktop may require license acceptance/subscription depending on usage. Please review Docker Desktop terms.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
