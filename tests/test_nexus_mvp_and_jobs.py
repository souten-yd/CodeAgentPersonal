import json
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.nexus.db import get_conn
from app.nexus.evidence import EvidenceItem
from app.nexus.jobs import append_job_event, append_job_heartbeat, create_job, get_job, get_job_events
from app.nexus.market import run_market_mvp
from app.nexus.news import run_news_mvp


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NexusMvpAndJobsTests(unittest.TestCase):
    def test_news_mvp_headlines_use_title_then_quote_without_metadata_attr(self) -> None:
        evidence_items = [
            EvidenceItem(
                source_type="web",
                document_id="doc-1",
                chunk_id="chunk-1",
                url="https://example.com/1",
                retrieved_at=_now_iso(),
                title="Primary title",
                quote="quote-1",
                metadata_json={"title": "meta-title-1"},
            ),
            EvidenceItem(
                source_type="web",
                document_id="doc-2",
                chunk_id="chunk-2",
                url="https://example.com/2",
                retrieved_at=_now_iso(),
                title="",
                quote="Fallback quote",
                metadata_json={},
            ),
        ]

        with patch("app.nexus.news.load_runtime_config", return_value=SimpleNamespace(enable_news=True)), patch(
            "app.nexus.news.create_job", return_value=None
        ), patch("app.nexus.news.update_job", return_value=None), patch(
            "app.nexus.news.plan_web_queries", return_value=["q"]
        ), patch(
            "app.nexus.news.run_web_search",
            return_value={"items": [{"title": "a"}]},
        ), patch(
            "app.nexus.news.build_web_evidence", return_value=evidence_items
        ), patch("app.nexus.news.save_evidence_items", return_value=len(evidence_items)):
            result = run_news_mvp("ai")

        points = result["digest"]["template"]["key_points"]
        self.assertEqual(points[0], "Primary title")
        self.assertEqual(points[1], "Fallback quote")

    def test_market_mvp_catalysts_fallback_to_metadata_then_quote(self) -> None:
        evidence_items = [
            EvidenceItem(
                source_type="web",
                document_id="doc-1",
                chunk_id="chunk-1",
                url="https://example.com/1",
                retrieved_at=_now_iso(),
                title="",
                quote="Fallback quote",
                metadata_json={"title": "Metadata title"},
            ),
            EvidenceItem(
                source_type="web",
                document_id="doc-2",
                chunk_id="chunk-2",
                url="https://example.com/2",
                retrieved_at=_now_iso(),
                title="",
                quote="Quote title",
                metadata_json={},
            ),
        ]

        with patch("app.nexus.market.load_runtime_config", return_value=SimpleNamespace(enable_market=True)), patch(
            "app.nexus.market.create_job", return_value=None
        ), patch("app.nexus.market.update_job", return_value=None), patch(
            "app.nexus.market.plan_web_queries", return_value=["q"]
        ), patch(
            "app.nexus.market.run_web_search",
            return_value={"items": [{"title": "a"}]},
        ), patch(
            "app.nexus.market.build_web_evidence", return_value=evidence_items
        ), patch("app.nexus.market.save_evidence_items", return_value=len(evidence_items)):
            result = run_market_mvp("NVDA")

        catalysts = result["snapshot"]["template"]["catalysts"]
        self.assertEqual(catalysts[0], "Metadata title")
        self.assertEqual(catalysts[1], "Quote title")

    def test_get_job_events_normalizes_legacy_planning_status(self) -> None:
        job_id = f"job_legacy_{uuid.uuid4().hex[:8]}"
        now = _now_iso()
        create_job(job_id, title="legacy", status="queued")
        legacy_payload = {"status": "planning", "message": "Planning...", "progress": 0.1, "updated_at": now}
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO nexus_job_events(job_id, seq, type, data, ts)
                VALUES(?, ?, ?, ?, ?)
                """,
                (job_id, 0, "planning", json.dumps(legacy_payload, ensure_ascii=False), now),
            )
            conn.commit()

        events = get_job_events(job_id, after=-1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, "running")
        self.assertEqual(events[0].data.get("original_status"), "planning")

    def test_append_job_event_normalizes_non_job_status_to_running(self) -> None:
        job_id = f"job_append_{uuid.uuid4().hex[:8]}"
        create_job(job_id, title="append", status="queued")

        event = append_job_event(
            job_id,
            "state_transition",
            {"status": "planning", "phase": "planning", "message": "Planning...", "progress": 0.1},
        )

        self.assertEqual(event.status, "running")
        self.assertEqual(event.data.get("original_status"), "planning")
        self.assertEqual(event.data.get("phase"), "planning")

    def test_append_job_event_auto_recovers_missing_parent_with_warning_info(self) -> None:
        job_id = f"job_missing_{uuid.uuid4().hex[:8]}"
        event = append_job_event(
            job_id,
            "ingest.started",
            {"message": "start"},
        )
        warning = event.data.get("auto_recovery_warning")
        self.assertIsInstance(warning, dict)
        self.assertEqual(warning.get("reason"), "missing_parent_job_auto_recovered")
        self.assertEqual(warning.get("job_id"), job_id)
        self.assertEqual(warning.get("event_type"), "ingest.started")
        self.assertTrue(str(warning.get("created_at") or "").strip())

    def test_append_job_heartbeat_persists_event_and_updates_job_timestamp(self) -> None:
        job_id = f"job_hb_{uuid.uuid4().hex[:8]}"
        create_job(job_id, title="hb", status="queued")
        before_updated_at = None
        with get_conn() as conn:
            row = conn.execute("SELECT updated_at FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
            before_updated_at = str(row["updated_at"] or "") if row else ""
        event = append_job_heartbeat(
            job_id,
            "answer_llm_generating",
            "heartbeat",
            0.85,
            {"elapsed_sec": 3.2},
        )
        self.assertEqual(event.type, "heartbeat")
        self.assertEqual(event.data.get("phase"), "answer_llm_generating")
        self.assertIn("heartbeat_at", event.data)
        job = get_job(job_id)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job.status, "running")
        self.assertEqual(job.message, "heartbeat")
        self.assertNotEqual(str(job.updated_at), before_updated_at)


if __name__ == "__main__":
    unittest.main()
