from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.server import create_app

API_NEXUS_PATH = Path("app/api/nexus.py")
SERVICE_PATH = Path("app/services/nexus_execution.py")
ROUTER_PATH = Path("app/nexus/router.py")

WRITE_ROUTES = [
    ("/nexus/search", "POST", "nexus_search_api", {"query": "alpha", "limit": 2}),
    ("/nexus/web/search", "POST", "nexus_web_search_api", {"query": "alpha"}),
    ("/nexus/web/research", "POST", "nexus_web_research_api", {"query": "alpha"}),
    ("/nexus/research/run", "POST", "nexus_research_run_api", {"query": "alpha"}),
    ("/nexus/sources/search", "POST", "nexus_sources_search_api", {"query": "alpha", "job_id": "job-1"}),
    (
        "/nexus/evidence/add-from-chunks",
        "POST",
        "nexus_evidence_add_from_chunks_api",
        {"job_id": "job-1", "chunk_ids": ["chunk-1"]},
    ),
    (
        "/nexus/research/jobs/job-1/followup",
        "POST",
        "nexus_research_followup_api",
        {"question": "what changed?"},
    ),
    ("/nexus/web/collect", "POST", "nexus_web_collect_api", {"job_id": "job-1"}),
    ("/nexus/ask", "POST", "nexus_ask_api", {"query": "alpha"}),
    ("/nexus/report/build", "POST", "nexus_report_build_api", {"job_id": "job-1"}),
]


def _route(path: str, method: str, app=main.app):
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(routes) == 1
    return routes[0]


def _unavailable(response):
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "unavailable"
    assert "provider unavailable" in payload["message"]
    return payload


def test_create_app_nexus_write_routes_return_side_effect_free_fallbacks():
    client = TestClient(create_app())

    for path, _method, _handler, body in WRITE_ROUTES:
        payload = _unavailable(client.post(path, json=body))
        assert payload["message"].startswith("nexus ")

    upload = client.post(
        "/nexus/upload",
        data={"project": "default"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    upload_payload = _unavailable(upload)
    assert upload_payload["job_id"] is None
    assert upload_payload["document_id"] is None


def test_create_app_write_fallbacks_do_not_call_production_or_heavy_providers(monkeypatch):
    def fail_provider(*args, **kwargs):
        raise AssertionError("production provider was called")

    provider_names = [
        "nexus_upload_provider",
        "nexus_search_provider",
        "nexus_web_search_provider",
        "nexus_web_research_provider",
        "nexus_research_provider",
        "nexus_deep_research_provider",
        "nexus_recursive_research_provider",
        "nexus_sources_search_provider",
        "nexus_evidence_add_from_chunks_provider",
        "nexus_research_followup_provider",
        "nexus_web_collect_provider",
        "nexus_ask_provider",
        "nexus_report_build_provider",
    ]
    for name in provider_names:
        monkeypatch.setattr(main.app.state, name, fail_provider, raising=False)

    client = TestClient(create_app())
    for path, _method, _handler, body in WRITE_ROUTES:
        assert client.post(path, json=body).status_code == 200


def test_main_app_registers_nexus_write_providers_as_callables():
    for name in [
        "nexus_upload_provider",
        "nexus_search_provider",
        "nexus_web_search_provider",
        "nexus_web_research_provider",
        "nexus_research_provider",
        "nexus_deep_research_provider",
        "nexus_recursive_research_provider",
        "nexus_sources_search_provider",
        "nexus_evidence_add_from_chunks_provider",
        "nexus_research_followup_provider",
        "nexus_web_collect_provider",
        "nexus_ask_provider",
        "nexus_report_build_provider",
    ]:
        assert callable(getattr(main.app.state, name))


def test_moved_nexus_write_routes_are_owned_by_app_api_nexus():
    expected = [
        ("/nexus/upload", "POST", "nexus_upload_api"),
        ("/nexus/search", "POST", "nexus_search_api"),
        ("/nexus/web/search", "POST", "nexus_web_search_api"),
        ("/nexus/web/research", "POST", "nexus_web_research_api"),
        ("/nexus/research/run", "POST", "nexus_research_run_api"),
        ("/nexus/sources/search", "POST", "nexus_sources_search_api"),
        ("/nexus/evidence/add-from-chunks", "POST", "nexus_evidence_add_from_chunks_api"),
        ("/nexus/research/jobs/{job_id}/followup", "POST", "nexus_research_followup_api"),
        ("/nexus/web/collect", "POST", "nexus_web_collect_api"),
        ("/nexus/ask", "POST", "nexus_ask_api"),
        ("/nexus/report/build", "POST", "nexus_report_build_api"),
    ]
    for path, method, handler_name in expected:
        route = _route(path, method)
        assert route.endpoint.__module__ == "app.api.nexus"
        assert route.endpoint.__name__ == handler_name


def test_nexus_execution_boundary_stays_out_of_api_router():
    service_text = SERVICE_PATH.read_text(encoding="utf-8")
    api_text = API_NEXUS_PATH.read_text(encoding="utf-8")
    router_text = ROUTER_PATH.read_text(encoding="utf-8")

    assert "import main" not in service_text
    assert "from main" not in service_text
    assert "from app.services.nexus_execution" not in api_text
    assert "run_research_async" not in api_text
    assert "execute_web_search_service" not in api_text
    assert "accept_upload" not in api_text
    assert '@nexus_router.post("/upload")' not in router_text
    assert '@nexus_router.post("/search")' not in router_text
    assert '@nexus_router.post("/web/search")' not in router_text
    assert '@nexus_router.post("/web/research")' not in router_text
    assert '@nexus_router.post("/research/run")' not in router_text
    assert '@nexus_router.post("/sources/search")' not in router_text
    assert '@nexus_router.post("/evidence/add-from-chunks")' not in router_text
    assert '@nexus_router.post("/research/jobs/{job_id}/followup")' not in router_text
    assert '@nexus_router.post("/web/collect")' not in router_text
    assert '@nexus_router.post("/ask")' not in router_text


def test_fallback_response_shapes_keep_legacy_keys():
    client = TestClient(create_app())

    search = _unavailable(client.post("/nexus/search", json={"query": "alpha", "as_evidence": True}))
    assert search["results"] == []
    assert search["applied_filters"] == {}
    assert search["evidence"] == []

    web_search = _unavailable(client.post("/nexus/web/search", json={"query": "alpha"}))
    assert web_search["job_id"] is None
    assert web_search["operation"] == "web.search"
    assert web_search["result"]["items"] == []
    assert web_search["result"]["total_items"] == 0

    report = _unavailable(client.post("/nexus/report/build", json={"job_id": "job-1"}))
    assert report["job_id"] == "job-1"
    assert report["report_id"] is None
    assert report["report_md_path"] == ""
