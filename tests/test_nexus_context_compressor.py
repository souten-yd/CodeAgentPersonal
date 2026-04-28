import os
import unittest
from unittest.mock import patch

from app.nexus.context_compressor import (
    build_context_budget,
    choose_profile_name,
    compress_global_evidence,
    compress_large_source,
)


class NexusContextCompressorTests(unittest.TestCase):
    def test_large_source_respects_source_budget_and_chunk_limit(self) -> None:
        budget = build_context_budget(
            max_context_tokens=16384,
            instruction_tokens_estimate=300,
            question_tokens_estimate=100,
            source_metadata_tokens_estimate=200,
            preferred_profile="standard_16k",
        )
        source = {"source_id": "s1", "source_type": "paper", "title": "Huge"}
        chunks = [
            {"source_id": "s1", "chunk_id": f"c{i}", "citation_label": "[S1]", "quote": "query alpha " * 200}
            for i in range(20)
        ]
        packet = compress_large_source("query alpha", source, chunks, budget)
        self.assertLessEqual(len(packet["chunks"]), budget.max_chunks_per_source)
        self.assertTrue(all(len(c.get("quote", "")) <= budget.max_chars_per_chunk for c in packet["chunks"]))

    def test_global_budget_and_citation_label_are_preserved(self) -> None:
        budget = build_context_budget(
            max_context_tokens=16384,
            instruction_tokens_estimate=300,
            question_tokens_estimate=100,
            source_metadata_tokens_estimate=200,
            preferred_profile="standard_16k",
        )
        references = [
            {"source_id": "s1", "source_type": "official", "title": "A", "url": "https://a"},
            {"source_id": "s2", "source_type": "news", "title": "B", "url": "https://b"},
        ]
        chunks = [
            {"source_id": "s1", "chunk_id": "c1", "citation_label": "[S1]", "quote": "alpha" * 400},
            {"source_id": "s2", "chunk_id": "c2", "citation_label": "[S2]", "quote": "beta" * 400},
            {"source_id": "s2", "chunk_id": "c3", "citation_label": "[S2]", "quote": "beta" * 400},
        ]
        out = compress_global_evidence("alpha beta", references, chunks, budget)
        self.assertLessEqual(out["stats"]["estimated_evidence_tokens"], budget.max_evidence_tokens)
        self.assertTrue(any(c.get("citation_label") == "[S1]" for c in out["chunks"]))
        self.assertGreaterEqual(out["stats"]["sources_used"], 1)

    def test_dedupe_and_stats(self) -> None:
        budget = build_context_budget(
            max_context_tokens=16384,
            instruction_tokens_estimate=300,
            question_tokens_estimate=100,
            source_metadata_tokens_estimate=200,
            preferred_profile="standard_16k",
        )
        references = [
            {"source_id": "s1", "source_type": "web", "title": "dup", "url": "https://dup"},
            {"source_id": "s2", "source_type": "web", "title": "dup", "url": "https://dup"},
        ]
        chunks = [
            {"source_id": "s1", "chunk_id": "c1", "citation_label": "[S1]", "quote": "same quote"},
            {"source_id": "s2", "chunk_id": "c2", "citation_label": "[S2]", "quote": "same quote"},
        ]
        out = compress_global_evidence("same", references, chunks, budget)
        self.assertGreaterEqual(out["stats"]["dropped_count"], 1)
        self.assertLessEqual(out["stats"]["chunks_used"], 1)

    def test_profile_budget_scaling_for_24k(self) -> None:
        budget16 = build_context_budget(
            max_context_tokens=16384,
            instruction_tokens_estimate=300,
            question_tokens_estimate=100,
            source_metadata_tokens_estimate=200,
            preferred_profile=choose_profile_name(16384),
        )
        budget24 = build_context_budget(
            max_context_tokens=24576,
            instruction_tokens_estimate=300,
            question_tokens_estimate=100,
            source_metadata_tokens_estimate=200,
            preferred_profile=choose_profile_name(24576),
        )
        self.assertEqual(budget24.compression_profile, "high_24k")
        self.assertGreater(budget24.max_evidence_chars, budget16.max_evidence_chars)
        self.assertGreater(budget24.max_source_tokens, budget16.max_source_tokens)
        self.assertGreater(budget24.max_evidence_tokens, budget16.max_evidence_tokens)

    def test_empty_compression_uses_minimal_short_chunks_not_raw_fallback(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NEXUS_ANSWER_LLM_MAX_EVIDENCE_CHARS": "230",
                "NEXUS_ANSWER_LLM_MAX_CHARS_PER_CHUNK": "1400",
            },
            clear=False,
        ):
            budget = build_context_budget(
                max_context_tokens=16384,
                instruction_tokens_estimate=300,
                question_tokens_estimate=100,
                source_metadata_tokens_estimate=200,
                preferred_profile="compact_8k",
            )
        references = [{"source_id": "s1", "source_type": "web", "title": "A", "url": "https://a"}]
        chunks = [{"source_id": "s1", "chunk_id": f"c{i}", "citation_label": "[S1]", "quote": ("x" * 6000)} for i in range(5)]
        out = compress_global_evidence("irrelevant", references, chunks, budget)
        self.assertTrue(out["chunks"])
        self.assertTrue(out["stats"]["compression_empty_fallback_used"])
        self.assertTrue(all(len(c.get("quote", "")) <= 220 for c in out["chunks"]))


if __name__ == "__main__":
    unittest.main()
