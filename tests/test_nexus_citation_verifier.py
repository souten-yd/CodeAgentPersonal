import unittest

from app.nexus.answer_builder import build_answer_payload
from app.nexus.citation_verifier import (
    HeuristicCitationSupportVerifier,
    LLMNLICitationSupportVerifier,
    evaluate_sentence_citations,
    verify_citation_labels,
)


class _AlwaysWeakVerifier:
    def evaluate(self, *, answer_text: str, evidence_chunks: list[dict]) -> dict:
        return {
            "sentence_results": [
                {
                    "sentence_index": 1,
                    "sentence": answer_text,
                    "citations": ["[S1]"],
                    "status": "weak",
                    "best_score": 0.0,
                    "matched_evidence": [],
                }
            ],
            "warnings": [
                {
                    "sentence_index": 1,
                    "sentence": answer_text,
                    "citations": ["[S1]"],
                    "status": "weak",
                    "reason": "custom_verifier",
                    "best_score": 0.0,
                }
            ],
        }


class NexusCitationVerifierContractTests(unittest.TestCase):
    def test_heuristic_evaluate_matches_legacy_function_output(self) -> None:
        answer_text = "東京の人口は約1400万人です。[S1]"
        evidence_chunks = [{"citation_label": "[S1]", "source_id": "src-1", "quote": "東京の人口は約1400万人です。"}]

        legacy = evaluate_sentence_citations(answer_text=answer_text, evidence_chunks=evidence_chunks)
        current = HeuristicCitationSupportVerifier().evaluate(answer_text=answer_text, evidence_chunks=evidence_chunks)

        self.assertEqual(legacy, current)
        self.assertEqual(set(current.keys()), {"sentence_results", "warnings"})

    def test_verify_citation_labels_accepts_injected_verifier_and_keeps_schema(self) -> None:
        result = verify_citation_labels(
            answer_text="結論です。[S1]",
            references=[{"citation_label": "[S1]"}],
            evidence_chunks=[{"citation_label": "[S1]", "quote": "x"}],
            verifier=_AlwaysWeakVerifier(),
        )

        self.assertEqual(
            set(result.keys()),
            {"ok", "missing_in_references", "unused_references", "invalid_labels", "sentence_results", "warnings"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["warnings"][0]["reason"], "custom_verifier")

    def test_answer_builder_can_use_injected_verifier_without_changing_response_shape(self) -> None:
        payload = build_answer_payload(
            question="質問",
            summary="結論です [S1]",
            references=[{"citation_label": "src-1", "title": "Source 1", "source_id": "src-1"}],
            evidence_chunks=[{"citation_label": "src-1", "source_id": "src-1", "quote": "fact"}],
            citation_support_verifier=_AlwaysWeakVerifier(),
        )

        verification = payload["citation_verification"]
        self.assertEqual(
            set(verification.keys()),
            {"ok", "missing_in_references", "unused_references", "invalid_labels", "sentence_results", "warnings"},
        )
        self.assertEqual(verification["warnings"][0]["reason"], "custom_verifier")

    def test_llm_nli_verifier_stub_is_present_but_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            LLMNLICitationSupportVerifier().evaluate(answer_text="x", evidence_chunks=[])


if __name__ == "__main__":
    unittest.main()
