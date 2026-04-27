import os
import unittest
from unittest.mock import patch

from app.nexus.answer_builder import build_answer_payload


class NexusAnswerBuilderTests(unittest.TestCase):
    def test_build_answer_payload_uses_llm_when_available(self) -> None:
        references = [{"citation_label": "[S1]", "title": "Source 1", "url": "https://example.com/1"}]
        chunks = [{"quote": "fact", "source_id": "src-1", "citation_label": "[S1]"}]
        llm_text = "結論です [S1]\n\n## 追加確認が必要な点\n- なし"

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

        self.assertEqual(payload["answer"], llm_text)
        self.assertIn(llm_text, payload["answer_markdown"])
        mocked.assert_called_once()

    def test_build_answer_payload_falls_back_when_llm_unavailable(self) -> None:
        references = [{"citation_label": "[S1]", "title": "Source 1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "[S1]"}]

        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=False), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            side_effect=TimeoutError("timeout"),
        ):
            payload = build_answer_payload(
                question="質問",
                summary="fallback summary",
                references=references,
                evidence_chunks=chunks,
            )

        self.assertIn("fallback summary", payload["answer"])
        self.assertIn("[S1]", payload["answer"])
        self.assertIn("## References", payload["answer_markdown"])


if __name__ == "__main__":
    unittest.main()
