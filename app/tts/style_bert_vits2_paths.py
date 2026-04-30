from __future__ import annotations

import os
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
