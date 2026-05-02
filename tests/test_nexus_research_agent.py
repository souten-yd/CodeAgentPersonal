import time
import unittest
import uuid
from unittest.mock import patch

from app.nexus.db import get_conn
from app.nexus.evidence import EvidenceItem, list_evidence_items, replace_evidence_items_for_job, save_evidence_items
from app.nexus.jobs import create_job
from app.nexus.research_agent import ResearchAgentInput, _download_sources_parallel, _should_stop_recursive_research, run_research_job


class NexusResearchAgentTests(unittest.TestCase):
    def test_download_parallel_event_does_not_fail_job_on_parallel_events(self) -> None:
        job_id = f"job-parallel-{uuid.uuid4().hex[:8]}"
        create_job(job_id, title="parallel", status="running", message="running")
        candidates = [{"url": f"https://example.com/{i}", "title": f"t-{i}"} for i in range(8)]

        def _fake_download(url: str, **_: dict) -> dict:
            time.sleep(0.01)
            return {"final_url": url, "content_type": "text/html", "size": 10, "bytes": b"ok", "extension": ".html"}

        with patch("app.nexus.research_agent.safe_download", side_effect=_fake_download), patch(
            "app.nexus.research_agent.save_download_artifacts",
            return_value={"status": "downloaded", "original": "o", "extracted_txt": "t", "extracted_md": "m"},
        ):
            sources, errors = _download_sources_parallel(
                job_id=job_id,
                candidates=candidates,
                max_downloads=8,
                max_download_bytes=2048,
                max_total_download_bytes=100_000,
                download_timeout_sec=2,
                continue_on_download_error=True,
                concurrency=4,
                pdf_extract_concurrency=1,
                download_progress_interval_sec=1,
                download_stalled_after_sec=30,
            )

        self.assertEqual(errors, 0)
        self.assertTrue(all(str(s.get("status")) in {"downloaded", "degraded"} for s in sources))
        with get_conn() as conn:
            statuses = conn.execute("SELECT status FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
            started_count = conn.execute(
                "SELECT COUNT(*) AS c FROM nexus_job_events WHERE job_id = ? AND type = 'download_source_started'",
                (job_id,),
            ).fetchone()
            progress_count = conn.execute(
                "SELECT COUNT(*) AS c FROM nexus_job_events WHERE job_id = ? AND type = 'download_progress'",
                (job_id,),
            ).fetchone()
        self.assertNotEqual(str((statuses or {})["status"]), "failed")
        self.assertGreater(int((started_count or {})["c"]), 0)
        self.assertGreater(int((progress_count or {})["c"]), 0)

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

    def test_run_research_job_sets_terminal_status_and_completed_event(self) -> None:
        fake_search = {"items": [{"title": "result", "url": "https://example.com/article", "snippet": "snippet"}]}
        registered_sources = [{"source_id": "src-1", "title": "Article", "url": "https://example.com/article", "final_url": "https://example.com/article", "status": "downloaded"}]

        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value=fake_search
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=fake_search["items"]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=fake_search["items"]
        ), patch("app.nexus.research_agent.safe_download", return_value={"final_url": "https://example.com/article"}), patch(
            "app.nexus.research_agent.save_download_artifacts", return_value={"status": "downloaded"}
        ), patch("app.nexus.research_agent.register_or_update_sources", return_value=registered_sources), patch(
            "app.nexus.research_agent._build_evidence_from_sources", return_value=[]
        ), patch("app.nexus.research_agent.save_evidence_items", return_value=None), patch(
            "app.nexus.research_agent._load_source_chunks", return_value=[]
        ), patch("app.nexus.research_agent.build_citation_map", return_value=[]), patch(
            "app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}
        ):
            job_id = f"job-terminal-{uuid.uuid4().hex[:8]}"
            create_job(job_id, title="terminal", status="queued", message="queued")
            run_research_job(ResearchAgentInput(query="test"), job_id=job_id)

        with get_conn() as conn:
            row = conn.execute("SELECT status, progress FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
            completed_event = conn.execute(
                "SELECT data FROM nexus_job_events WHERE job_id = ? AND type = 'research_completed' ORDER BY seq DESC LIMIT 1",
                (job_id,),
            ).fetchone()

        self.assertIn(str(row["status"]), {"completed", "degraded"})
        self.assertEqual(float(row["progress"]), 1.0)
        self.assertIsNotNone(completed_event)


class NexusResearchParallelDownloadTests(unittest.TestCase):
    def test_parallel_download_is_faster_than_serial(self) -> None:
        candidates = [{"url": f"https://example.com/{i}", "title": f"t{i}"} for i in range(5)]

        def _slow_download(url: str, **_: dict) -> dict:
            time.sleep(0.2)
            return {"final_url": url, "content_type": "text/html", "size": 16, "bytes": b"ok", "extension": ".html"}

        with patch("app.nexus.research_agent.safe_download", side_effect=_slow_download), patch(
            "app.nexus.research_agent.save_download_artifacts",
            return_value={"status": "downloaded", "original": "o", "extracted_txt": "t", "extracted_md": "m"},
        ), patch("app.nexus.research_agent.append_job_event", return_value=None), patch(
            "app.nexus.research_agent.append_job_heartbeat", return_value=None
        ):
            start = time.monotonic()
            _download_sources_parallel(
                job_id="job-parallel",
                candidates=candidates,
                max_downloads=5,
                max_download_bytes=1024,
                max_total_download_bytes=10_000,
                download_timeout_sec=3,
                continue_on_download_error=True,
                concurrency=5,
                pdf_extract_concurrency=1,
                download_progress_interval_sec=1,
                download_stalled_after_sec=60,
            )
            elapsed_parallel = time.monotonic() - start

            start = time.monotonic()
            _download_sources_parallel(
                job_id="job-serial",
                candidates=candidates,
                max_downloads=5,
                max_download_bytes=1024,
                max_total_download_bytes=10_000,
                download_timeout_sec=3,
                continue_on_download_error=True,
                concurrency=1,
                pdf_extract_concurrency=1,
                download_progress_interval_sec=1,
                download_stalled_after_sec=60,
            )
            elapsed_serial = time.monotonic() - start

        self.assertLess(elapsed_parallel, elapsed_serial)

    def test_timeout_does_not_stop_others_when_continue_true(self) -> None:
        candidates = [{"url": "https://example.com/ok"}, {"url": "https://example.com/timeout"}]

        def _download(url: str, **_: dict) -> dict:
            if "timeout" in url:
                raise ValueError("download failed: timeout")
            return {"final_url": url, "content_type": "text/html", "size": 12, "bytes": b"ok", "extension": ".html"}

        with patch("app.nexus.research_agent.safe_download", side_effect=_download), patch(
            "app.nexus.research_agent.save_download_artifacts",
            return_value={"status": "downloaded", "original": "o", "extracted_txt": "t", "extracted_md": "m"},
        ), patch("app.nexus.research_agent.append_job_event", return_value=None), patch(
            "app.nexus.research_agent.append_job_heartbeat", return_value=None
        ):
            sources, errors = _download_sources_parallel(
                job_id="job-timeout",
                candidates=candidates,
                max_downloads=2,
                max_download_bytes=1024,
                max_total_download_bytes=10_000,
                download_timeout_sec=1,
                continue_on_download_error=True,
                concurrency=2,
                pdf_extract_concurrency=1,
                download_progress_interval_sec=1,
                download_stalled_after_sec=60,
            )

        statuses = {str(row.get("status")) for row in sources}
        self.assertIn("downloaded", statuses)
        self.assertIn("degraded", statuses)
        self.assertEqual(errors, 1)

    def test_download_progress_emits_multiple_times(self) -> None:
        candidates = [{"url": f"https://example.com/{i}"} for i in range(3)]
        captured_events: list[str] = []

        def _slow_download(url: str, **_: dict) -> dict:
            time.sleep(0.08)
            return {"final_url": url, "content_type": "text/html", "size": 12, "bytes": b"ok", "extension": ".html"}

        def _capture_event(_job_id: str, event_type: str, _payload: dict) -> None:
            captured_events.append(event_type)

        with patch("app.nexus.research_agent.safe_download", side_effect=_slow_download), patch(
            "app.nexus.research_agent.save_download_artifacts",
            return_value={"status": "downloaded", "original": "o", "extracted_txt": "t", "extracted_md": "m"},
        ), patch("app.nexus.research_agent.append_job_event", side_effect=_capture_event), patch(
            "app.nexus.research_agent.append_job_heartbeat", return_value=None
        ):
            _download_sources_parallel(
                job_id="job-progress",
                candidates=candidates,
                max_downloads=3,
                max_download_bytes=1024,
                max_total_download_bytes=10_000,
                download_timeout_sec=1,
                continue_on_download_error=True,
                concurrency=2,
                pdf_extract_concurrency=1,
                download_progress_interval_sec=1,
                download_stalled_after_sec=60,
            )

        progress_count = sum(1 for ev in captured_events if ev == "download_progress")
        self.assertGreaterEqual(progress_count, 2)

    def test_max_downloads_and_total_size_limit_mark_skipped(self) -> None:
        candidates = [{"url": f"https://example.com/{i}"} for i in range(4)]

        with patch("app.nexus.research_agent.safe_download", return_value={"final_url": "https://example.com", "content_type": "text/html", "size": 600, "bytes": b"x", "extension": ".html"}), patch(
            "app.nexus.research_agent.save_download_artifacts",
            return_value={"status": "downloaded", "original": "o", "extracted_txt": "t", "extracted_md": "m"},
        ), patch("app.nexus.research_agent.append_job_event", return_value=None), patch(
            "app.nexus.research_agent.append_job_heartbeat", return_value=None
        ):
            sources, _ = _download_sources_parallel(
                job_id="job-limits",
                candidates=candidates,
                max_downloads=3,
                max_download_bytes=2048,
                max_total_download_bytes=1000,
                download_timeout_sec=1,
                continue_on_download_error=True,
                concurrency=3,
                pdf_extract_concurrency=1,
                download_progress_interval_sec=1,
                download_stalled_after_sec=60,
            )

        skipped = [row for row in sources if str(row.get("status")) == "skipped_download_limit"]
        self.assertGreaterEqual(len(skipped), 2)

    def test_download_phase_events_are_normalized_to_downloading(self) -> None:
        candidates = [{"url": "https://example.com/1"}]
        captured_payloads: list[dict] = []

        def _capture_event(_job_id: str, _event_type: str, payload: dict) -> None:
            captured_payloads.append(payload)

        with patch(
            "app.nexus.research_agent.safe_download",
            return_value={"final_url": "https://example.com/1", "content_type": "text/html", "size": 10, "bytes": b"ok", "extension": ".html"},
        ), patch(
            "app.nexus.research_agent.save_download_artifacts",
            return_value={"status": "downloaded", "original": "o", "extracted_txt": "t", "extracted_md": "m"},
        ), patch("app.nexus.research_agent.append_job_event", side_effect=_capture_event), patch(
            "app.nexus.research_agent.append_job_heartbeat", return_value=None
        ):
            _download_sources_parallel(
                job_id="job-phase",
                candidates=candidates,
                max_downloads=1,
                max_download_bytes=2048,
                max_total_download_bytes=10_000,
                download_timeout_sec=1,
                continue_on_download_error=True,
                concurrency=1,
                pdf_extract_concurrency=1,
                download_progress_interval_sec=1,
                download_stalled_after_sec=60,
            )

        phases = [str(p.get("phase") or "") for p in captured_payloads if isinstance(p, dict)]
        self.assertIn("downloading", phases)
        self.assertNotIn("download", phases)

    def test_answer_generation_mode_llm_answer_emits_finished_event_with_incomplete_details(self) -> None:
        fake_search = {"items": [{"title": "result", "url": "https://example.com/article", "snippet": "snippet"}]}
        registered_sources = [{"source_id": "src-1", "title": "Article", "url": "https://example.com/article"}]
        captured: list[tuple[str, dict]] = []

        def _capture_event(_job_id: str, event_type: str, payload: dict) -> None:
            captured.append((event_type, payload))

        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value=fake_search
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=fake_search["items"]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=fake_search["items"]
        ), patch(
            "app.nexus.research_agent.safe_download",
            return_value={"final_url": "https://example.com/article", "content_type": "text/html", "size": 10, "bytes": b"ok", "extension": ".html"},
        ), patch(
            "app.nexus.research_agent.save_download_artifacts", return_value={"status": "downloaded", "original": "o", "extracted_txt": "t", "extracted_md": "m"}
        ), patch(
            "app.nexus.research_agent.register_or_update_sources", return_value=registered_sources
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch(
            "app.nexus.research_agent.save_evidence_items", return_value=None
        ), patch("app.nexus.research_agent._load_source_chunks", return_value=[]), patch(
            "app.nexus.research_agent.build_citation_map", return_value=[]
        ), patch(
            "app.nexus.research_agent.build_answer_payload",
            return_value={
                "generation": {"mode": "llm_answer", "finish_reason": "stop", "output_incomplete": True, "output_truncated": False},
                "output_incomplete": True,
                "output_truncated": False,
            },
        ), patch("app.nexus.research_agent.append_job_event", side_effect=_capture_event):
            run_research_job(ResearchAgentInput(query="test"), job_id="job-answer-mode")

        finished = [item for item in captured if item[0] == "answer_llm_request_finished"]
        self.assertTrue(finished)
        details = finished[-1][1].get("details") if isinstance(finished[-1][1], dict) else {}
        self.assertTrue(bool((details or {}).get("output_incomplete")))


class NexusResearchRecursiveTests(unittest.TestCase):
    def test_recursive_search_false_keeps_existing_path(self) -> None:
        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value={"items": []}
        ) as mocked_search, patch("app.nexus.research_agent.collect_source_candidates", return_value=[]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=[]
        ), patch("app.nexus.research_agent.register_or_update_sources", return_value=[]), patch(
            "app.nexus.research_agent._build_evidence_from_sources", return_value=[]
        ), patch("app.nexus.research_agent.save_evidence_items", return_value=0), patch(
            "app.nexus.research_agent._load_source_chunks", return_value=[]
        ), patch("app.nexus.research_agent.build_citation_map", return_value=[]), patch(
            "app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}
        ):
            run_research_job(ResearchAgentInput(query="q", recursive_search=False), job_id="job-r0")
        self.assertEqual(mocked_search.call_count, 1)

    def test_recursive_followup_uses_string_queries_and_updates_evidence(self) -> None:
        search_calls: list[list] = []
        replace_calls: list[list] = []

        def _mock_search(queries, **kwargs):
            search_calls.append(list(queries))
            return {"items": [{"url": "https://example.com/new", "title": "new"}]}

        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", side_effect=_mock_search
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=[{"url": "https://example.com/new", "title": "new"}]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=[{"url": "https://example.com/new", "title": "new"}]
        ), patch("app.nexus.research_agent._download_sources_parallel", return_value=([{"source_id": "src-2", "url": "https://example.com/new", "final_url": "https://example.com/new", "status": "downloaded", "size": 10}], 0)), patch(
            "app.nexus.research_agent.register_or_update_sources",
            side_effect=[
                [{"source_id": "src-1", "url": "https://example.com/old", "final_url": "https://example.com/old"}],
                [{"source_id": "src-2", "url": "https://example.com/new", "final_url": "https://example.com/new"}],
            ],
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch(
            "app.nexus.research_agent.save_evidence_items", return_value=0
        ), patch("app.nexus.research_agent.replace_evidence_items_for_job", side_effect=lambda *args, **kwargs: replace_calls.append(args[1]) or 0), patch(
            "app.nexus.research_agent._load_source_chunks", return_value=[]
        ), patch("app.nexus.research_agent.build_citation_map", return_value=[]), patch(
            "app.nexus.research_agent._analyze_research_gaps",
            side_effect=[{"confidence": 0.1, "gaps": ["source_count_low"], "unresolved_items": []}, {"confidence": 0.9, "gaps": [], "unresolved_items": []}],
        ), patch("app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}):
            run_research_job(ResearchAgentInput(query="q", recursive_search=True, max_iterations=2), job_id="job-r1")
        self.assertTrue(all(isinstance(q, str) for q in search_calls[-1]))
        self.assertTrue(replace_calls)

    def test_recursive_download_budget_exhaustion_stops(self) -> None:
        captured = []
        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value={"items": []}
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=[]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=[]
        ), patch("app.nexus.research_agent._download_sources_parallel", return_value=([{"source_id": "src-1", "status": "downloaded", "size": 10}], 0)), patch(
            "app.nexus.research_agent.register_or_update_sources", return_value=[{"source_id": "src-1", "url": "https://example.com/1"}]
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch(
            "app.nexus.research_agent.save_evidence_items", return_value=0
        ), patch("app.nexus.research_agent.replace_evidence_items_for_job", return_value=0), patch(
            "app.nexus.research_agent._load_source_chunks", return_value=[]
        ), patch("app.nexus.research_agent.build_citation_map", return_value=[]), patch(
            "app.nexus.research_agent._analyze_research_gaps", return_value={"confidence": 0.1, "gaps": ["source_count_low"], "unresolved_items": []}
        ), patch("app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}), patch(
            "app.nexus.research_agent.append_job_event", side_effect=lambda _jid, et, payload: captured.append((et, payload))
        ):
            run_research_job(
                ResearchAgentInput(query="q", recursive_search=True, max_iterations=2, max_downloads=0, max_total_download_mb=1),
                job_id="job-r2",
            )
        stops = [p for e, p in captured if e == "recursive_stopped" and p.get("reason") == "download_budget_exhausted"]
        self.assertTrue(stops)

    def test_recursive_stops_no_new_sources_when_filtered_candidates_empty(self) -> None:
        captured = []
        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value={"items": [{"url": "https://example.com/1"}]}
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=[{"url": "https://example.com/1"}]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=[{"url": "https://example.com/1"}]
        ), patch(
            "app.nexus.research_agent.register_or_update_sources",
            return_value=[{"source_id": "src-1", "url": "https://example.com/1", "final_url": "https://example.com/1"}],
        ), patch(
            "app.nexus.research_agent._download_sources_parallel",
            return_value=([{"source_id": "src-1", "url": "https://example.com/1", "status": "downloaded", "size": 10}], 0),
        ) as mocked_followup_download, patch(
            "app.nexus.research_agent._build_evidence_from_sources", return_value=[]
        ), patch("app.nexus.research_agent.save_evidence_items", return_value=0), patch(
            "app.nexus.research_agent.replace_evidence_items_for_job", return_value=0
        ), patch("app.nexus.research_agent._load_source_chunks", return_value=[]), patch(
            "app.nexus.research_agent.build_citation_map", return_value=[]
        ), patch(
            "app.nexus.research_agent._analyze_research_gaps", return_value={"confidence": 0.1, "gaps": ["source_count_low"], "unresolved_items": []}
        ), patch("app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}), patch(
            "app.nexus.research_agent.append_job_event", side_effect=lambda _jid, et, payload: captured.append((et, payload))
        ):
            run_research_job(ResearchAgentInput(query="q", recursive_search=True, max_iterations=2), job_id="job-r3")
        stops = [p for e, p in captured if e == "recursive_stopped" and p.get("reason") == "no_new_sources"]
        self.assertTrue(stops)
        self.assertEqual(mocked_followup_download.call_count, 1)

    def test_recursive_stops_no_new_sources_when_registered_empty(self) -> None:
        captured = []
        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value={"items": [{"url": "https://example.com/new"}]}
        ), patch("app.nexus.research_agent.collect_source_candidates", return_value=[{"url": "https://example.com/new"}]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=[{"url": "https://example.com/new"}]
        ), patch(
            "app.nexus.research_agent._download_sources_parallel",
            return_value=([{"source_id": "src-2", "url": "https://example.com/new", "status": "downloaded", "size": 10}], 0),
        ), patch(
            "app.nexus.research_agent.register_or_update_sources",
            side_effect=[
                [{"source_id": "src-1", "url": "https://example.com/old", "final_url": "https://example.com/old"}],
                [],
            ],
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch(
            "app.nexus.research_agent.save_evidence_items", return_value=0
        ), patch("app.nexus.research_agent.replace_evidence_items_for_job", return_value=0), patch(
            "app.nexus.research_agent._load_source_chunks", return_value=[]
        ), patch("app.nexus.research_agent.build_citation_map", return_value=[]), patch(
            "app.nexus.research_agent._analyze_research_gaps", return_value={"confidence": 0.1, "gaps": ["source_count_low"], "unresolved_items": []}
        ), patch("app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}), patch(
            "app.nexus.research_agent.append_job_event", side_effect=lambda _jid, et, payload: captured.append((et, payload))
        ):
            run_research_job(ResearchAgentInput(query="q", recursive_search=True, max_iterations=2), job_id="job-r4")
        stops = [p for e, p in captured if e == "recursive_stopped" and p.get("reason") == "no_new_sources"]
        self.assertTrue(stops)

    def test_should_stop_prefers_confidence_when_sufficient_enabled(self) -> None:
        should_stop, reason = _should_stop_recursive_research(
            analysis={"confidence": 0.9, "sufficient": False},
            iteration=2,
            payload=ResearchAgentInput(query="q", recursive_search=True, max_iterations=2, confidence_threshold=0.75),
        )
        self.assertTrue(should_stop)
        self.assertEqual(reason, "confidence_threshold_reached")

    def test_recursive_max_iterations_1_executes_single_followup_search(self) -> None:
        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value={"items": [{"url": "https://example.com/new", "title": "new"}]}
        ) as mocked_search, patch("app.nexus.research_agent.collect_source_candidates", return_value=[{"url": "https://example.com/new", "title": "new"}]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=[{"url": "https://example.com/new", "title": "new"}]
        ), patch("app.nexus.research_agent._download_sources_parallel", return_value=([{"source_id": "src-2", "url": "https://example.com/new", "final_url": "https://example.com/new", "status": "downloaded", "size": 10}], 0)), patch(
            "app.nexus.research_agent.register_or_update_sources",
            side_effect=[[{"source_id": "src-1", "url": "https://example.com/old", "final_url": "https://example.com/old"}], [{"source_id": "src-2", "url": "https://example.com/new", "final_url": "https://example.com/new"}]],
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch("app.nexus.research_agent.save_evidence_items", return_value=0), patch(
            "app.nexus.research_agent.replace_evidence_items_for_job", return_value=0
        ), patch("app.nexus.research_agent._load_source_chunks", return_value=[]), patch(
            "app.nexus.research_agent.build_citation_map", return_value=[]
        ), patch("app.nexus.research_agent._analyze_research_gaps", return_value={"confidence": 0.1, "gaps": ["source_count_low"], "unresolved_items": []}), patch(
            "app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}
        ):
            result = run_research_job(ResearchAgentInput(query="q", recursive_search=True, max_iterations=1), job_id="job-r5")
        self.assertEqual(mocked_search.call_count, 2)
        self.assertEqual(result["answer"]["followup_search_count"], 1)

    def test_recursive_max_iterations_2_executes_two_followup_searches_without_early_stop(self) -> None:
        captured = []
        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search",
            side_effect=[{"items": [{"url": "https://example.com/new-1"}]}, {"items": [{"url": "https://example.com/new-2"}]}, {"items": [{"url": "https://example.com/new-3"}]}],
        ) as mocked_search, patch(
            "app.nexus.research_agent.collect_source_candidates",
            side_effect=[[{"url": "https://example.com/new-1"}], [{"url": "https://example.com/new-2"}], [{"url": "https://example.com/new-3"}]],
        ), patch(
            "app.nexus.research_agent.rank_source_candidates",
            side_effect=[[{"url": "https://example.com/new-1"}], [{"url": "https://example.com/new-2"}], [{"url": "https://example.com/new-3"}]],
        ), patch(
            "app.nexus.research_agent._download_sources_parallel",
            side_effect=[([{"source_id": "src-1", "url": "https://example.com/old", "status": "downloaded", "size": 10}], 0), ([{"source_id": "src-2", "url": "https://example.com/new-1", "status": "downloaded", "size": 10}], 0), ([{"source_id": "src-3", "url": "https://example.com/new-2", "status": "downloaded", "size": 10}], 0)],
        ), patch(
            "app.nexus.research_agent.register_or_update_sources",
            side_effect=[[{"source_id": "src-1", "url": "https://example.com/old", "final_url": "https://example.com/old"}], [{"source_id": "src-2", "url": "https://example.com/new-1", "final_url": "https://example.com/new-1"}], [{"source_id": "src-3", "url": "https://example.com/new-2", "final_url": "https://example.com/new-2"}]],
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch("app.nexus.research_agent.save_evidence_items", return_value=0), patch(
            "app.nexus.research_agent.replace_evidence_items_for_job", return_value=0
        ), patch("app.nexus.research_agent._load_source_chunks", return_value=[]), patch(
            "app.nexus.research_agent.build_citation_map", return_value=[]
        ), patch("app.nexus.research_agent._analyze_research_gaps", return_value={"confidence": 0.1, "gaps": ["source_count_low"], "unresolved_items": []}), patch(
            "app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}
        ), patch(
            "app.nexus.research_agent.append_job_event", side_effect=lambda _jid, et, payload: captured.append((et, payload))
        ):
            result = run_research_job(ResearchAgentInput(query="q", recursive_search=True, max_iterations=2), job_id="job-r6")
        self.assertEqual(mocked_search.call_count, 3)
        self.assertEqual(result["answer"]["followup_search_count"], 2)
        self.assertEqual(result["answer"]["recursive_stop_reason"], "max_iterations_reached")
        self.assertEqual(result["answer"]["iterations"][-1]["stop_reason"], "max_iterations_reached")
        max_iter_stops = [p for e, p in captured if e == "recursive_stopped" and p.get("reason") == "max_iterations_reached"]
        self.assertTrue(max_iter_stops)

    def test_recursive_confidence_threshold_stops_before_followup(self) -> None:
        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search", return_value={"items": []}
        ) as mocked_search, patch("app.nexus.research_agent.collect_source_candidates", return_value=[]), patch(
            "app.nexus.research_agent.rank_source_candidates", return_value=[]
        ), patch("app.nexus.research_agent.register_or_update_sources", return_value=[]), patch(
            "app.nexus.research_agent._build_evidence_from_sources", return_value=[]
        ), patch("app.nexus.research_agent.save_evidence_items", return_value=0), patch(
            "app.nexus.research_agent._load_source_chunks", return_value=[]
        ), patch("app.nexus.research_agent.build_citation_map", return_value=[]), patch(
            "app.nexus.research_agent._analyze_research_gaps", return_value={"confidence": 0.95, "sufficient": False, "gaps": [], "unresolved_items": []}
        ), patch("app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}):
            result = run_research_job(ResearchAgentInput(query="q", recursive_search=True, max_iterations=2, confidence_threshold=0.75), job_id="job-r7")
        self.assertEqual(mocked_search.call_count, 1)
        self.assertEqual(result["answer"]["followup_search_count"], 0)

    def test_recursive_stop_when_sufficient_false_runs_until_max_iterations(self) -> None:
        with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
            "app.nexus.research_agent.run_web_search",
            side_effect=[{"items": [{"url": "https://example.com/new-1"}]}, {"items": [{"url": "https://example.com/new-2"}]}, {"items": [{"url": "https://example.com/new-3"}]}],
        ) as mocked_search, patch(
            "app.nexus.research_agent.collect_source_candidates",
            side_effect=[[{"url": "https://example.com/new-1"}], [{"url": "https://example.com/new-2"}], [{"url": "https://example.com/new-3"}]],
        ), patch(
            "app.nexus.research_agent.rank_source_candidates",
            side_effect=[[{"url": "https://example.com/new-1"}], [{"url": "https://example.com/new-2"}], [{"url": "https://example.com/new-3"}]],
        ), patch(
            "app.nexus.research_agent._download_sources_parallel",
            side_effect=[([{"source_id": "src-1", "url": "https://example.com/old", "status": "downloaded", "size": 10}], 0), ([{"source_id": "src-2", "url": "https://example.com/new-1", "status": "downloaded", "size": 10}], 0), ([{"source_id": "src-3", "url": "https://example.com/new-2", "status": "downloaded", "size": 10}], 0)],
        ), patch(
            "app.nexus.research_agent.register_or_update_sources",
            side_effect=[[{"source_id": "src-1", "url": "https://example.com/old", "final_url": "https://example.com/old"}], [{"source_id": "src-2", "url": "https://example.com/new-1", "final_url": "https://example.com/new-1"}], [{"source_id": "src-3", "url": "https://example.com/new-2", "final_url": "https://example.com/new-2"}]],
        ), patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]), patch("app.nexus.research_agent.save_evidence_items", return_value=0), patch(
            "app.nexus.research_agent.replace_evidence_items_for_job", return_value=0
        ), patch("app.nexus.research_agent._load_source_chunks", return_value=[]), patch(
            "app.nexus.research_agent.build_citation_map", return_value=[]
        ), patch("app.nexus.research_agent._analyze_research_gaps", return_value={"confidence": 0.95, "sufficient": True, "gaps": ["source_count_low"], "unresolved_items": []}), patch(
            "app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}
        ):
            result = run_research_job(ResearchAgentInput(query="q", recursive_search=True, max_iterations=2, stop_when_sufficient=False), job_id="job-r8")
        self.assertEqual(mocked_search.call_count, 3)
        self.assertEqual(result["answer"]["followup_search_count"], 2)

    def test_replace_evidence_items_for_job_replaces_existing_rows(self) -> None:
        job_id = f"job-evidence-{uuid.uuid4().hex[:6]}"
        create_job(job_id, title="evidence", status="running", message="running")
        save_evidence_items(
            job_id,
            [EvidenceItem(source_type="web", document_id="", chunk_id="c1", url="https://example.com/1", retrieved_at="2026-01-01T00:00:00+00:00", source_id="s1")],
        )
        replaced = replace_evidence_items_for_job(
            job_id,
            [EvidenceItem(source_type="web", document_id="", chunk_id="c2", url="https://example.com/2", retrieved_at="2026-01-01T00:00:01+00:00", source_id="s2")],
        )
        items = list_evidence_items(job_id)
        self.assertEqual(replaced, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["chunk_id"], "c2")

    def test_replace_evidence_items_for_job_rolls_back_on_insert_error(self) -> None:
        job_id = f"job-evidence-rollback-{uuid.uuid4().hex[:6]}"
        create_job(job_id, title="evidence rollback", status="running", message="running")
        save_evidence_items(
            job_id,
            [EvidenceItem(source_type="web", document_id="", chunk_id="c1", url="https://example.com/1", retrieved_at="2026-01-01T00:00:00+00:00", source_id="s1")],
        )
        with self.assertRaises(ValueError):
            replace_evidence_items_for_job(
                job_id,
                [EvidenceItem(source_type="web", document_id="", chunk_id="c2", url="", retrieved_at="2026-01-01T00:00:01+00:00", source_id="s2")],
            )
        items = list_evidence_items(job_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["chunk_id"], "c1")


if __name__ == "__main__":
    unittest.main()
