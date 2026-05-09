import ast
import json
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.server import create_app

API_NEXUS_PATH = Path("app/api/nexus.py")
SERVICE_PATH = Path("app/services/nexus_execution.py")
ROUTER_PATH = Path("app/nexus/router.py")
ROUTE_INVENTORY_PATH = Path("docs/generated/route_inventory.json")
DOC_PATHS = [
    Path("docs/api_route_ownership_inventory.md"),
    Path("docs/refactor_recovery_map.md"),
    Path("docs/refactor_remaining_main_routes_inventory.md"),
]

MOVED_NEXUS_ROUTES = [
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

MOVED_ROUTER_DECORATORS = [
    '@nexus_router.post("/upload")',
    '@nexus_router.post("/search")',
    '@nexus_router.post("/web/search")',
    '@nexus_router.post("/web/research")',
    '@nexus_router.post("/research/run")',
    '@nexus_router.post("/sources/search")',
    '@nexus_router.post("/evidence/add-from-chunks")',
    '@nexus_router.post("/research/jobs/{job_id}/followup")',
    '@nexus_router.post("/web/collect")',
    '@nexus_router.post("/ask")',
    '@nexus_router.post("/report/build")',
]

HEAVY_API_IMPORTS_OR_CALLS = {
    "accept_upload",
    "add_nexus_evidence_from_chunks_service",
    "build_job_report",
    "build_nexus_report_service",
    "collect_nexus_web_sources_service",
    "collect_web_sources",
    "execute_web_search_service",
    "get_conn",
    "index_document",
    "ingest_nexus_document_service",
    "run_nexus_ask_service",
    "run_nexus_deep_research_service",
    "run_nexus_recursive_research_service",
    "run_nexus_research_followup_service",
    "run_nexus_research_service",
    "run_nexus_search_service",
    "run_nexus_sources_search_service",
    "run_nexus_web_research_service",
    "run_nexus_web_search_service",
    "run_research_async",
    "search_evidence",
    "subprocess",
    "threading",
}


def _route(path: str, method: str, app=main.app):
    matches = [
        route
        for route in app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_app_nexus_router_has_no_moved_route_decorators_and_documents_residue_role():
    router_text = ROUTER_PATH.read_text(encoding="utf-8")
    for decorator in MOVED_ROUTER_DECORATORS:
        assert decorator not in router_text

    assert "provider payload helper" in router_text
    assert "routes that were not part of the PR4.52 move" in router_text
    assert "app/api/nexus.py" in router_text
    assert "app/services/nexus_execution.py" in router_text


def test_app_api_nexus_is_moved_route_owner_in_main_and_create_app():
    for app in (main.app, create_app()):
        for path, method, handler_name in MOVED_NEXUS_ROUTES:
            route = _route(path, method, app=app)
            assert route.endpoint.__module__ == "app.api.nexus"
            assert route.endpoint.__name__ == handler_name


def test_app_api_nexus_stays_thin_provider_and_fallback_layer():
    api_text = API_NEXUS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(api_text)

    imported_names = set()
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_names.add(module)
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    assert "app.services.nexus_execution" not in imported_names
    assert not (HEAVY_API_IMPORTS_OR_CALLS & imported_names)
    assert not (HEAVY_API_IMPORTS_OR_CALLS & called_names)

    client = TestClient(create_app())
    response = client.post("/nexus/research/run", json={"query": "baseline", "mode": "deep"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "unavailable"


def test_nexus_execution_service_has_no_route_ownership_or_main_import():
    service_text = SERVICE_PATH.read_text(encoding="utf-8")
    assert "import main" not in service_text
    assert "from main" not in service_text
    assert "APIRouter" not in service_text
    assert "@router." not in service_text
    assert "@nexus_router." not in service_text


def test_generated_route_inventory_has_no_duplicate_path_method_pairs():
    inventory = json.loads(ROUTE_INVENTORY_PATH.read_text(encoding="utf-8"))
    pairs = [
        (entry["path"], method)
        for entry in inventory
        for method in entry.get("methods", [])
    ]
    duplicates = [pair for pair, count in Counter(pairs).items() if count > 1]
    assert duplicates == []


def test_docs_record_v28_baseline_and_nexus_ownership():
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "KasaneCore_v2.8" in text
        assert "e94c20dfe0d23e233f4dbc817af994408e739b80" in text
        assert "app/api/nexus.py" in text
        assert "app/services/nexus_execution.py" in text

    combined = "\n".join(path.read_text(encoding="utf-8") for path in DOC_PATHS)
    assert "Nexus/Lumen/ASR/TTS/LLM" in combined or "Nexus / Lumen / ASR / TTS / LLM" in combined
