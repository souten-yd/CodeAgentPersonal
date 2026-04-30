from __future__ import annotations

import os

_STYLE_BERT_VITS2_DEFAULT_BASE_DIR = "/workspace/ca_data/tts/style_bert_vits2"
_STYLE_BERT_VITS2_MODELS_DIR_ENV = "CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR"
_STYLE_BERT_VITS2_BASE_DIR_ENV = "CODEAGENT_STYLE_BERT_VITS2_BASE_DIR"


def _from_env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    return os.path.abspath(value)


def resolve_style_bert_vits2_base_dir() -> str:
    env = _from_env(_STYLE_BERT_VITS2_BASE_DIR_ENV)
    if env:
        return env
    if os.name == "nt":
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(repo_root, "ca_data", "tts", "style_bert_vits2")
    return _STYLE_BERT_VITS2_DEFAULT_BASE_DIR


def resolve_style_bert_vits2_models_dir() -> str:
    models_dir = _from_env(_STYLE_BERT_VITS2_MODELS_DIR_ENV)
    if models_dir:
        return models_dir
    return os.path.join(resolve_style_bert_vits2_base_dir(), "models")
