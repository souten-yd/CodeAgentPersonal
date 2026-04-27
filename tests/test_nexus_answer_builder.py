import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.nexus.answer_builder import build_answer_payload
from app.nexus.config import NexusPaths


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
        self.assertEqual(payload["generation_mode"], "llm")
        self.assertTrue(payload["llm_enabled"])
        self.assertEqual(payload["llm_endpoint"], "http://127.0.0.1:8000/v1/chat/completions")
        self.assertEqual(payload["llm_model"], "local-llm")
        self.assertIsNone(payload["llm_error"])
        self.assertEqual(payload["generation"]["mode"], "llm")
        self.assertTrue(payload["generation"]["llm_enabled"])
        self.assertEqual(payload["generation"]["llm_endpoint"], "http://127.0.0.1:8000/v1/chat/completions")
        self.assertEqual(payload["generation"]["llm_model"], "local-llm")
        self.assertIsNone(payload["generation"]["error"])

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
        self.assertEqual(payload["generation_mode"], "template_fallback")
        self.assertTrue(payload["llm_enabled"])
        self.assertEqual(payload["llm_endpoint"], "http://127.0.0.1:8000/v1/chat/completions")
        self.assertEqual(payload["llm_model"], "local-llm")
        self.assertEqual(payload["llm_error"], "timeout")
        self.assertEqual(payload["generation"]["mode"], "template_fallback")
        self.assertTrue(payload["generation"]["llm_enabled"])
        self.assertEqual(payload["generation"]["llm_endpoint"], "http://127.0.0.1:8000/v1/chat/completions")
        self.assertEqual(payload["generation"]["llm_model"], "local-llm")
        self.assertEqual(payload["generation"]["error"], "timeout")

    def test_build_answer_payload_persists_llm_metadata_in_answer_json(self) -> None:
        references = [{"citation_label": "legacy-label", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "legacy-label"}]

        with tempfile.TemporaryDirectory() as tmp_dir:
            ca_data_dir = Path(tmp_dir) / "ca_data"
            nexus_dir = ca_data_dir / "nexus"
            paths = NexusPaths(
                ca_data_dir=ca_data_dir,
                nexus_dir=nexus_dir,
                db_path=nexus_dir / "nexus.db",
                uploads_dir=nexus_dir / "uploads",
                extracted_dir=nexus_dir / "extracted",
                reports_dir=nexus_dir / "reports",
                exports_dir=nexus_dir / "exports",
            )
            with patch(
                "app.nexus.answer_builder.NEXUS_PATHS",
                paths,
            ), patch(
                "app.nexus.answer_builder._save_answer_row",
                return_value="answer-id-123",
            ), patch.dict(
                os.environ,
                {"NEXUS_ENABLE_ANSWER_LLM": "true"},
                clear=False,
            ), patch(
                "app.nexus.answer_builder._generate_answer_with_llm",
                side_effect=RuntimeError("llm unavailable"),
            ):
                payload = build_answer_payload(
                    question="質問",
                    summary="fallback summary legacy-label",
                    references=references,
                    evidence_chunks=chunks,
                    job_id="job_1",
                )

            answer_json_path = Path(payload["answer_json_path"])
            self.assertTrue(answer_json_path.exists())
            saved_payload = json.loads(answer_json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["generation_mode"], "template_fallback")
            self.assertTrue(saved_payload["llm_enabled"])
            self.assertEqual(saved_payload["llm_endpoint"], "http://127.0.0.1:8000/v1/chat/completions")
            self.assertEqual(saved_payload["llm_model"], "local-llm")
            self.assertEqual(saved_payload["llm_error"], "llm unavailable")
            self.assertEqual(saved_payload["generation"]["mode"], "template_fallback")
            self.assertTrue(saved_payload["generation"]["llm_enabled"])
            self.assertEqual(saved_payload["generation"]["llm_endpoint"], "http://127.0.0.1:8000/v1/chat/completions")
            self.assertEqual(saved_payload["generation"]["llm_model"], "local-llm")
            self.assertEqual(saved_payload["generation"]["error"], "llm unavailable")

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

        self.assertTrue(payload["citation_verification"]["ok"])
        self.assertEqual(payload["citation_verification"]["missing_in_references"], [])
        self.assertEqual(payload["citation_verification"]["unused_references"], [])
        self.assertEqual(payload["citation_verification"]["invalid_labels"], [])
        self.assertEqual(payload["citation_verification"]["warnings"], [])

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

    def test_citation_verification_sentence_status_regression(self) -> None:
        references = [
            {"citation_label": "r1", "title": "Source 1", "source_id": "src-1"},
            {"citation_label": "r2", "title": "Source 2", "source_id": "src-2"},
            {"citation_label": "r3", "title": "Source 3", "source_id": "src-3"},
        ]
        chunks = [
            {"citation_label": "r1", "source_id": "src-1", "chunk_id": "c1", "quote": "東京の人口は約1400万人です。"},
            {"citation_label": "r2", "source_id": "src-2", "chunk_id": "c2", "quote": "電気自動車の販売は前年比で増加した。"},
            {"citation_label": "r3", "source_id": "src-3", "chunk_id": "c3", "quote": "全く関係のない証拠文です。"},
        ]

        payload = build_answer_payload(
            question="質問",
            summary=(
                "東京の人口は約1400万人です。[S1] "
                "電気自動車市場については増加傾向です。[S2] "
                "火星に海があると断定できます。[S3]"
            ),
            references=references,
            evidence_chunks=chunks,
        )

        sentence_results = payload["citation_verification"]["sentence_results"]
        self.assertEqual([row["status"] for row in sentence_results], ["supported", "weak", "unsupported"])
        self.assertEqual(payload["citation_verification"]["warnings"][0]["sentence_index"], 3)
        self.assertEqual(payload["citation_verification"]["warnings"][0]["reason"], "low_semantic_overlap")

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
