#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONTAINER_NAME = "codeagent-searxng"
IMAGE = "searxng/searxng:latest"
HOST_BIND = "127.0.0.1"
HOST_PORT = "8088"
CONTAINER_PORT = "8080"


def _is_windows() -> bool:
    return os.name == "nt"


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def _log(log_file: Path, message: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as fp:
        fp.write(f"{message}\n")


def _health_probe(url: str, timeout: float = 2.0) -> tuple[bool, int | None, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = int(resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, int(exc.code), body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, None, str(exc)

    if status != 200:
        return False, status, body
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False, status, body
    if isinstance(data, dict) and ("results" in data or "query" in data):
        return True, status, body
    return False, status, body


def _extract_secret_from_settings(text: str) -> str | None:
    server_match = re.search(r"(?ms)^server:\s*.*?^\s*secret_key:\s*\"?([^\"\n]+)\"?", text)
    if server_match:
        return server_match.group(1).strip()
    general_match = re.search(r"(?ms)^general:\s*.*?^\s*secret_key:\s*\"?([^\"\n]+)\"?", text)
    if general_match:
        return general_match.group(1).strip()
    return None


def _resolve_secret(config_dir: Path) -> str:
    secret_file = config_dir / "secret_key"
    settings_file = config_dir / "settings.yml"
    candidates: list[str] = []
    if secret_file.exists():
        candidates.append(secret_file.read_text(encoding="utf-8").strip())
    if settings_file.exists():
        candidates.append(_extract_secret_from_settings(settings_file.read_text(encoding="utf-8")) or "")
    for secret in candidates:
        if secret and secret != "ultrasecretkey":
            secret_file.write_text(secret + "\n", encoding="utf-8")
            return secret
    secret = secrets.token_urlsafe(64)
    secret_file.write_text(secret + "\n", encoding="utf-8")
    return secret


def ensure_settings(config_dir: Path) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    settings_file = config_dir / "settings.yml"
    secret = _resolve_secret(config_dir)
    body = (
        "use_default_settings: true\n\n"
        "server:\n"
        f"  secret_key: \"{secret}\"\n"
        "  bind_address: \"0.0.0.0\"\n"
        "  port: 8080\n"
        "  base_url: false\n\n"
        "search:\n"
        "  safe_search: 0\n"
        "  formats:\n"
        "    - html\n"
        "    - json\n\n"
        "ui:\n"
        "  static_use_hash: true\n"
    )
    settings_file.write_text(body, encoding="utf-8")
    return settings_file


def try_install_docker(log_file: Path) -> bool:
    winget = _run(["where", "winget"])
    if winget.returncode != 0:
        _log(log_file, "[Docker][WARN] winget not found. Install Docker Desktop manually.")
        return False
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
        _log(log_file, "[Docker] Docker Desktop installed via winget.")
        return True
    _log(log_file, f"[Docker][WARN] winget install failed: {install.stderr.strip()}")
    return False


def ensure_docker_engine(log_file: Path) -> bool:
    if _run(["docker", "info"]).returncode == 0:
        return True
    _run(["powershell", "-Command", 'Start-Process "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"'])
    for _ in range(30):
        if _run(["docker", "info"]).returncode == 0:
            return True
        time.sleep(2)
    _log(log_file, "Docker Desktopを起動し、利用条件を承認してから start.bat を再実行してください")
    return False


def _container_state() -> str:
    cp = _run(["docker", "inspect", "-f", "{{.State.Status}}", CONTAINER_NAME])
    return cp.stdout.strip().lower() if cp.returncode == 0 else ""


def main() -> int:
    if not _is_windows():
        return 0
    base_dir = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    config_dir = Path(env.get("CODEAGENT_SEARXNG_CONFIG_DIR", str(base_dir / "ca_data" / "searxng"))).expanduser()
    log_file = Path(env.get("CODEAGENT_SEARXNG_LOG_FILE", str(config_dir / "searxng.log"))).expanduser()
    base = (env.get("NEXUS_SEARXNG_URL") or f"http://{HOST_BIND}:{HOST_PORT}").strip().rstrip("/")
    health_url = f"{base}/search?{urllib.parse.urlencode({'format':'json','q':'healthcheck'})}"

    ok, _, _ = _health_probe(health_url)
    if ok:
        print("SearXNG already running")
        return 0

    ensure_settings(config_dir)

    if _run(["docker", "--version"]).returncode != 0:
        if not try_install_docker(log_file):
            return 0

    if not ensure_docker_engine(log_file):
        return 0

    state = _container_state()
    if state in {"exited", "dead", "restarting", "created"}:
        _run(["docker", "rm", "-f", CONTAINER_NAME])
        state = ""

    if state == "running":
        logs = _run(["docker", "logs", CONTAINER_NAME, "--tail", "100"]).stdout
        if any(s in logs for s in ["server.secret_key is not changed", "ultrasecretkey", "403 Forbidden"]):
            ensure_settings(config_dir)
            _run(["docker", "rm", "-f", CONTAINER_NAME])
            state = ""

    if not state:
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
                f"{config_dir.resolve()}:/etc/searxng",
                "--restart",
                "unless-stopped",
                IMAGE,
            ]
        )

    for _ in range(60):
        ok, status, _body = _health_probe(health_url)
        if ok:
            print(f"[SearXNG][windows] Ready: {health_url}")
            return 0
        if status == 403:
            ensure_settings(config_dir)
            _run(["docker", "rm", "-f", CONTAINER_NAME])
            _run([
                "docker", "run", "-d", "--name", CONTAINER_NAME, "-p", f"{HOST_BIND}:{HOST_PORT}:{CONTAINER_PORT}",
                "-v", f"{config_dir.resolve()}:/etc/searxng", "--restart", "unless-stopped", IMAGE,
            ])
        time.sleep(1)

    _log(log_file, _run(["docker", "ps", "-a", "--filter", f"name={CONTAINER_NAME}"]).stdout.strip())
    _log(log_file, _run(["docker", "logs", CONTAINER_NAME, "--tail", "100"]).stdout.strip())
    _log(log_file, f"settings.yml exists: {(config_dir / 'settings.yml').exists()}")
    _log(log_file, f"log file: {log_file}")
    print(f"[SearXNG][windows][WARN] failed to start. Check log: {log_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
