"""PI-9 context, path, impact, and test-selection v2 tests.

Acceptance criteria (implementation plan PI-9):
- no full graph dump into prompts (bounded);
- target and mandatory requirements receive priority;
- stale/contradicted information is labeled or excluded;
- source excerpts match the manifest source revision;
- context can be generated without Atlas-specific schemas (portable).
Plus impact (resolved vs candidate callers, recommended tests) and path tracing.
"""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.contracts import ContextItem
from agent.project_twin.analyzers.behavioral import BehavioralAnalyzer
from agent.project_twin.analyzers.default import build_default_registry
from agent.project_twin.query.context import build_context_package
from agent.project_twin.query.impact import assess_impact, select_tests, trace_path
from agent.project_twin.query.metrics import precision_recall
from agent.project_twin.runtime.collectors import normalize_pytest

ROOT = Path(".")

FIXTURE = {
    "app.py": (
        "def helper():\n    return 1\n"
        "def handler():\n    return helper()\n"
        "def caller():\n    return handler()\n"
    ),
}


def _graphs(files=FIXTURE):
    sem = build_default_registry().analyze_project(ROOT, files).graph
    beh, _ = BehavioralAnalyzer().analyze_project(files)
    return sem, beh


# --- Impact ------------------------------------------------------------------

def test_impact_resolved_and_transitive_callers() -> None:
    sem, beh = _graphs()
    report = assess_impact(sem, beh, "py://app#handler")
    assert "py://app#caller" in report.direct_callers
    report2 = assess_impact(sem, beh, "py://app#helper")
    assert "py://app#handler" in report2.direct_callers
    assert "py://app#caller" in report2.transitive_callers  # helper <- handler <- caller


def test_impact_recommended_tests_from_coverage() -> None:
    sem, beh = _graphs()
    obs = normalize_pytest({"tests": [{"nodeid": "tests/test_app.py::test_handler", "outcome": "passed"}]},
                           project_id="p1", workspace_id="w1", source_revision="r1",
                           coverage={"app.py": ["handler"]})
    report = assess_impact(sem, beh, "py://app#handler", runtime=obs)
    assert "test://tests/test_app.py::test_handler" in report.recommended_tests


def test_path_tracing_found_and_not_found() -> None:
    sem, _ = _graphs()
    ok = trace_path(sem, "py://app#caller", "py://app#helper")
    assert ok.found and ok.path[0] == "py://app#caller" and ok.path[-1] == "py://app#helper"
    missing = trace_path(sem, "py://app#helper", "py://app#caller")
    assert missing.found is False and "no path" in missing.diagnostics[0]


def test_impact_metrics_recorded() -> None:
    m = precision_recall(predicted={"a", "b"}, actual={"a", "c"})
    assert m["true_positives"] == 1.0
    assert 0.0 <= m["precision"] <= 1.0 and 0.0 <= m["recall"] <= 1.0


# --- Context package ---------------------------------------------------------

def test_context_is_bounded_no_full_graph_dump() -> None:
    # A larger graph but a tiny budget must not dump everything.
    files = {f"m{i}.py": f"def f{i}():\n    return {i}\n" for i in range(40)}
    sem, beh = _graphs(files)
    pkg = build_context_package(
        project_id="p1", workspace_id="w1", phase="planning", objective="x",
        target_refs=["py://m0#f0"], token_budget=50, semantic=sem, behavioral=beh,
    )
    total_items = len(pkg.symbols) + len(pkg.interfaces) + len(pkg.behavior_paths)
    assert total_items < sem.node_count  # not a full dump
    assert pkg.manifest.used_tokens <= pkg.manifest.token_budget or pkg.manifest.truncated


def test_mandatory_requirements_and_target_prioritized() -> None:
    sem, beh = _graphs()
    mandatory = [ContextItem(ref="requirement://R1", kind="requirement", summary="must do",
                             status="mandatory", inclusion_reason="mandatory")]
    pkg = build_context_package(
        project_id="p1", workspace_id="w1", phase="planning", objective="x",
        target_refs=["py://app#handler"], token_budget=1, semantic=sem, behavioral=beh,
        requirements=mandatory,
    )
    # Even with budget=1, the mandatory requirement is never dropped.
    assert any(r.ref == "requirement://R1" for r in pkg.requirements)
    assert "requirement://R1" in pkg.manifest.included_refs


def test_contradicted_labeled_in_uncertainties() -> None:
    sem, beh = _graphs()
    pkg = build_context_package(
        project_id="p1", workspace_id="w1", phase="planning", objective="x",
        target_refs=["py://app#handler"], token_budget=500, semantic=sem, behavioral=beh,
        contradicted_refs={"py://app#handler"},
    )
    assert any(u.ref == "py://app#handler" and u.status == "contradicted" for u in pkg.uncertainties)
    # The contradicted ref is not presented as a normal symbol.
    assert all(s.ref != "py://app#handler" for s in pkg.symbols)


def test_stale_is_labeled() -> None:
    sem, beh = _graphs()
    pkg = build_context_package(
        project_id="p1", workspace_id="w1", phase="planning", objective="x",
        target_refs=["py://app#handler"], token_budget=500, semantic=sem, behavioral=beh,
        stale_refs={"py://app#handler"},
    )
    handler = next(s for s in pkg.symbols if s.ref == "py://app#handler")
    assert "stale" in handler.inclusion_reason


def test_source_excerpts_match_manifest_revision() -> None:
    sem, beh = _graphs()
    pkg = build_context_package(
        project_id="p1", workspace_id="w1", phase="generation", objective="x",
        target_refs=["py://app#handler"], token_budget=500, semantic=sem, behavioral=beh,
        sources=FIXTURE, source_revision="rev-XYZ",
    )
    assert pkg.source_material, "expected a source excerpt for the target file"
    assert all(s.source_revision == "rev-XYZ" for s in pkg.source_material)
    assert pkg.manifest.source_revisions.get("app.py") == "rev-XYZ"


def test_context_is_portable_serializes() -> None:
    sem, beh = _graphs()
    pkg = build_context_package(
        project_id="p1", workspace_id="w1", phase="planning", objective="x",
        target_refs=["py://app#handler"], token_budget=500, semantic=sem, behavioral=beh,
    )
    # No Atlas schema needed: the package is a pure contract DTO and serializes.
    assert pkg.model_dump_json()
    assert pkg.contract_version  # digital_twin.v2
