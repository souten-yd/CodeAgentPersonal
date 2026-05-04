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

    def test_ctx_stays_16k(self):
        d = Path('Dockerfile').read_text(encoding='utf-8')
        s = Path('scripts/start_codeagent.py').read_text(encoding='utf-8')
        self.assertIn('DEFAULT_LLM_CTX_SIZE=16384', d)
        self.assertIn('LLAMA_CTX_SIZE=16384', d)
        self.assertIn('env.setdefault("DEFAULT_LLM_CTX_SIZE", "16384")', s)

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
