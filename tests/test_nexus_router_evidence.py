import unittest
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.nexus.evidence import EvidenceItem, save_evidence_items
from app.nexus.jobs import append_job_heartbeat, create_job
from app.nexus.router import nexus_router


class NexusRouterEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(nexus_router, prefix="/nexus")
        self.client = TestClient(app)

    def test_evidence_endpoint_filters_source_type_without_job_id(self) -> None:
        project = f"proj-{uuid.uuid4().hex[:8]}"
        news_job_id = f"job-news-{uuid.uuid4().hex[:8]}"
        market_job_id = f"job-market-{uuid.uuid4().hex[:8]}"
        create_job(news_job_id, title="news", status="queued", message="queued")
        create_job(market_job_id, title="market", status="queued", message="queued")

        save_evidence_items(
            news_job_id,
            [
                EvidenceItem(
                    source_type="news",
                    document_id="",
                    chunk_id=f"chunk-news-{uuid.uuid4().hex[:6]}",
                    url="https://news.example.com/alpha",
                    title="Alpha News Title",
                    quote="Alpha quote about semiconductor outlook",
                    citation_label="[S1]",
                    retrieved_at="2026-01-01T00:00:00+00:00",
                )
            ],
            project=project,
        )
        save_evidence_items(
            market_job_id,
            [
                EvidenceItem(
                    source_type="market",
                    document_id="",
                    chunk_id=f"chunk-market-{uuid.uuid4().hex[:6]}",
                    url="https://market.example.com/beta",
                    title="Beta Market Title",
                    quote="Beta quote for macro trend",
                    citation_label="[S2]",
                    retrieved_at="2026-01-01T00:00:00+00:00",
                )
            ],
            project=project,
        )

        news_response = self.client.get(f"/nexus/evidence?project={project}&source_type=news")
        self.assertEqual(news_response.status_code, 200)
        news_items = news_response.json()["items"]
        self.assertEqual(len(news_items), 1)
        self.assertEqual(news_items[0]["source_type"], "news")
        self.assertEqual(news_items[0]["title"], "Alpha News Title")

        market_response = self.client.get(f"/nexus/evidence?project={project}&source_type=market")
        self.assertEqual(market_response.status_code, 200)
        market_items = market_response.json()["items"]
        self.assertEqual(len(market_items), 1)
        self.assertEqual(market_items[0]["source_type"], "market")
        self.assertEqual(market_items[0]["title"], "Beta Market Title")

        title_filter_response = self.client.get(
            f"/nexus/evidence?project={project}&source_type=news&filter=alpha%20news"
        )
        self.assertEqual(title_filter_response.status_code, 200)
        self.assertEqual(title_filter_response.json()["total"], 1)

        quote_filter_response = self.client.get(
            f"/nexus/evidence?project={project}&source_type=market&filter=macro%20trend"
        )
        self.assertEqual(quote_filter_response.status_code, 200)
        self.assertEqual(quote_filter_response.json()["total"], 1)

        url_filter_response = self.client.get(
            f"/nexus/evidence?project={project}&source_type=news&filter=news.example.com"
        )
        self.assertEqual(url_filter_response.status_code, 200)
        self.assertEqual(url_filter_response.json()["total"], 1)

    def test_evidence_endpoint_job_id_filter_is_backward_compatible(self) -> None:
        project = f"proj-{uuid.uuid4().hex[:8]}"
        target_job_id = f"job-target-{uuid.uuid4().hex[:8]}"
        other_job_id = f"job-other-{uuid.uuid4().hex[:8]}"
        create_job(target_job_id, title="target", status="queued", message="queued")
        create_job(other_job_id, title="other", status="queued", message="queued")

        save_evidence_items(
            target_job_id,
            [
                EvidenceItem(
                    source_type="news",
                    document_id="",
                    chunk_id=f"chunk-target-{uuid.uuid4().hex[:6]}",
                    url="https://example.com/target",
                    title="Target job evidence",
                    quote="target quote",
                    citation_label="[S1]",
                    retrieved_at="2026-01-01T00:00:00+00:00",
                )
            ],
            project=project,
        )
        save_evidence_items(
            other_job_id,
            [
                EvidenceItem(
                    source_type="news",
                    document_id="",
                    chunk_id=f"chunk-other-{uuid.uuid4().hex[:6]}",
                    url="https://example.com/other",
                    title="Other job evidence",
                    quote="other quote",
                    citation_label="[S2]",
                    retrieved_at="2026-01-01T00:00:00+00:00",
                )
            ],
            project=project,
        )

        response = self.client.get(f"/nexus/evidence?job_id={target_job_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["job_id"], target_job_id)
        self.assertEqual(payload["items"][0]["title"], "Target job evidence")

    def test_debug_endpoint_returns_health(self) -> None:
        job_id = f"job-debug-{uuid.uuid4().hex[:8]}"
        create_job(job_id, title="debug", status="running", message="running")
        append_job_heartbeat(job_id, "downloading", "progress", 0.4, {"active": 1})
        response = self.client.get(f"/nexus/research/jobs/{job_id}/debug")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("job_id"), job_id)
        self.assertIn("health", payload)
        self.assertIn("is_stalled", payload.get("health", {}))


if __name__ == "__main__":
    unittest.main()
