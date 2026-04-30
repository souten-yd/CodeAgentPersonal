from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_STYLE_BERT_VITS2_DEFAULT_BASE_DIR = "/workspace/ca_data/tts/style_bert_vits2"
_STYLE_BERT_VITS2_MODELS_DIR_ENV = "CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR"
_STYLE_BERT_VITS2_BASE_DIR_ENV = "CODEAGENT_STYLE_BERT_VITS2_BASE_DIR"
_STYLE_BERT_VITS2_REPO_DIR_ENV = "CODEAGENT_STYLE_BERT_VITS2_REPO_DIR"
_STYLE_BERT_VITS2_VENV_DIR_ENV = "CODEAGENT_STYLE_BERT_VITS2_VENV_DIR"


def _from_env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    return os.path.abspath(value)


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_style_bert_vits2_repo_dir() -> str:
    env = _from_env(_STYLE_BERT_VITS2_REPO_DIR_ENV)
    if env:
        return env
    if os.name == "nt":
        return str(resolve_project_root() / "third_party" / "Style-Bert-VITS2")
    return "/app/Style-Bert-VITS2"


def resolve_style_bert_vits2_venv_dir() -> str:
    env = _from_env(_STYLE_BERT_VITS2_VENV_DIR_ENV)
    if env:
        return env
    if os.name == "nt":
        return str(resolve_project_root() / "tts_envs" / "style_bert_vits2")
    return "/app/Style-Bert-VITS2/.venv"


def resolve_style_bert_vits2_python_path() -> str:
    venv = Path(resolve_style_bert_vits2_venv_dir())
    if os.name == "nt":
        return str(venv / "Scripts" / "python.exe")
    return str(venv / "bin" / "python")


def resolve_style_bert_vits2_base_dir() -> str:
    env = _from_env(_STYLE_BERT_VITS2_BASE_DIR_ENV)
    if env:
        return env
    if os.name == "nt":
        return str(resolve_project_root() / "ca_data" / "tts" / "style_bert_vits2")
    return _STYLE_BERT_VITS2_DEFAULT_BASE_DIR


def resolve_style_bert_vits2_models_dir() -> str:
    models_dir = _from_env(_STYLE_BERT_VITS2_MODELS_DIR_ENV)
    if models_dir:
        return models_dir
    return os.path.join(resolve_style_bert_vits2_base_dir(), "models")


def resolve_style_bert_vits2_site_packages_dir() -> str:
    venv_dir = Path(resolve_style_bert_vits2_venv_dir())
    python_path = Path(resolve_style_bert_vits2_python_path())
    if python_path.exists():
        try:
            code = "import site, json; print(json.dumps(site.getsitepackages()))"
            completed = subprocess.run(
                [str(python_path), "-c", code],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if completed.returncode == 0:
                import json

                for p in json.loads(completed.stdout.strip() or "[]"):
                    pp = Path(p)
                    if pp.exists() and pp.is_dir() and pp.name == "site-packages":
                        return str(pp)
        except Exception:
            pass

    win_site = venv_dir / "Lib" / "site-packages"
    if os.name == "nt" and win_site.exists():
        return str(win_site)

    for candidate in sorted((venv_dir / "lib").glob("python*/site-packages")):
        if candidate.exists() and candidate.is_dir():
            return str(candidate)

    if os.name == "nt":
        return str(win_site)
    return str(venv_dir / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")
