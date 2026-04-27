import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.tools.registry import create_default_registry
from agent.tools.nexus_tools import nexus_web_search
from app.nexus.export import nexus_export_router
from app.nexus.router import nexus_router
from app.nexus.web_scout import run_web_search


class NexusWebIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(nexus_router, prefix="/nexus")
        self.client = TestClient(app)

    def test_web_status_returns_non_fatal_fields_when_searxng_unreachable(self) -> None:
        env = {
            "NEXUS_ENABLE_WEB": "true",
            "NEXUS_WEB_SEARCH_PROVIDER": "searxng",
            "NEXUS_SEARCH_FALLBACK_PROVIDERS": "searxng",
            "NEXUS_SEARXNG_URL": "http://127.0.0.1:65535",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("app.nexus.router._check_searxng_connectivity", return_value=(False, "probe failed")):
                r = self.client.get("/nexus/web/status")

        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("non_fatal", data)
        self.assertIn("stub", data)
        self.assertIn("provider_errors", data)
        self.assertIn("last_provider_errors", data)
        self.assertIn("last_search_at", data)
        self.assertIn("last_non_fatal", data)
        self.assertIn("last_message", data)
        self.assertTrue(data["non_fatal"])
        self.assertTrue(data["stub"])
        self.assertIn("searxng", data["provider_errors"])
        self.assertEqual(data["last_provider_errors"], {})
        self.assertIsNone(data["last_search_at"])

    def test_summary_limits_include_download_related_keys(self) -> None:
        response = self.client.get("/nexus/summary")

        self.assertEqual(response.status_code, 200)
        limits = response.json()["limits"]
        self.assertIn("max_upload_mb", limits)
        self.assertIn("max_upload_bytes", limits)
        self.assertIn("max_download_mb", limits)
        self.assertIn("max_total_download_mb", limits)
        self.assertIn("max_downloads", limits)
        self.assertIn("download_timeout_sec", limits)

    def test_web_search_returns_provider_error_payload(self) -> None:
        fake_search = {
            "provider": "searxng",
            "selected_provider": "searxng",
            "attempted_providers": ["searxng"],
            "fallback_used": False,
            "skipped_providers": {},
            "provider_errors": {"searxng": ["connection refused"]},
            "configured": False,
            "non_fatal": True,
            "message": "stub",
            "items": [
                {
                    "provider": "stub",
                    "query": "test",
                    "rank": 1,
                    "title": "[stub] test",
                    "url": "",
                    "snippet": "stub",
                    "engine": "stub",
                    "is_stub": True,
                }
            ],
            "total_items": 1,
            "generated_queries": ["test"],
            "effective_query_plan": {"queries": ["test"]},
        }
        with patch(
            "app.nexus.router.execute_web_search_service",
            return_value={
                "ok": True,
                "job_id": "job-web-1",
                "queries": ["test"],
                "saved_evidence": 1,
                "search": fake_search,
            },
        ):
            r = self.client.post("/nexus/web/search", json={"query": "test"})

        self.assertEqual(r.status_code, 200)
        result = r.json()["result"]
        self.assertTrue(result["non_fatal"])
        self.assertEqual(result["provider_errors"], {"searxng": ["connection refused"]})

    def test_web_search_response_includes_job_id_and_saved_evidence(self) -> None:
        fake_search = {
            "provider": "searxng",
            "selected_provider": "searxng",
            "attempted_providers": ["searxng"],
            "provider_errors": {},
            "configured": True,
            "non_fatal": False,
            "message": "",
            "items": [
                {
                    "provider": "searxng",
                    "query": "ai chips",
                    "rank": 1,
                    "title": "AI Chips Overview",
                    "url": "https://example.com/ai-chips",
                    "snippet": "Market summary",
                    "engine": "searxng",
                }
            ],
            "total_items": 1,
            "generated_queries": ["ai chips"],
            "effective_query_plan": {"queries": ["ai chips"]},
        }
        with patch(
            "app.nexus.router.execute_web_search_service",
            return_value={
                "ok": True,
                "job_id": "job-web-shape-1",
                "queries": ["ai chips"],
                "saved_evidence": 1,
                "search": fake_search,
            },
        ):
            response = self.client.post("/nexus/web/search", json={"query": "ai chips"})

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["job_id"], "job-web-shape-1")
        self.assertEqual(result["saved_evidence"], 1)
        self.assertIn("job_id", result)
        self.assertIn("saved_evidence", result)

    def test_web_search_provider_non_fatal_stub_still_builds_and_saves_evidence(self) -> None:
        provider_failure_stub = {
            "provider": "searxng",
            "selected_provider": "searxng",
            "attempted_providers": ["searxng"],
            "provider_errors": {"searxng": ["connection refused"]},
            "non_fatal": True,
            "message": "stub",
            "items": [
                {
                    "provider": "stub",
                    "query": "fallback",
                    "rank": 1,
                    "title": "[stub] fallback",
                    "url": "",
                    "snippet": "stub",
                    "engine": "stub",
                    "is_stub": True,
                }
            ],
            "total_items": 1,
        }
        fake_evidence_items = [object(), object()]

        with patch("app.nexus.web_service.plan_web_queries", return_value=["fallback"]) as mocked_plan, patch(
            "app.nexus.web_service._run_web_search", return_value=provider_failure_stub
        ) as mocked_search, patch("app.nexus.web_service.create_job") as mocked_create_job, patch(
            "app.nexus.web_service.build_web_evidence", return_value=fake_evidence_items
        ) as mocked_build, patch("app.nexus.web_service.save_evidence_items", return_value=2) as mocked_save, patch(
            "app.nexus.web_service.update_job"
        ) as mocked_update_job, patch(
            "app.nexus.web_service.uuid.uuid4", return_value="job-web-stub-id"
        ):
            response = self.client.post("/nexus/web/search", json={"query": "fallback", "max_queries": 1})

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertTrue(result["non_fatal"])
        self.assertEqual(result["saved_evidence"], 2)
        mocked_plan.assert_called_once()
        mocked_search.assert_called_once()
        mocked_create_job.assert_called_once_with(
            "job-web-stub-id",
            title="nexus_web_search:fallback",
            message="tool_invocation",
        )
        mocked_build.assert_called_once_with(provider_failure_stub, note="nexus_web_search")
        mocked_save.assert_called_once_with("job-web-stub-id", fake_evidence_items)
        mocked_update_job.assert_called_once_with(
            "job-web-stub-id",
            status="completed",
            progress=1.0,
            message="nexus_web_search completed",
            document_count=2,
        )

    def test_web_search_updates_job_failed_with_failure_message_on_exception(self) -> None:
        provider_failure_stub = {
            "provider": "searxng",
            "selected_provider": "searxng",
            "attempted_providers": ["searxng"],
            "provider_errors": {},
            "non_fatal": False,
            "message": "",
            "items": [],
            "total_items": 0,
        }

        with patch("app.nexus.web_service.plan_web_queries", return_value=["failing query"]) as mocked_plan, patch(
            "app.nexus.web_service._run_web_search", return_value=provider_failure_stub
        ) as mocked_search, patch("app.nexus.web_service.create_job") as mocked_create_job, patch(
            "app.nexus.web_service.build_web_evidence", side_effect=RuntimeError("boom")
        ) as mocked_build, patch(
            "app.nexus.web_service.update_job"
        ) as mocked_update_job, patch(
            "app.nexus.web_service.uuid.uuid4", return_value="job-web-failed-id"
        ):
            with self.assertRaises(RuntimeError):
                self.client.post("/nexus/web/search", json={"query": "failing query", "max_queries": 1})

        mocked_plan.assert_called_once()
        mocked_search.assert_called_once()
        mocked_create_job.assert_called_once_with(
            "job-web-failed-id",
            title="nexus_web_search:failing query",
            message="tool_invocation",
        )
        mocked_build.assert_called_once_with(provider_failure_stub, note="nexus_web_search")
        mocked_update_job.assert_called_once_with(
            "job-web-failed-id",
            status="failed",
            message="nexus_web_search failed",
            error="boom",
        )

    def test_research_bundle_endpoint_returns_zip_file(self) -> None:
        export_app = FastAPI()
        export_app.include_router(nexus_export_router, prefix="/nexus")
        export_client = TestClient(export_app)
        with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
            tmp.write(b"PK\x03\x04")
            tmp.flush()
            with patch("app.nexus.export.create_research_bundle", return_value=tmp.name):
                r = export_client.get("/nexus/research/jobs/job-test/bundle.zip")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("content-type"), "application/zip")
        content_disposition = str(r.headers.get("content-disposition") or "")
        self.assertIn("attachment;", content_disposition)
        self.assertIn('.zip"', content_disposition)
        self.assertTrue(r.content.startswith(b"PK\x03\x04"))

    def test_web_research_returns_job_id_immediately(self) -> None:
        fake_async_result = {
            "job_id": "research_job_123",
            "job": {
                "job_id": "research_job_123",
                "status": "queued",
                "message": "research queued",
            },
        }
        with patch("app.nexus.router.run_research_async", return_value=fake_async_result) as mocked:
            r = self.client.post(
                "/nexus/web/research",
                json={"query": "test immediate", "mode": "standard"},
            )

        self.assertEqual(r.status_code, 200)
        payload = r.json()
        self.assertEqual(payload["operation"], "web.research")
        self.assertEqual(payload["result"]["job_id"], "research_job_123")
        self.assertEqual(payload["result"]["job"]["status"], "queued")
        self.assertIn("summary", payload["result"])
        mocked.assert_called_once()


