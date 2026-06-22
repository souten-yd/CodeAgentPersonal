"""Atlas LLM adapter registration: a bare launch must still resolve a local backend.

Regression guard for "Atlas plan generation silently returns no items" when the server is
launched without the CODEAGENT_LLM_* env that scripts/start_codeagent.py normally sets. The
registration must fall back to the conventional local llama-server so the real planner keeps
working, while remaining overridable (explicit config wins) and able to fail closed on request.
"""

from types import SimpleNamespace

from app.api.atlas_pipeline import (
    _DEFAULT_LOCAL_LLM_BASE_URL,
    register_atlas_llm_json_adapter,
)

_BACKEND_ENV_KEYS = (
    "CODEAGENT_LLM_BASE_URL",
    "OPENAI_BASE_URL",
    "LLAMA_SERVER_URL",
    "LLM_BASE_URL",
    "CODEAGENT_LLM_CHAT",
    "LLM_URL",
    "CODEAGENT_MODEL",
    "OPENAI_MODEL",
    "ATLAS_DISABLE_LOCAL_LLM_DEFAULT",
    "ATLAS_LLM_MAX_TOKENS",
)


def _clear_backend_env(monkeypatch) -> None:
    for key in _BACKEND_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _app() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace())


def test_registers_local_default_when_nothing_resolved(monkeypatch) -> None:
    _clear_backend_env(monkeypatch)
    app = _app()

    register_atlas_llm_json_adapter(app)

    fn = app.state.atlas_llm_json_fn
    assert callable(fn)
    assert fn.base_url == _DEFAULT_LOCAL_LLM_BASE_URL


def test_opt_out_leaves_adapter_unset(monkeypatch) -> None:
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("ATLAS_DISABLE_LOCAL_LLM_DEFAULT", "1")
    app = _app()

    register_atlas_llm_json_adapter(app)

    assert getattr(app.state, "atlas_llm_json_fn", None) is None


def test_explicit_env_backend_wins_over_default(monkeypatch) -> None:
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("CODEAGENT_LLM_CHAT", "http://10.0.0.5:9000/v1/chat/completions")
    app = _app()

    register_atlas_llm_json_adapter(app)

    fn = app.state.atlas_llm_json_fn
    assert callable(fn)
    assert fn.base_url == "http://10.0.0.5:9000"


def test_max_tokens_defaults_to_zero_uses_schema_default(monkeypatch) -> None:
    # No override configured: the adapter leaves max_tokens at 0 so the request/schema default
    # (now 8192) applies — large files are not truncated at the old 4096.
    _clear_backend_env(monkeypatch)
    app = _app()

    register_atlas_llm_json_adapter(app)

    assert app.state.atlas_llm_json_fn.max_tokens == 0


def test_env_max_tokens_overrides_generation_cap(monkeypatch) -> None:
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("ATLAS_LLM_MAX_TOKENS", "16384")
    app = _app()

    register_atlas_llm_json_adapter(app)

    assert app.state.atlas_llm_json_fn.max_tokens == 16384


def test_state_max_tokens_used_when_env_absent(monkeypatch) -> None:
    _clear_backend_env(monkeypatch)
    app = _app()
    app.state.atlas_llm_max_tokens = 12000

    register_atlas_llm_json_adapter(app)

    assert app.state.atlas_llm_json_fn.max_tokens == 12000


def test_existing_callable_is_not_overwritten(monkeypatch) -> None:
    _clear_backend_env(monkeypatch)
    app = _app()
    sentinel = lambda _s, _u: {"ok": True}  # noqa: E731
    app.state.atlas_llm_json_fn = sentinel

    register_atlas_llm_json_adapter(app)

    assert app.state.atlas_llm_json_fn is sentinel
