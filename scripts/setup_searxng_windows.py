#!/usr/bin/env python3
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("[SearXNG][setup] $", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def main() -> int:
    if os.name != "nt":
        print("[SearXNG][setup] Windows専用です。何も実行せず終了します。")
        return 0

    base_dir = Path(__file__).resolve().parent.parent
    env = os.environ.copy()

    repo_dir = Path(env.get("CODEAGENT_SEARXNG_REPO_DIR", str(base_dir / "third_party" / "searxng"))).expanduser()
    venv_dir = Path(env.get("CODEAGENT_SEARXNG_VENV_DIR", str(base_dir / "search_envs" / "searxng"))).expanduser()
    config_dir = Path(env.get("CODEAGENT_SEARXNG_CONFIG_DIR", str(base_dir / "ca_data" / "searxng"))).expanduser()
    log_file = Path(env.get("CODEAGENT_SEARXNG_LOG_FILE", str(config_dir / "searxng.log"))).expanduser()

    config_dir.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    py_exe = venv_dir / "Scripts" / "python.exe"
    pip_exe = venv_dir / "Scripts" / "pip.exe"
    if not py_exe.exists():
        print(f"[SearXNG][setup] Creating venv: {venv_dir}")
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=base_dir, env=env)

    _run([str(py_exe), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=base_dir, env=env)

    if not repo_dir.exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "https://github.com/searxng/searxng.git", str(repo_dir)], cwd=base_dir, env=env)
    else:
        print(f"[SearXNG][setup] Reusing repo: {repo_dir}")

    _run([str(pip_exe), "install", "-e", str(repo_dir)], cwd=base_dir, env=env)

    secret_file = config_dir / "secret_key"
    if not secret_file.exists() or not secret_file.read_text(encoding="utf-8").strip():
        secret = secrets.token_urlsafe(48)
        secret_file.write_text(secret + "\n", encoding="utf-8")
        print(f"[SearXNG][setup] Created secret key: {secret_file}")
    secret_key = secret_file.read_text(encoding="utf-8").strip()

    settings_file = config_dir / "settings.yml"
    if not settings_file.exists():
        settings_file.write_text(
            "\n".join(
                [
                    "use_default_settings: true",
                    "general:",
                    f"  secret_key: \"{secret_key}\"",
                    "server:",
                    "  bind_address: \"127.0.0.1\"",
                    "  port: 8088",
                    "  base_url: false",
                    "search:",
                    "  safe_search: 0",
                    "ui:",
                    "  static_use_hash: true",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"[SearXNG][setup] Created settings: {settings_file}")
    else:
        print(f"[SearXNG][setup] Reusing settings: {settings_file}")

    print("[SearXNG][setup] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
