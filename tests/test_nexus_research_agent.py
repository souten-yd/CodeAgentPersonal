import unittest
from unittest.mock import patch

from app.nexus.research_agent import ResearchAgentInput, run_research_job


class NexusResearchAgentTests(unittest.TestCase):
    def test_run_research_job_passes_evidence_chunks_to_answer_builder(self) -> None:
        fake_search = {
            "items": [
                {
                    "title": "result",
                    "url": "https://example.com/article",
                    "snippet": "snippet",
                }
            ]
        }
        registered_sources = [
            {
                "source_id": "src-1",
                "title": "Article",
                "url": "https://example.com/article",
                "final_url": "https://example.com/article",
            }
        ]
        source_chunks = [{"source_id": "src-1", "quote": "quoted evidence", "citation_label": "article#1"}]
        references = [
            {
                "citation_label": "article#1",
                "title": "Article",
                "url": "https://example.com/article",
                "source_id": "src-1",
            }
        ]

        with patch("app.nexus.research_agent._record_state", return_value=None), patch(
            "app.nexus.research_agent.update_job", return_value=None
        ), patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value=fake_search
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=fake_search["items"]), patch(
            "app.nexus.research_agent.safe_download", return_value={"final_url": "https://example.com/article"}
        ), patch("app.nexus.research_agent.save_download_artifacts", return_value={"status": "downloaded"}), patch(
            "app.nexus.research_agent.register_or_update_sources", return_value=registered_sources
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch(
            "app.nexus.research_agent.save_evidence_items", return_value=None
        ), patch("app.nexus.research_agent._load_source_chunks", return_value=source_chunks), patch(
            "app.nexus.research_agent.build_citation_map", return_value=references
        ), patch(
            "app.nexus.research_agent.build_answer_payload",
            return_value={"answer": "ok"},
        ) as mocked_build_answer:
            result = run_research_job(ResearchAgentInput(query="test"), job_id="job-test")

        self.assertEqual(result["answer"]["answer"], "ok")
        kwargs = mocked_build_answer.call_args.kwargs
        self.assertEqual(kwargs["references"][0]["citation_label"], "[S1]")
        self.assertEqual(kwargs["evidence_chunks"][0]["citation_label"], "[S1]")


if __name__ == "__main__":
    unittest.main()
