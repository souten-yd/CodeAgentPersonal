"""PDT-9 tests for runtime collectors and ingestor."""

from __future__ import annotations

from agent.project_twin.runtime_collectors import (
    ApiObservationCollector,
    PlayConsoleCollector,
    PlaywrightCollector,
    PytestCollector,
    RuntimeObservationIngestor,
)
from agent.project_twin.store import SqliteProjectTwinStore


def test_pytest_collector_distinguishes_pass_fail():
    obs = PytestCollector().collect({
        "project_id": "p1", "collector_version": "8.0",
        "tests": [
            {"nodeid": "tests/test_x.py::test_ok", "outcome": "passed"},
            {"nodeid": "tests/test_x.py::test_bad", "outcome": "failed"},
            {"nodeid": "tests/test_x.py::test_skip", "outcome": "skipped"},
        ],
    })
    by_result = {o.summary.split(" -> ")[0]: o.result for o in obs}
    assert by_result["tests/test_x.py::test_ok"] == "passed"
    assert by_result["tests/test_x.py::test_bad"] == "failed"
    assert by_result["tests/test_x.py::test_skip"] == "observed"
    # links to the structural test ref
    assert obs[0].subject_refs == ["test://tests/test_x.py::test_ok"]


def test_unavailable_pytest_never_becomes_success():
    obs = PytestCollector().collect({"project_id": "p1", "available": False, "reason": "pytest missing"})
    assert len(obs) == 1
    assert obs[0].result == "unavailable"
    assert obs[0].result != "passed"


def test_playwright_unavailable_is_truthful():
    obs = PlaywrightCollector().collect({"project_id": "p1", "available": False, "reason": "browser_not_installed"})
    assert obs[0].result == "unavailable"


def test_playwright_observed_and_failed():
    ok = PlaywrightCollector().collect({"project_id": "p1", "summary": "loaded"})
    assert ok[0].result == "observed"
    bad = PlaywrightCollector().collect({"project_id": "p1", "errors": ["boom"]})
    assert bad[0].result == "failed"


def test_api_collector_marks_5xx_failed():
    ok = ApiObservationCollector().collect({"project_id": "p1", "method": "get", "path": "/items", "status": 200})
    assert ok[0].result == "observed" and ok[0].subject_refs == ["route://GET /items"]
    bad = ApiObservationCollector().collect({"project_id": "p1", "method": "post", "path": "/x", "status": 503})
    assert bad[0].result == "failed"


def test_play_console_failed_request_and_error():
    obs = PlayConsoleCollector().collect({
        "project_id": "p1", "session_id": "s1",
        "console": [{"level": "error", "text": "TypeError"}, {"level": "log", "text": "ok"}],
        "failed_requests": [{"method": "get", "url": "/api/missing", "status": 404}],
    })
    results = sorted(o.result for o in obs)
    assert results == ["failed", "failed", "observed"]


def test_ingestor_stores_observation_and_reports_unavailable():
    store = SqliteProjectTwinStore(":memory:")
    ing = RuntimeObservationIngestor(store)

    passed = PytestCollector().collect({"project_id": "p1", "tests": [{"nodeid": "tests/t.py::t", "outcome": "passed"}]})[0]
    res = ing.ingest(passed)
    assert res.accepted is True and res.twin_revision_id is not None
    row = store._conn.execute("SELECT result FROM twin_observations WHERE project_id='p1'").fetchone()
    assert row["result"] == "passed"

    # an unavailable observation with no project cannot be ingested as project truth
    unavailable = PytestCollector().collect({"project_id": "p1", "available": False})[0]
    res2 = ing.ingest(unavailable)
    assert res2.accepted is False
    assert any(d["code"] == "collector_unavailable" for d in res2.diagnostics)
    store.close()
