import json
from pathlib import Path


BASELINE_DOCS = [
    Path("docs/runbooks/known_good_runtime_baseline.md"),
    Path("docs/refactor_recovery_map.md"),
    Path("docs/refactor_remaining_main_routes_inventory.md"),
]
ROUTER_PATH = Path("app/nexus/router.py")
API_NEXUS_PATH = Path("app/api/nexus.py")
SERVICE_PATH = Path("app/services/nexus_execution.py")
ROUTE_INVENTORY_JSON = Path("docs/generated/route_inventory.json")
MAIN_INVENTORY_DOC = Path("docs/refactor_remaining_main_routes_inventory.md")

MOVED_NEXUS_DECORATORS = [
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

MOVED_NEXUS_ROUTES = [
    ("/nexus/upload", "POST", "app.api.nexus"),
    ("/nexus/search", "POST", "app.api.nexus"),
    ("/nexus/web/search", "POST", "app.api.nexus"),
    ("/nexus/web/research", "POST", "app.api.nexus"),
    ("/nexus/research/run", "POST", "app.api.nexus"),
    ("/nexus/sources/search", "POST", "app.api.nexus"),
    ("/nexus/evidence/add-from-chunks", "POST", "app.api.nexus"),
    ("/nexus/research/jobs/{job_id}/followup", "POST", "app.api.nexus"),
    ("/nexus/web/collect", "POST", "app.api.nexus"),
    ("/nexus/ask", "POST", "app.api.nexus"),
    ("/nexus/report/build", "POST", "app.api.nexus"),
]


def _route_rows():
    return json.loads(ROUTE_INVENTORY_JSON.read_text(encoding="utf-8"))


def test_docs_lock_kasanecore_v2_8_baseline_and_health_confirmation():
    for path in BASELINE_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "KasaneCore_v2.8" in text
        assert "e94c20dfe0d23e233f4dbc817af994408e739b80" in text

    combined = "\n".join(path.read_text(encoding="utf-8") for path in BASELINE_DOCS)
    assert "KasaneCore_v2.8 == main at e94c20dfe0d23e233f4dbc817af994408e739b80" in combined
    assert "LLM / ASR / TTS / Nexus / Lumen" in combined
    assert "Runpod LLM" in combined
    assert "-ngl=999 -> OK" in combined
    assert "parsed_n_gpu_layers=43" in combined
    assert "LLM ready" in combined
    assert "warm-up complete" in combined
    assert "ASR OK" in combined
    assert "TTS/SBV2 OK" in combined
    assert "Nexus write/research/ingest route移動後も機能OK" in combined


def test_app_nexus_router_has_no_moved_write_research_ingest_decorators():
    text = ROUTER_PATH.read_text(encoding="utf-8")
    for decorator in MOVED_NEXUS_DECORATORS:
        assert decorator not in text

    assert "provider payload helper" in text
    assert "legacy" in text
    assert "non-moved Nexus route" in text
    assert "Do not re-add moved POST route decorators here" in text


def test_app_api_nexus_is_thin_route_provider_fallback_layer():
    text = API_NEXUS_PATH.read_text(encoding="utf-8")
    assert "HTTP routes, request parsing" in text
    assert "provider dispatch" in text
    assert "app-factory fallback" in text
    assert "from app.services.nexus_execution" not in text
    assert "execute_web_search_service" not in text
    assert "run_research_async" not in text
    assert "accept_upload" not in text
    assert "build_job_report" not in text


def test_nexus_execution_service_has_no_route_ownership_or_main_import():
    text = SERVICE_PATH.read_text(encoding="utf-8")
    assert "import main" not in text
    assert "from main" not in text
    assert "APIRouter" not in text
    assert "@router" not in text
    assert "@app" not in text


def test_route_inventory_has_no_duplicate_path_method_and_locks_moved_owners():
    seen = {}
    duplicates = []
    for row in _route_rows():
        for method in row["methods"]:
            key = (row["path"], method)
            if key in seen:
                duplicates.append(key)
            seen[key] = row
    assert not duplicates

    for path, method, module in MOVED_NEXUS_ROUTES:
        assert seen[(path, method)]["module"] == module

    assert seen[("/jobs/submit", "POST")]["module"] == "app.api.jobs"


def test_main_py_remaining_endpoints_are_classified_as_high_risk_runtime_inventory():
    text = MAIN_INVENTORY_DOC.read_text(encoding="utf-8")
    for heading in [
        "model runtime high-risk",
        "audio runtime high-risk",
        "app orchestration",
        "already extracted",
    ]:
        assert heading in text

    for required in [
        "auto-load",
        "model switch",
        "llama lifecycle",
        "Runpod/Linux NGL探索",
        "Windows auto-fit",
        "ASR",
        "TTS",
        "Echo WebSocket",
        "SBV2 runtime",
        "Lumen/Chat execution",
        "job background execution",
        "project/history/files",
        "jobs router",
        "jobs service",
        "Nexus router",
        "Nexus execution service",
        "Echo read-only router",
        "runtime controls router",
    ]:
        assert required in text
