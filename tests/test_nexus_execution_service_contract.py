from pathlib import Path

import main
from app.nexus.router import NexusSearchRequest, NexusWebSearchRequest
from app.services import nexus_execution

SERVICE_PATH = Path("app/services/nexus_execution.py")
API_NEXUS_PATH = Path("app/api/nexus.py")


def _route(path: str, method: str):
    routes = [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(routes) == 1
    return routes[0]


def test_nexus_execution_service_module_exists_and_exports_contract_functions():
    assert SERVICE_PATH.exists()
    for name in [
        "run_nexus_research_service",
        "run_nexus_deep_research_service",
        "run_nexus_recursive_research_service",
        "ingest_nexus_document_service",
        "index_nexus_document_service",
        "run_nexus_web_search_service",
        "run_nexus_web_research_service",
        "collect_nexus_web_sources_service",
        "run_nexus_sources_search_service",
        "add_nexus_evidence_from_chunks_service",
        "build_nexus_report_service",
    ]:
        assert callable(getattr(nexus_execution, name))


def test_nexus_execution_service_has_no_main_import_or_http_route_ownership():
    text = SERVICE_PATH.read_text(encoding="utf-8")

    assert "import main" not in text
    assert "from main" not in text
    assert "APIRouter" not in text
    assert "@router" not in text
    assert "@app" not in text
    assert "nexus_router" not in text


def test_nexus_route_owner_remains_existing_router_for_write_research_ingest_routes():
    expected = [
        ("/nexus/upload", "POST", "nexus_upload"),
        ("/nexus/search", "POST", "nexus_search"),
        ("/nexus/web/search", "POST", "nexus_web_search"),
        ("/nexus/web/research", "POST", "nexus_web_research"),
        ("/nexus/research/run", "POST", "nexus_research_run"),
        ("/nexus/web/collect", "POST", "nexus_web_collect"),
        ("/nexus/evidence/add-from-chunks", "POST", "nexus_evidence_add_from_chunks"),
        ("/nexus/documents/{document_id}", "DELETE", "nexus_delete_document"),
    ]
    for path, method, handler_name in expected:
        route = _route(path, method)
        assert route.endpoint.__module__ == "app.nexus.router"
        assert route.endpoint.__name__ == handler_name


def test_api_nexus_keeps_read_only_status_list_scope_only():
    text = API_NEXUS_PATH.read_text(encoding="utf-8")

    assert '@router.get("/nexus/summary")' in text
    assert '@router.get("/nexus/documents")' in text
    assert '@router.get("/nexus/jobs/active")' in text
    assert '@router.get("/nexus/web/status")' in text
    assert "@router.post" not in text
    assert "@router.delete" not in text
    assert '"/nexus/research' not in text
    assert '"/nexus/upload' not in text
    assert '"/nexus/web/search' not in text


def test_web_search_service_preserves_canonical_response_shape():
    payload = NexusWebSearchRequest(query="nexus execution", max_results_per_query=2)

    def fake_execute_web_search(**kwargs):
        assert kwargs["query"] == "nexus execution"
        return {
            "job_id": "job-1",
            "queries": ["nexus execution"],
            "saved_evidence": 2,
            "search": {
                "provider": "searxng",
                "selected_provider": "searxng",
                "items": [{"title": "Result", "url": "https://example.test"}],
                "configured": True,
            },
        }

    result = nexus_execution.run_nexus_web_search_service(payload, execute_web_search=fake_execute_web_search)

    assert result["ok"] is True
    assert result["operation"] == "web.search"
    assert result["request"]["query"] == "nexus execution"
    body = result["result"]
    assert body["job_id"] == "job-1"
    assert body["queries"] == ["nexus execution"]
    assert body["saved_evidence"] == 2
    assert body["provider"] == "searxng"
    assert body["selected_provider"] == "searxng"
    assert body["items"][0]["provider"] == "searxng"
    assert body["items"][0]["engine"] == "searxng"
    assert body["total_items"] == 1
    assert body["search"]["total_items"] == 1


def test_search_service_preserves_library_search_response_shape():
    payload = NexusSearchRequest(query="alpha", limit=3, as_evidence=False)

    def fake_search_evidence(**kwargs):
        assert kwargs["query"] == "alpha"
        assert kwargs["limit"] == 3
        return ([{"chunk": {"title": "A"}}], {"scope": "all"})

    result = nexus_execution.run_nexus_search_service(payload, search_evidence=fake_search_evidence)

    assert result == {
        "query": "alpha",
        "scope": None,
        "doc_types": [],
        "limit": 3,
        "top_k": None,
        "filters": {},
        "applied_filters": {"scope": "all"},
        "results": [{"chunk": {"title": "A"}}],
    }
