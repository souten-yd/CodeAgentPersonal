#!/usr/bin/env python3
from __future__ import annotations

import os
import secrets
import stat
import subprocess
import sys
import shutil
from pathlib import Path


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("[SearXNG][setup] $", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def _rmtree_onerror(func, path, exc_info):
    # Windowsでreadonly属性のファイル削除に失敗した際の対策
    if isinstance(exc_info[1], PermissionError):
        os.chmod(path, stat.S_IWRITE)
        func(path)
        return
    raise exc_info[1]


def _is_incomplete_repo(repo_dir: Path) -> bool:
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        return False
    required_paths = [
        repo_dir / "searx" / "webapp.py",
        repo_dir / "pyproject.toml",
    ]
    if any(not p.exists() for p in required_paths):
        return True
    return False


def _clone_searxng_sparse(repo_dir: Path, base_dir: Path, env: dict[str, str]) -> None:
    sparse_patterns = "\n".join(
        [
            "/*",
            "!/utils/templates/**",
            "/searx/",
            "/searxng_extra/",
            "/pyproject.toml",
            "/babel.cfg",
            "/README.rst",
            "/manage",
            "/requirements*.txt",
            "",
        ]
    )
    _run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", "https://github.com/searxng/searxng.git", str(repo_dir)],
        cwd=base_dir,
        env=env,
    )
    _run(["git", "-C", str(repo_dir), "sparse-checkout", "init", "--no-cone"], cwd=base_dir, env=env)
    info_sparse = repo_dir / ".git" / "info" / "sparse-checkout"
    info_sparse.parent.mkdir(parents=True, exist_ok=True)
    info_sparse.write_text(sparse_patterns, encoding="utf-8")
    try:
        _run(["git", "-C", str(repo_dir), "checkout", "HEAD"], cwd=base_dir, env=env)
    except RuntimeError as exc:
        raise RuntimeError(
            "SearXNG の sparse checkout に失敗しました。Windows では通常 clone が失敗するため sparse checkout を使用しています。"
            " 壊れた third_party/searxng を削除して再実行してください。"
            f" repo_dir={repo_dir} sparse_pattern_file={info_sparse} sparse_patterns={sparse_patterns!r}"
        ) from exc


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

    if repo_dir.exists() and _is_incomplete_repo(repo_dir):
        print("[SearXNG][setup] Existing repo looks incomplete. Removing and re-cloning with sparse checkout.")
        shutil.rmtree(repo_dir, onerror=_rmtree_onerror)

    if not repo_dir.exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        print("[SearXNG][setup] Cloning SearXNG with Windows-safe sparse checkout (utils/templates is excluded).")
        _clone_searxng_sparse(repo_dir=repo_dir, base_dir=base_dir, env=env)
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
    bind_address = env.get("SEARXNG_BIND_ADDRESS", "127.0.0.1")
    port = env.get("SEARXNG_PORT", "8088")
    base_url = env.get("SEARXNG_BASE_URL", "false")

    if not settings_file.exists():
        settings_file.write_text(
            "\n".join(
                [
                    "use_default_settings: true",
                    "general:",
                    f"  secret_key: \"{secret_key}\"",
                    "server:",
                    f"  bind_address: \"{bind_address}\"",
                    f"  port: {port}",
                    f"  base_url: {base_url}",
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
