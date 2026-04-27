import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.tools.registry import create_default_registry
from app.nexus.router import nexus_router


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
        self.assertTrue(data["non_fatal"])
        self.assertTrue(data["stub"])
        self.assertIn("searxng", data["provider_errors"])

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
        with patch("app.nexus.router.run_web_search", return_value=fake_search):
            r = self.client.post("/nexus/web/search", json={"query": "test"})

        self.assertEqual(r.status_code, 200)
        result = r.json()["result"]
        self.assertTrue(result["non_fatal"])
        self.assertEqual(result["provider_errors"], {"searxng": ["connection refused"]})

    def test_research_bundle_endpoint_returns_zip_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
            tmp.write(b"PK\x03\x04")
            tmp.flush()
            with patch("app.nexus.export.create_research_bundle", return_value=tmp.name):
                r = self.client.get("/nexus/research/jobs/job-test/bundle")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("content-type"), "application/zip")


class AgentRegistryTests(unittest.TestCase):
    def test_registry_contains_nexus_web_search(self) -> None:
        registry = create_default_registry()
        self.assertIn("nexus_web_search", registry.list_tools())


if __name__ == "__main__":
    unittest.main()
