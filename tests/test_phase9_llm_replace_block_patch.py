from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.llm_patch_generator import generate_replace_block_patch
from agent.patch_safety import PatchSafetyChecker


class Phase9LLMReplaceBlockPatchTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.target = self.project / "a.py"
        self.target.write_text("x=1\nprint('a')\n", encoding="utf-8")

    def tearDown(self):
        self.td.cleanup()

    def test_valid_json_generates_replace_block(self):
        def fake_llm(**kwargs):
            return '{"original_block":"x=1","replacement_block":"x=2"}'
        content = self.target.read_text(encoding="utf-8")
        p = generate_replace_block_patch("r","p","s","t","d","low",self.target,content,llm_fn=fake_llm)
        self.assertEqual(p.patch_type, "replace_block")
        self.assertTrue(p.apply_allowed)

    def test_no_match_denied(self):
        def fake_llm(**kwargs): return '{"original_block":"zzz","replacement_block":"x=2"}'
        p = generate_replace_block_patch("r","p","s","t","d","low",self.target,self.target.read_text(encoding='utf-8'),llm_fn=fake_llm)
        self.assertFalse(p.apply_allowed)

    def test_fence_sanitize(self):
        def fake_llm(**kwargs): return '```json\n{"original_block":"x=1","replacement_block":"x=2"}\n```'
        p = generate_replace_block_patch("r","p","s","t","d","low",self.target,self.target.read_text(encoding='utf-8'),llm_fn=fake_llm)
        self.assertTrue(p.llm_sanitized)

    def test_safety_secret_reject(self):
        def fake_llm(**kwargs): return '{"original_block":"x=1","replacement_block":"api_key=1"}'
        p = generate_replace_block_patch("r","p","s","t","d","low",self.target,self.target.read_text(encoding='utf-8'),llm_fn=fake_llm)
        ok, _ = PatchSafetyChecker().evaluate(p, self.project, "low")
        self.assertFalse(ok)

if __name__ == '__main__':
    unittest.main()
