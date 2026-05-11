import unittest
from pathlib import Path

class TestPhase303LlamaKvCacheQ8Contract(unittest.TestCase):
    def test_defaults_in_dockerfile(self):
        t = Path('Dockerfile').read_text(encoding='utf-8')
        self.assertIn('LLAMA_CACHE_TYPE_K=q8_0', t)
        self.assertIn('LLAMA_CACHE_TYPE_V=q8_0', t)

    def test_command_has_cache_type_args(self):
        m = Path('main.py').read_text(encoding='utf-8')
        self.assertIn('--cache-type-k', m)
        self.assertIn('--cache-type-v', m)
        self.assertIn('resolve_llama_cache_types', m)

    def test_benchmark_uses_same_env(self):
        b = Path('benchmark_mem.py').read_text(encoding='utf-8')
        self.assertIn('LLAMA_CACHE_TYPE_K', b)
        self.assertIn('LLAMA_CACHE_TYPE_V', b)
        self.assertIn('--cache-type-k', b)
        self.assertIn('--cache-type-v', b)

    def test_ctx_defaults_are_runpod_gemma_32k_but_local_safe(self):
        d = Path('Dockerfile').read_text(encoding='utf-8')
        s = Path('scripts/start_codeagent.py').read_text(encoding='utf-8')
        r = Path('scripts/runpod_start.sh').read_text(encoding='utf-8')
        self.assertIn('LLAMA_CACHE_TYPE_K=q8_0', d)
        self.assertIn('LLAMA_CACHE_TYPE_V=q8_0', d)
        self.assertIn('DEFAULT_LLM_CTX_SIZE="${DEFAULT_LLM_CTX_SIZE:-32768}"', r)
        self.assertIn('def _default_llm_ctx_size', s)
        self.assertIn('return "16384"', s)
        self.assertIn('return "32768"', s)
        self.assertIn('return "long_64k"', s)
        self.assertIn('return "extended_32k"', s)

    def test_no_aggressive_defaults(self):
        m = Path('main.py').read_text(encoding='utf-8')
        self.assertNotIn('return {"gpu_layers": 999, "cache_type_k": "q4_0"', m)
        self.assertNotIn('部分オフロード+KV q4_0', m)

    def test_fallback_validation_exists(self):
        m = Path('main.py').read_text(encoding='utf-8')
        self.assertIn('_normalize_llama_cache_type', m)
        self.assertIn('"f16"', m)

if __name__ == '__main__':
    unittest.main()
