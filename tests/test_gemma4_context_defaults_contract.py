import importlib.util
from pathlib import Path


def _load_start_codeagent():
    path = Path("scripts/start_codeagent.py")
    spec = importlib.util.spec_from_file_location("start_codeagent_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_runpod_shell_defaults_use_64k_context():
    script = Path("scripts/runpod_start.sh").read_text(encoding="utf-8")
    assert 'export DEFAULT_LLM_CTX_SIZE="${DEFAULT_LLM_CTX_SIZE:-65535}"' in script
    assert 'export LLAMA_CTX_SIZE="${LLAMA_CTX_SIZE:-${DEFAULT_LLM_CTX_SIZE}}"' in script
    assert 'export NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS="${NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS:-${DEFAULT_LLM_CTX_SIZE}}"' in script
    assert 'export NEXUS_DEEP_RESEARCH_CONTEXT_PROFILE="${NEXUS_DEEP_RESEARCH_CONTEXT_PROFILE:-long_64k}"' in script
    assert 'echo "[Runpod] NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS=${NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS}"' in script
    assert 'echo "[Runpod] NEXUS_DEEP_RESEARCH_CONTEXT_PROFILE=${NEXUS_DEEP_RESEARCH_CONTEXT_PROFILE}"' in script


def test_start_codeagent_default_ctx_helper_contract():
    module = _load_start_codeagent()
    assert hasattr(module, "_default_llm_ctx_size")
    assert module._default_llm_ctx_size(runpod=True, env={}) == "65535"
    assert module._default_llm_ctx_size(runpod=False, env={}) == "16384"
    assert module._default_llm_ctx_size(runpod=False, env={"DEFAULT_LLM_CTX_SIZE": "32768"}) == "32768"
    assert module._default_llm_ctx_size(runpod=False, env={"CODEAGENT_INITIAL_MODEL": "unsloth/gemma-4-E4B-it-GGUF"}) == "65535"


def test_gemma4_seed_and_inference_use_65535():
    main_py = Path("main.py").read_text(encoding="utf-8")
    assert '"ctx_size": 65535' in main_py
    assert 'default_info["ctx_size"] = 65535' in main_py
    assert 'return 65535' in main_py
    assert '"--ctx-size", str(spec["ctx"])' in main_py