class AgentRegistryTests(unittest.TestCase):
    def test_registry_contains_nexus_web_search_only_for_web_tool_name(self) -> None:
        registry = create_default_registry()
        tools = registry.list_tools()

        self.assertIn("nexus_web_search", tools)
        self.assertNotIn("run_web_search", tools)
        self.assertNotIn("web_search", tools)


class NexusToolsWebSearchTests(unittest.TestCase):
    def test_nexus_web_search_response_has_core_keys(self) -> None:
        fake_search_output = {
            "provider": "searxng",
            "non_fatal": False,
            "items": [
                {
                    "provider": "searxng",
                    "query": "ai chips",
                    "rank": 1,
                    "title": "AI Chips Overview",
                    "url": "https://example.com/ai-chips",
                    "snippet": "Market summary",
                }
            ],
            "provider_errors": {},
        }
        with patch(
            "agent.tools.nexus_tools.execute_web_search_service",
            return_value={
                "ok": True,
                "job_id": "job-fixed-id",
                "queries": ["ai chips"],
                "saved_evidence": 1,
                "search": fake_search_output,
            },
        ):
            result = nexus_web_search(topic="ai chips", mode="quick", depth="quick", max_queries=1, max_results_per_query=3)

        self.assertEqual(result["job_id"], "job-fixed-id")
        self.assertEqual(result["saved_evidence"], 1)
        self.assertEqual(result["queries"], ["ai chips"])
        self.assertIn("search", result)
        self.assertFalse(result["search"]["non_fatal"])

    def test_nexus_web_search_matches_api_common_keys(self) -> None:
        provider_failure_stub = {
            "provider": "searxng",
            "selected_provider": "searxng",
            "attempted_providers": ["searxng"],
            "provider_errors": {"searxng": ["connection refused"]},
            "non_fatal": True,
            "message": "stub",
            "items": [
                {
                    "provider": "stub",
                    "query": "fallback",
                    "rank": 1,
                    "title": "[stub] fallback",
                    "url": "",
                    "snippet": "stub",
                    "engine": "stub",
                    "is_stub": True,
                }
            ],
            "total_items": 1,
        }
        shared_service_result = {
            "ok": True,
            "job_id": "job-shape-match-1",
            "queries": ["fallback"],
            "saved_evidence": 2,
            "search": provider_failure_stub,
        }

        with patch("agent.tools.nexus_tools.execute_web_search_service", return_value=shared_service_result):
            tool_result = nexus_web_search(topic="fallback", max_queries=1, max_results_per_query=2)

        app = FastAPI()
        app.include_router(nexus_router, prefix="/nexus")
        api_client = TestClient(app)
        with patch("app.nexus.router.execute_web_search_service", return_value=shared_service_result):
            api_response = api_client.post("/nexus/web/search", json={"query": "fallback", "max_queries": 1})

        self.assertEqual(api_response.status_code, 200)
        api_result = api_response.json()["result"]

        self.assertEqual(tool_result["job_id"], api_result["job_id"])
        self.assertEqual(tool_result["queries"], api_result["queries"])
        self.assertEqual(tool_result["saved_evidence"], api_result["saved_evidence"])
        self.assertEqual(tool_result["search"]["non_fatal"], api_result["search"]["non_fatal"])
        self.assertEqual(tool_result["search"]["provider_errors"], api_result["search"]["provider_errors"])
        self.assertEqual(tool_result["search"]["items"], api_result["search"]["items"])


class WebScoutRunSearchTests(unittest.TestCase):
    def test_run_web_search_returns_non_fatal_with_provider_errors_on_provider_failure(self) -> None:
        env = {
            "NEXUS_ENABLE_WEB": "true",
            "NEXUS_WEB_SEARCH_PROVIDER": "searxng",
            "NEXUS_SEARCH_FALLBACK_PROVIDERS": "searxng",
            "NEXUS_SEARXNG_URL": "http://127.0.0.1:65535",
        }
        with patch.dict(os.environ, env, clear=False):
            result = run_web_search(["integration test query"], mode="quick", depth="quick", max_results_per_query=2)

        self.assertTrue(result.get("non_fatal"))
        self.assertIn("provider_errors", result)
        self.assertIn("searxng", result.get("provider_errors", {}))
        self.assertGreaterEqual(len(result.get("provider_errors", {}).get("searxng", [])), 1)


if __name__ == "__main__":
    unittest.main()
