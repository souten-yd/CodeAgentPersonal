import os
import unittest
from unittest.mock import patch

from app.nexus.answer_builder import build_answer_payload


class NexusAnswerBuilderTests(unittest.TestCase):
    def test_build_answer_payload_uses_llm_with_evidence_chunks_and_preserves_s_label(self) -> None:
        references = [{"citation_label": "article#1", "title": "Source 1", "url": "https://example.com/1", "source_id": "src-1"}]
        chunks = [{"quote": "fact", "source_id": "src-1", "citation_label": "article#1"}]
        llm_text = "結論です article#1\n\n## 追加確認が必要な点\n- なし"

        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=False), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            return_value=llm_text,
        ) as mocked:
            payload = build_answer_payload(
                question="質問",
                summary="fallback summary",
                references=references,
                evidence_chunks=chunks,
            )

        self.assertIn("[S1]", payload["answer"])
        self.assertNotIn("article#1", payload["answer"])
        self.assertIn(payload["answer"], payload["answer_markdown"])
        mocked.assert_called_once()
        self.assertEqual(payload["references"][0]["citation_label"], "[S1]")
        self.assertIn("- [S1] Source 1 (https://example.com/1)", payload["answer_markdown"])

    def test_build_answer_payload_falls_back_to_template_summary_when_llm_fails(self) -> None:
        references = [{"citation_label": "legacy-label", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "legacy-label"}]
        fallback_summary = "fallback summary legacy-label"

        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=False), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            side_effect=TimeoutError("timeout"),
        ):
            payload = build_answer_payload(
                question="質問",
                summary=fallback_summary,
                references=references,
                evidence_chunks=chunks,
            )

        self.assertIn("fallback summary", payload["answer"])
        self.assertIn("[S1]", payload["answer"])
        self.assertNotIn("legacy-label", payload["answer"])
        self.assertIn("## References", payload["answer_markdown"])

    def test_build_answer_payload_keeps_references_consistent_between_json_and_markdown(self) -> None:
        references = [
            {"citation_label": "r1", "title": "Source 1", "url": "https://example.com/1", "source_id": "src-1"},
            {"citation_label": "r2", "title": "Source 2", "url": "https://example.com/2", "source_id": "src-2"},
        ]
        evidence = [
            {"citation_label": "r1", "source_id": "src-1", "quote": "q1"},
            {"citation_label": "r2", "source_id": "src-2", "quote": "q2"},
        ]
        chunks = [
            {"citation_label": "r1", "source_id": "src-1", "text": "q1"},
            {"citation_label": "r2", "source_id": "src-2", "text": "q2"},
        ]

        payload = build_answer_payload(
            question="質問",
            summary="summary r1 r2",
            references=references,
            evidence=evidence,
            evidence_chunks=chunks,
        )

        self.assertEqual([ref["citation_label"] for ref in payload["references"]], ["[S1]", "[S2]"])
        self.assertEqual([row["citation_label"] for row in payload["evidence_json"]], ["[S1]", "[S2]"])
        self.assertIn("- [S1] Source 1 (https://example.com/1)", payload["answer_markdown"])
        self.assertIn("- [S2] Source 2 (https://example.com/2)", payload["answer_markdown"])

    def test_build_answer_payload_normalizes_non_standard_labels(self) -> None:
        references = [{"citation_label": "article#1", "title": "Source 1", "source_id": "src-1"}]
        evidence = [{"citation_label": "article#1", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "article#1"}]

        payload = build_answer_payload(
            question="質問",
            summary="article#1 の根拠です",
            references=references,
            evidence=evidence,
            evidence_chunks=chunks,
        )

        self.assertEqual(payload["references"][0]["citation_label"], "[S1]")
        self.assertEqual(payload["evidence_json"][0]["citation_label"], "[S1]")
        self.assertIn("[S1]", payload["answer_markdown"])
        self.assertNotIn("article#1", payload["answer_markdown"])

    def test_citation_verification_ok_when_all_labels_match(self) -> None:
        references = [{"citation_label": "src-a", "title": "Source A", "source_id": "src-a"}]

        payload = build_answer_payload(
            question="質問",
            summary="これは結論です src-a",
            references=references,
        )

        self.assertEqual(
            payload["citation_verification"],
            {
                "ok": True,
                "missing_in_references": [],
                "unused_references": [],
                "invalid_labels": [],
            },
        )

    def test_citation_verification_detects_unknown_label_in_answer(self) -> None:
        references = [{"citation_label": "src-a", "title": "Source A", "source_id": "src-a"}]

        payload = build_answer_payload(
            question="質問",
            summary="結論 [S1] [S9]",
            references=references,
        )

        self.assertFalse(payload["citation_verification"]["ok"])
        self.assertEqual(payload["citation_verification"]["missing_in_references"], ["[S9]"])
        self.assertEqual(payload["citation_verification"]["unused_references"], [])

    def test_citation_verification_detects_unused_reference_label(self) -> None:
        references = [
            {"citation_label": "r1", "title": "Source 1", "source_id": "src-1"},
            {"citation_label": "r2", "title": "Source 2", "source_id": "src-2"},
        ]
        chunks = [
            {"text": "fact1", "source_id": "src-1", "citation_label": "r1"},
            {"text": "fact2", "source_id": "src-2", "citation_label": "r2"},
        ]

        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=False), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            return_value="結論 [S1]",
        ):
            payload = build_answer_payload(
                question="質問",
                summary="fallback",
                references=references,
                evidence_chunks=chunks,
            )

        self.assertFalse(payload["citation_verification"]["ok"])
        self.assertEqual(payload["citation_verification"]["missing_in_references"], [])
        self.assertEqual(payload["citation_verification"]["unused_references"], ["[S2]"])
        self.assertEqual(payload["citation_verification"]["invalid_labels"], [])


if __name__ == "__main__":
    unittest.main()
