import unittest
import uuid
from unittest.mock import patch

from app.nexus.db import get_conn
from app.nexus.jobs import create_job
from app.nexus.research_agent import ResearchAgentInput, run_research_job


class NexusResearchAgentTests(unittest.TestCase):
    def test_run_research_job_marks_source_degraded_on_403_when_continue_enabled(self) -> None:
        job_id = f"job-continue-403-{uuid.uuid4().hex[:8]}"
        create_job(job_id, title="test", status="queued", message="queued")
        fake_search = {"items": [{"title": "Forbidden", "url": "https://example.com/403", "snippet": "forbidden"}]}

        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value=fake_search
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=fake_search["items"]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=fake_search["items"]
        ), patch(
            "app.nexus.research_agent.safe_download",
            side_effect=ValueError("HTTP 403 forbidden"),
        ), patch(
            "app.nexus.research_agent.build_citation_map", return_value=[]
        ), patch(
            "app.nexus.research_agent.build_answer_payload",
            return_value={"answer": "ok"},
        ):
            run_research_job(
                ResearchAgentInput(
                    query="test",
                    continue_on_download_error=True,
                    max_sources=1,
                ),
                job_id=job_id,
            )

        with get_conn() as conn:
            job_row = conn.execute("SELECT status FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
            source_row = conn.execute(
                "SELECT status, linked_document_id FROM nexus_sources WHERE job_id = ?",
                (job_id,),
            ).fetchone()

        self.assertIsNotNone(job_row)
        self.assertNotEqual(job_row["status"], "failed")
        self.assertIsNotNone(source_row)
        self.assertEqual(source_row["status"], "degraded")
        self.assertIsNone(source_row["linked_document_id"])

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

    def test_run_research_job_constraint_event_includes_download_limits(self) -> None:
        fake_search = {
            "items": [
                {"title": "result1", "url": "https://example.com/1", "snippet": "snippet1"},
                {"title": "result2", "url": "https://example.com/2", "snippet": "snippet2"},
            ]
        }
        registered_sources = [
            {
                "source_id": "src-1",
                "title": "Article",
                "url": "https://example.com/1",
                "final_url": "https://example.com/1",
            }
        ]

        with patch("app.nexus.research_agent._record_state", return_value=None), patch(
            "app.nexus.research_agent.update_job", return_value=None
        ), patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value=fake_search
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=fake_search["items"]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=fake_search["items"]
        ), patch(
            "app.nexus.research_agent.safe_download",
            return_value={"final_url": "https://example.com/1", "size": 10},
        ), patch(
            "app.nexus.research_agent.save_download_artifacts", return_value={"status": "downloaded"}
        ), patch(
            "app.nexus.research_agent.register_or_update_sources", return_value=registered_sources
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch(
            "app.nexus.research_agent.save_evidence_items", return_value=None
        ), patch("app.nexus.research_agent._load_source_chunks", return_value=[]), patch(
            "app.nexus.research_agent.build_citation_map", return_value=[]
        ), patch(
            "app.nexus.research_agent.build_answer_payload",
            return_value={"answer": "ok"},
        ), patch("app.nexus.research_agent.append_job_event") as mocked_append_event:
            run_research_job(
                ResearchAgentInput(
                    query="test",
                    max_sources=1,
                    max_download_mb=7,
                ),
                job_id="job-test",
            )

        constraint_events = [
            call.args[2]
            for call in mocked_append_event.call_args_list
            if len(call.args) >= 3 and call.args[1] == "constraint_applied"
        ]
        self.assertTrue(constraint_events)
        self.assertEqual(constraint_events[0]["max_download_mb"], 7)
        self.assertEqual(constraint_events[0]["max_download_bytes"], 7 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
