#!/usr/bin/env python3
from __future__ import annotations

import os
import secrets
import stat
import subprocess
import sys
import shutil
import io
import urllib.request
import zipfile
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
    if not repo_dir.exists():
        return False
    required_paths = [
        repo_dir / "searx" / "webapp.py",
        repo_dir / "setup.py",
        repo_dir / "requirements.txt",
        repo_dir / "requirements-dev.txt",
    ]
    return any(not p.exists() for p in required_paths)


def _detect_default_branch(env: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--symref", "https://github.com/searxng/searxng.git", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        for line in result.stdout.splitlines():
            if line.startswith("ref: refs/heads/") and line.rstrip().endswith("HEAD"):
                return line.split("refs/heads/", 1)[1].split()[0].strip()
    except Exception:
        pass
    return "master"


def _is_windows_invalid_path(rel_path: str) -> bool:
    invalid_chars = '<>:"|?*'
    reserved_names = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    parts = rel_path.replace("\\", "/").split("/")
    for part in parts:
        if not part or part in {".", ".."}:
            return True
        if any(ch in part for ch in invalid_chars):
            return True
        if part.upper() in reserved_names:
            return True
    return False


def _should_extract(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/").lstrip("/")
    allowed_prefixes = ("searx/", "searxng_extra/", "LICENSES/")
    allowed_files = {"pyproject.toml", "setup.py", "setup.cfg", "babel.cfg", "README.rst", "LICENSE", "manage"}
    if rel.startswith("utils/templates/"):
        return False
    if _is_windows_invalid_path(rel):
        return False
    if rel in allowed_files:
        return True
    if rel.startswith("requirements") and rel.endswith(".txt"):
        return True
    return any(rel.startswith(prefix) for prefix in allowed_prefixes)


def _download_searxng_zip(repo_dir: Path, env: dict[str, str]) -> None:
    branch = _detect_default_branch(env)
    url = f"https://codeload.github.com/searxng/searxng/zip/refs/heads/{branch}"
    print(f"[SearXNG][setup] Downloading SearXNG source ZIP: {url}")

    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()

    repo_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    skipped = 0

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            parts = name.split("/", 1)
            if len(parts) != 2:
                continue
            rel = parts[1]
            if not rel or rel.endswith("/"):
                continue
            if not _should_extract(rel):
                skipped += 1
                continue

            target = repo_dir / Path(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted += 1

    print(f"[SearXNG][setup] Extracted {extracted} files, skipped {skipped} files.")
    required = [
        repo_dir / "searx" / "webapp.py",
        repo_dir / "setup.py",
        repo_dir / "requirements.txt",
        repo_dir / "requirements-dev.txt",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "SearXNG ZIP extraction incomplete. "
            f"Missing: {missing}\n"
            "Required files are setup.py-based because upstream SearXNG may not provide pyproject.toml."
        )



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
        print("[SearXNG][setup] Existing source directory looks incomplete. Removing and re-fetching source ZIP.")
        shutil.rmtree(repo_dir, onerror=_rmtree_onerror)

    if not repo_dir.exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        print("[SearXNG][setup] Fetching SearXNG with Windows-safe source ZIP extraction (utils/templates is excluded).")
        _download_searxng_zip(repo_dir=repo_dir, env=env)
    else:
        print(f"[SearXNG][setup] Reusing existing source directory: {repo_dir}")

    try:
        _run([str(pip_exe), "install", "-e", str(repo_dir)], cwd=base_dir, env=env)
    except RuntimeError:
        print("[SearXNG][setup] pip install failed. Removing source directory and retrying from source ZIP.")
        if repo_dir.exists():
            shutil.rmtree(repo_dir, onerror=_rmtree_onerror)
        _download_searxng_zip(repo_dir=repo_dir, env=env)
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
