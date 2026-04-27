import os
import json
import io
import tempfile
import unittest
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import uuid
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.nexus.db import get_conn, insert_chunk, insert_document, update_document_artifact_paths
from app.nexus.downloader import save_download_artifacts
from app.nexus.export import create_research_bundle
from app.nexus.jobs import append_job_event, create_job, update_job
from app.nexus.research_api import ResearchRunRequest, run_research
from app.nexus.router import nexus_router


class NexusResearchApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(nexus_router, prefix="/nexus")
        self.client = TestClient(app)
        self._tmpdir = tempfile.TemporaryDirectory()
        self._artifact_root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _mock_seed_async_research_job(self, payload: ResearchRunRequest) -> dict:
        query = payload.query.strip()
        job_id = f"research_api_poll_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        create_job(job_id, title=query, status="queued", message="queued")
        append_job_event(job_id, "job.status", {"status": "queued", "message": "queued", "updated_at": now})
        update_job(job_id, status="running", message="running")
        append_job_event(job_id, "job.status", {"status": "running", "message": "running", "updated_at": now})
        update_job(job_id, status="completed", progress=1.0, message="completed")
        append_job_event(job_id, "job.status", {"status": "completed", "message": "completed", "updated_at": now})

        status_map = {
            "downloaded": ["downloaded"],
            "degraded": ["degraded"],
            "skipped": ["skipped"],
        }
        expected_statuses = status_map.get(query, ["downloaded", "degraded", "skipped"])
        source_ids: list[str] = []
        with get_conn() as conn:
            for idx, source_status in enumerate(expected_statuses, start=1):
                source_id = f"src_{source_status}_{uuid.uuid4().hex[:8]}"
                source_ids.append(source_id)
                body = f"<html><body>{query} {source_status}</body></html>".encode("utf-8")
                download_result = {
                    "url": f"https://example.com/{query}/{idx}",
                    "final_url": f"https://example.com/{query}/{idx}",
                    "status_code": 200,
                    "content_type": "text/html",
                    "filename": "mock.html",
                    "extension": ".html",
                    "bytes": body,
                    "size": len(body),
                }
                artifacts = save_download_artifacts(job_id, source_id, download_result)
                document_id = f"doc_{source_id}"
                insert_document(
                    document_id=document_id,
                    project=payload.project,
                    filename=f"{source_status}-source.html",
                    size=len(body),
                    content_type="text/html",
                    path=artifacts["original"],
                    sha256=sha256(body).hexdigest(),
                    created_at=now,
                )
                update_document_artifact_paths(
                    document_id=document_id,
                    extracted_text_path=artifacts["extracted_txt"],
                    markdown_path=artifacts["extracted_md"],
                    updated_at=now,
                )
                conn.execute(
                    """
                    INSERT INTO nexus_sources(
                        source_id, job_id, project, source_type, url, final_url, title, publisher, domain,
                        language, content_type, local_original_path, local_text_path, local_markdown_path,
                        local_screenshot_path, linked_document_id, status, source_score, source_score_breakdown,
                        error, retrieved_at, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        job_id,
                        payload.project,
                        "web",
                        download_result["url"],
                        download_result["final_url"],
                        f"{source_status} source",
                        "",
                        "example.com",
                        "ja",
                        "text/html",
                        artifacts["original"],
                        artifacts["extracted_txt"],
                        artifacts["extracted_md"],
                        "",
                        document_id,
                        source_status,
                        0.7,
                        "{}",
                        "" if source_status != "degraded" else "partial extraction",
                        now,
                        now,
                        now,
                    ),
                )
            conn.execute(
                """
                INSERT INTO nexus_research_answers(
                    answer_id, job_id, project, question, answer_markdown,
                    evidence_json, answer_json, source_ids_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    job_id,
                    payload.project,
                    query,
                    f"# Answer\n{query} result\n",
                    "[]",
                    json.dumps(
                        {
                            "question": query,
                            "answer_markdown": f"# Answer\n{query} result\n",
                            "references": [],
                            "citation_verification": {"ok": True, "warnings": []},
                            "generation": {"mode": payload.mode},
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(source_ids, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
        return {"job_id": job_id, "job": {"job_id": job_id, "status": "completed", "message": "completed"}}

    def test_get_research_job_answer_prefers_persisted_answer_json(self) -> None:
        job_id = f"job_answer_json_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        create_job(job_id, title="test", status="completed")
        persisted_payload = {
            "question": "Q",
            "answer": "A [S1]",
            "references": [{"citation_label": "[S1]", "title": "T", "source_id": "src-1"}],
            "citation_verification": {
                "ok": False,
                "warnings": [{"sentence_index": 1, "reason": "low_semantic_overlap"}],
            },
            "generation": {"mode": "llm"},
        }
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO nexus_research_answers(
                    answer_id, job_id, project, question, answer_markdown,
                    evidence_json, answer_json, source_ids_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    job_id,
                    "default",
                    "Q",
                    "# Answer\nA [S1]\n",
                    "[]",
                    json.dumps(persisted_payload, ensure_ascii=False),
                    '["src-1"]',
                    now,
                ),
            )
            conn.commit()

        response = self.client.get(f"/nexus/research/jobs/{job_id}/answer")
        self.assertEqual(response.status_code, 200)
        answer = response.json().get("answer", {})
        self.assertEqual(answer.get("generation", {}).get("mode"), "llm")
        self.assertEqual(answer.get("citation_verification", {}).get("warnings", [{}])[0].get("reason"), "low_semantic_overlap")
        self.assertEqual(answer.get("references", [{}])[0].get("citation_label"), "[S1]")

    def test_get_research_job_answer_reconstructs_legacy_rows_without_answer_json(self) -> None:
        job_id = f"job_answer_legacy_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        create_job(job_id, title="test", status="completed")
        source_id = f"src_{uuid.uuid4().hex[:6]}"
        document_id = f"doc_{uuid.uuid4().hex[:8]}"
        insert_document(
            document_id=document_id,
            project="default",
            filename="legacy.html",
            size=1,
            content_type="text/html",
            path="",
            sha256="legacy-sha",
            created_at=now,
        )
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO nexus_sources(
                    source_id, job_id, project, source_type, url, final_url, title, publisher, domain,
                    language, content_type, local_original_path, local_text_path, local_markdown_path,
                    local_screenshot_path, linked_document_id, status, source_score, source_score_breakdown,
                    error, retrieved_at, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    job_id,
                    "default",
                    "web",
                    "https://example.com",
                    "https://example.com",
                    "Legacy source",
                    "",
                    "example.com",
                    "ja",
                    "text/html",
                    "",
                    "",
                    "",
                    "",
                    document_id,
                    "ingested",
                    0.9,
                    "{}",
                    "",
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO nexus_research_answers(
                    answer_id, job_id, project, question, answer_markdown,
                    evidence_json, answer_json, source_ids_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    job_id,
                    "default",
                    "Q",
                    "# Answer\nA [S1]\n",
                    json.dumps([{"citation_label": "[S1]", "source_id": source_id}], ensure_ascii=False),
                    "{}",
                    json.dumps([source_id], ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()

        response = self.client.get(f"/nexus/research/jobs/{job_id}/answer")
        self.assertEqual(response.status_code, 200)
        answer = response.json().get("answer", {})
        self.assertEqual(answer.get("references", [{}])[0].get("source_id"), source_id)
        self.assertEqual(answer.get("references", [{}])[0].get("title"), "Legacy source")

    def _mock_register_or_update_sources(self, *, job_id: str, project: str, sources: list[dict]) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        saved: list[dict] = []

        for idx, source in enumerate(sources):
            source_id = f"source_{idx + 1}_{uuid.uuid4().hex[:8]}"
            document_id = f"doc_{source_id}_{uuid.uuid4().hex[:8]}"
            url = str(source.get("url") or "")
            title = str(source.get("title") or f"Source {idx + 1}")
            is_pdf = url.endswith(".pdf")
            content_type = "application/pdf" if is_pdf else "text/html"
            extension = ".pdf" if is_pdf else ".html"
            body = (
                b"%PDF-1.4 mock pdf bytes for integration keyword_pdf"
                if is_pdf
                else b"<html><body>integration keyword_html and more content</body></html>"
            )
            download_result = {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": content_type,
                "filename": "mock" + extension,
                "extension": extension,
                "bytes": body,
                "size": len(body),
            }
            artifacts = save_download_artifacts(job_id, source_id, download_result)
            extracted_text = Path(artifacts["extracted_txt"]).read_text(encoding="utf-8", errors="replace")

            insert_document(
                document_id=document_id,
                project=project,
                filename=title,
                size=len(body),
                content_type=content_type,
                path=artifacts["original"],
                sha256=sha256(body).hexdigest(),
                created_at=now,
            )
            update_document_artifact_paths(
                document_id=document_id,
                extracted_text_path=artifacts["extracted_txt"],
                markdown_path=artifacts["extracted_md"],
                updated_at=now,
            )
            chunk_id = f"{document_id}:0"
            insert_chunk(
                chunk_id=chunk_id,
                document_id=document_id,
                chunk_index=0,
                title=title,
                section_path="/",
                content=extracted_text,
                page_start=1,
                page_end=1,
                citation_label=f"{title}#1",
                created_at=now,
            )

            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO nexus_sources(
                        source_id, job_id, project, source_type, url, final_url, title,
                        publisher, language, domain, content_type,
                        local_original_path, local_text_path, local_markdown_path, local_screenshot_path,
                        linked_document_id, status, error, retrieved_at, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        job_id,
                        project,
                        "web",
                        url,
                        url,
                        title,
                        "",
                        "",
                        "example.com",
                        content_type,
                        artifacts["original"],
                        artifacts["extracted_txt"],
                        artifacts["extracted_md"],
                        "",
                        document_id,
                        "ingested",
                        "",
                        now,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO nexus_source_chunks(id, source_id, document_id, chunk_id, page_start, page_end,
                                                    section_path, citation_label, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), source_id, document_id, chunk_id, 1, 1, "/", f"{title}#1", now),
                )
                conn.commit()

            saved.append(
                {
                    **source,
                    "source_id": source_id,
                    "final_url": url,
                    "content_type": content_type,
                    "status": "ingested",
                    "document_id": document_id,
                    "linked_document_id": document_id,
                    "local_original_path": artifacts["original"],
                    "local_text_path": artifacts["extracted_txt"],
                    "local_markdown_path": artifacts["extracted_md"],
                }
            )

        return saved

    def test_research_run_persists_sources_files_answer_and_bundle(self) -> None:
        fake_search = {
            "provider": "mock",
            "selected_provider": "mock",
            "attempted_providers": ["mock"],
            "fallback_used": False,
            "provider_errors": {},
            "configured": True,
            "non_fatal": False,
            "message": "ok",
            "items": [
                {
                    "provider": "mock",
                    "query": "integration test",
                    "rank": 1,
                    "title": "HTML source",
                    "url": "https://example.com/research.html",
                    "snippet": "html snippet",
                    "engine": "mock",
                },
                {
                    "provider": "mock",
                    "query": "integration test",
                    "rank": 2,
                    "title": "PDF source",
                    "url": "https://example.com/research.pdf",
                    "snippet": "pdf snippet",
                    "engine": "mock",
                },
            ],
            "total_items": 2,
            "generated_queries": ["integration test"],
            "effective_query_plan": {"queries": ["integration test"]},
        }

        def _mock_safe_download(url: str, **_: object) -> dict:
            is_pdf = url.endswith(".pdf")
            body = b"%PDF-1.4 mocked pdf bytes" if is_pdf else b"<html><body>integration keyword_html</body></html>"
            return {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "application/pdf" if is_pdf else "text/html",
                "filename": "mock.pdf" if is_pdf else "mock.html",
                "extension": ".pdf" if is_pdf else ".html",
                "bytes": body,
                "size": len(body),
            }

        with patch("app.nexus.research_agent._record_state", return_value=None), patch(
            "app.nexus.research_agent.plan_web_queries", return_value=["integration test"]
        ), patch("app.nexus.research_agent.run_web_search", return_value=fake_search), patch(
            "app.nexus.research_agent.register_or_update_sources", side_effect=self._mock_register_or_update_sources
        ), patch("app.nexus.research_agent.safe_download", side_effect=_mock_safe_download), patch(
            "app.nexus.router.run_research_async", side_effect=lambda payload: run_research(payload)
        ):
            run_response = self.client.post(
                "/nexus/research/run",
                json={"query": "integration test", "project": "default"},
            )

        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()

        job_id = payload.get("job_id")
        self.assertTrue(job_id)

        with get_conn() as conn:
            rows = conn.execute("SELECT url FROM nexus_sources WHERE job_id = ? ORDER BY url", (job_id,)).fetchall()
        saved_urls = [str(row["url"]) for row in rows]
        self.assertEqual(saved_urls, ["https://example.com/research.html", "https://example.com/research.pdf"])

        sources_response = self.client.get(f"/nexus/research/jobs/{job_id}/sources")
        self.assertEqual(sources_response.status_code, 200)
        sources = sources_response.json()["sources"]
        self.assertEqual(len(sources), 2)

        html_source = next(source for source in sources if source["url"].endswith(".html"))
        pdf_source = next(source for source in sources if source["url"].endswith(".pdf"))

        html_text_path = Path(html_source["local_text_path"])
        self.assertTrue(html_text_path.exists())
        self.assertEqual(html_text_path.name, "text.txt")

        pdf_original_path = Path(pdf_source["local_original_path"])
        self.assertTrue(pdf_original_path.exists())
        self.assertEqual(pdf_original_path.name, "original.pdf")

        search_response = self.client.post("/nexus/search", json={"query": "keyword_html", "limit": 5})
        self.assertEqual(search_response.status_code, 200)
        self.assertGreaterEqual(len(search_response.json()["results"]), 1)

        answer = payload.get("answer", {})
        self.assertIn("references", answer)
        self.assertGreaterEqual(len(answer["references"]), 1)
        self.assertTrue(all(str(ref.get("citation_label", "")).startswith("[S") for ref in answer["references"]))
        self.assertTrue(all(str(item.get("citation_label", "")).startswith("[S") for item in answer["evidence_json"]))

        job_answer_response = self.client.get(f"/nexus/research/jobs/{job_id}/answer")
        self.assertEqual(job_answer_response.status_code, 200)
        job_answer = job_answer_response.json().get("answer", {})
        self.assertIn("references", job_answer)
        self.assertGreaterEqual(len(job_answer["references"]), 1)
        required_reference_keys = {
            "citation_label",
            "title",
            "source_type",
            "source_score",
            "status",
            "url",
            "error",
            "source_id",
        }
        self.assertTrue(required_reference_keys.issubset(set(job_answer["references"][0].keys())))

        text_response = self.client.get(f"/nexus/sources/{html_source['source_id']}/text")
        self.assertEqual(text_response.status_code, 200)
        self.assertIn("keyword_html", text_response.text)

        evidence_response = self.client.get(f"/nexus/research/jobs/{job_id}/evidence")
        self.assertEqual(evidence_response.status_code, 200)
        evidence_items = evidence_response.json().get("evidence", [])
        self.assertGreaterEqual(len(evidence_items), 1)
        self.assertTrue(all("source_id" in item for item in evidence_items))
        self.assertTrue(all(isinstance(item.get("source_id"), str) for item in evidence_items))

        bundle_response = self.client.get(f"/nexus/research/jobs/{job_id}/bundle")
        self.assertEqual(bundle_response.status_code, 200)
        bundle = bundle_response.json()
        self.assertEqual(bundle.get("job_id"), job_id)
        self.assertIn("answer", bundle)
        self.assertIn("sources", bundle)
        self.assertIn("evidence", bundle)

        bundle_zip_path = create_research_bundle(job_id)
        with zipfile.ZipFile(bundle_zip_path) as zf:
            names = set(zf.namelist())
        required_root_files = {
            "answer.md",
            "answer.json",
            "evidence.json",
            "sources.json",
            "source_chunks.json",
            "events.json",
            "queries.json",
            "job.json",
        }
        self.assertTrue(required_root_files.issubset(names))
        for source in sources:
            source_id = source["source_id"]
            root = f"downloads/{source_id}"
            self.assertIn(f"{root}/metadata.json", names)
            self.assertIn(f"{root}/text.txt", names)
            self.assertIn(f"{root}/document.md", names)
            original_path = Path(str(source.get("local_original_path") or ""))
            suffix = original_path.suffix or ".bin"
            self.assertIn(f"{root}/original{suffix}", names)

    def test_web_search_returns_non_fatal_when_brave_and_searxng_are_unset(self) -> None:
        env = {
            "NEXUS_ENABLE_WEB": "true",
            "NEXUS_WEB_SEARCH_PROVIDER": "brave",
            "NEXUS_SEARCH_FALLBACK_PROVIDERS": "searxng",
            "BRAVE_SEARCH_API_KEY": "",
            "NEXUS_SEARXNG_URL": "",
        }
        with patch.dict(os.environ, env, clear=False):
            response = self.client.post("/nexus/web/search", json={"query": "provider fallback test"})

        self.assertEqual(response.status_code, 200)
        result = response.json().get("result", {})
        self.assertTrue(result.get("non_fatal"))
        self.assertIsInstance(result.get("provider_errors"), dict)

    def test_web_research_returns_immediate_job_payload(self) -> None:
        async_payload = {
            "job_id": "research_abc123",
            "job": {"job_id": "research_abc123", "status": "queued", "message": "research queued"},
        }
        with patch("app.nexus.router.run_research_async", return_value=async_payload) as mocked:
            response = self.client.post(
                "/nexus/web/research",
                json={
                    "query": "ai chips",
                    "mode": "deep",
                    "depth": "high",
                    "max_queries": 3,
                    "max_results_per_query": 5,
                    "scope": ["news"],
                    "language": "ja",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["result"]["job_id"], "research_abc123")
        self.assertEqual(payload["result"]["job"]["status"], "queued")
        self.assertIn("summary", payload["result"])

        mocked.assert_called_once()
        delegated = mocked.call_args.args[0]
        self.assertIsInstance(delegated, ResearchRunRequest)
        self.assertEqual(delegated.query, "ai chips")
        self.assertEqual(delegated.mode, "deep")
        self.assertEqual(delegated.depth, "high")
        self.assertEqual(delegated.max_queries, 3)
        self.assertEqual(delegated.max_results_per_query, 5)
        self.assertEqual(delegated.scope, ["news"])
        self.assertEqual(delegated.language, "ja")

    def test_web_collect_manual_pdf_url_persists_download_artifacts(self) -> None:
        manual_url = "https://example.com/manual.pdf"

        def _mock_safe_download(url: str, **_: object) -> dict:
            self.assertEqual(url, manual_url)
            body = b"%PDF-1.4 mock manual pdf bytes"
            return {
                "url": url,
                "final_url": f"{url}?download=1",
                "status_code": 200,
                "content_type": "application/pdf",
                "filename": "manual.pdf",
                "extension": ".pdf",
                "bytes": body,
                "size": len(body),
            }

        def _capture_registered_sources(*, job_id: str, project: str, sources: list[dict]) -> list[dict]:
            self.assertEqual(job_id, "collect_manual_pdf")
            self.assertEqual(project, "default")
            self.assertEqual(len(sources), 1)
            source = sources[0]
            self.assertTrue(Path(source["local_original_path"]).exists())
            self.assertTrue(Path(source["local_text_path"]).exists())
            self.assertTrue(Path(source["local_markdown_path"]).exists())
            return sources

        with patch("app.nexus.research_api.safe_download", side_effect=_mock_safe_download), patch(
            "app.nexus.research_api.register_or_update_sources", side_effect=_capture_registered_sources
        ):
            response = self.client.post(
                "/nexus/web/collect",
                json={"job_id": "collect_manual_pdf", "project": "default", "manual_urls": [manual_url]},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("collected_count"), 1)
        sources = payload.get("sources", [])
        self.assertEqual(len(sources), 1)

        source = sources[0]
        self.assertEqual(source["url"], manual_url)
        self.assertEqual(source["content_type"], "application/pdf")
        self.assertEqual(source["final_url"], f"{manual_url}?download=1")

        original_path = Path(source["local_original_path"])
        text_path = Path(source["local_text_path"])
        markdown_path = Path(source["local_markdown_path"])

        self.assertTrue(original_path.exists())
        self.assertEqual(original_path.name, "original.pdf")
        self.assertTrue(text_path.exists())
        self.assertEqual(text_path.name, "text.txt")
        self.assertTrue(markdown_path.exists())
        self.assertEqual(markdown_path.name, "document.md")

    def test_web_collect_marks_skipped_size_limit_when_max_download_mb_is_1(self) -> None:
        manual_url = "https://example.com/too-large.pdf"

        def _mock_safe_download(url: str, **kwargs: object) -> dict:
            self.assertEqual(url, manual_url)
            self.assertEqual(kwargs.get("max_bytes"), 1 * 1024 * 1024)
            raise ValueError("content too large: 2097152 bytes")

        with patch("app.nexus.research_api.safe_download", side_effect=_mock_safe_download), patch(
            "app.nexus.research_api.register_or_update_sources", side_effect=lambda **kwargs: kwargs["sources"]
        ):
            response = self.client.post(
                "/nexus/web/collect",
                json={"job_id": "collect_size_limit_1mb", "project": "default", "manual_urls": [manual_url], "max_download_mb": 1},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("collected_count"), 1)
        sources = payload.get("sources", [])
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source["url"], manual_url)
        self.assertEqual(source["status"], "skipped_size_limit")
        self.assertIn("content too large", source["error"])

    def test_research_run_polling_sources_answer_bundle_contract(self) -> None:
        scenarios = [
            ("downloaded", {"downloaded"}),
            ("degraded", {"degraded"}),
            ("skipped", {"skipped"}),
        ]
        required_root_files = {
            "answer.md",
            "answer.json",
            "evidence.json",
            "sources.json",
            "source_chunks.json",
            "queries.json",
            "job.json",
            "events.json",
        }

        with patch("app.nexus.router.run_research_async", side_effect=self._mock_seed_async_research_job):
            for query, expected_statuses in scenarios:
                run_response = self.client.post(
                    "/nexus/research/run",
                    json={"query": query, "project": "default", "mode": "standard", "depth": "shallow", "scope": ["web"]},
                )
                self.assertEqual(run_response.status_code, 200)
                job_id = run_response.json().get("job_id")
                self.assertTrue(job_id)

                after = -1
                observed_states: list[str] = []
                for _ in range(3):
                    events_response = self.client.get(f"/nexus/research/jobs/{job_id}/events?after={after}")
                    self.assertEqual(events_response.status_code, 200)
                    events = events_response.json().get("events", [])
                    for event in events:
                        if event.get("status"):
                            observed_states.append(str(event["status"]))
                        after = max(after, int(event.get("seq", -1)))
                self.assertTrue("queued" in observed_states)
                self.assertTrue("running" in observed_states)
                self.assertTrue(any(state in {"completed", "degraded", "failed"} for state in observed_states))

                sources_response = self.client.get(f"/nexus/research/jobs/{job_id}/sources")
                self.assertEqual(sources_response.status_code, 200)
                sources = sources_response.json().get("sources", [])
                self.assertGreaterEqual(len(sources), 1)
                statuses = {str(source.get("status") or "") for source in sources}
                self.assertTrue(expected_statuses.issubset(statuses))

                answer_response = self.client.get(f"/nexus/research/jobs/{job_id}/answer")
                self.assertEqual(answer_response.status_code, 200)
                answer = answer_response.json().get("answer", {})
                self.assertIn("answer_markdown", answer)
                self.assertIn("generation", answer)
                self.assertIn("citation_verification", answer)
                self.assertIn("warnings", answer.get("citation_verification", {}))

                bundle_zip_response = self.client.get(f"/nexus/research/jobs/{job_id}/bundle.zip")
                self.assertEqual(bundle_zip_response.status_code, 200)
                with zipfile.ZipFile(io.BytesIO(bundle_zip_response.content)) as zf:
                    names = set(zf.namelist())
                self.assertTrue(required_root_files.issubset(names))
                for source in sources:
                    source_id = source["source_id"]
                    root = f"downloads/{source_id}"
                    self.assertIn(f"{root}/original.html", names)
                    self.assertIn(f"{root}/text.txt", names)
                    self.assertIn(f"{root}/document.md", names)
                    self.assertIn(f"{root}/metadata.json", names)

    def test_web_collect_accepts_pseudo_pdf_between_20mb_and_30mb(self) -> None:
        manual_url = "https://example.com/large-allowed.pdf"
        pseudo_pdf_size = 25 * 1024 * 1024
        original_path = self._artifact_root / "allowed-original.pdf"
        text_path = self._artifact_root / "allowed-text.txt"
        markdown_path = self._artifact_root / "allowed-document.md"

        def _mock_safe_download(url: str, **kwargs: object) -> dict:
            self.assertEqual(url, manual_url)
            self.assertEqual(kwargs.get("max_bytes"), 30 * 1024 * 1024)
            return {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "application/pdf",
                "filename": "large-allowed.pdf",
                "extension": ".pdf",
                "bytes": b"%PDF-1.4 pseudo",
                "size": pseudo_pdf_size,
            }

        def _mock_save_download_artifacts(**_: object) -> dict:
            original_path.write_bytes(b"%PDF-1.4 pseudo")
            text_path.write_text("pseudo pdf text", encoding="utf-8")
            markdown_path.write_text("# pseudo pdf", encoding="utf-8")
            return {
                "original": str(original_path),
                "extracted_txt": str(text_path),
                "extracted_md": str(markdown_path),
                "status": "downloaded",
                "error": "",
            }

        with patch("app.nexus.research_api.safe_download", side_effect=_mock_safe_download), patch(
            "app.nexus.research_api.save_download_artifacts", side_effect=_mock_save_download_artifacts
        ), patch("app.nexus.research_api.register_or_update_sources", side_effect=lambda **kwargs: kwargs["sources"]):
            response = self.client.post(
                "/nexus/web/collect",
                json={"job_id": "collect_size_limit_30mb", "project": "default", "manual_urls": [manual_url], "max_download_mb": 30},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("collected_count"), 1)
        sources = payload.get("sources", [])
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source["url"], manual_url)
        self.assertEqual(source["status"], "downloaded")
        self.assertEqual(source["content_type"], "application/pdf")
        self.assertEqual(source["local_original_path"], str(original_path))
        self.assertEqual(source["local_text_path"], str(text_path))
        self.assertEqual(source["local_markdown_path"], str(markdown_path))


if __name__ == "__main__":
    unittest.main()
