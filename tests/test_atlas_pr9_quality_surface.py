from __future__ import annotations

from types import SimpleNamespace

from agent.atlas_orchestration_summary import AtlasOrchestrationSummaryBuilder
from agent.atlas_run_quality_rollup import compute_run_quality_rollup
from agent.atlas_requirement_tracer import AtlasRequirementTracer

_BUILDER = AtlasOrchestrationSummaryBuilder()


def _pool_data(*, metadata=None, status="ready", warnings=None):
    return {"pool_id": "p1", "status": status, "items": [], "warnings": warnings or [],
            "errors": [], "metadata": metadata or {}}


def _ns_pool(*, metadata=None, status="ready"):
    return SimpleNamespace(metadata=metadata or {}, items=[], project_path="", status=status)


def _result(status="completed", changed_files=None, vr_status="passed"):
    return SimpleNamespace(status=status, changed_files=changed_files or [],
                           verification_result={"status": vr_status})


# ── quality_rollup surfaced in orchestration summary via pool metadata ─────────

def test_quality_rollup_empty_by_default():
    summary = _BUILDER.build_from_pool_and_state(_pool_data(), None)
    assert "quality_rollup" in summary.metadata
    assert summary.metadata["quality_rollup"] == {}


def test_quality_rollup_surfaced_when_present():
    pool = _pool_data(metadata={"quality_rollup": {"degraded": False, "degrade_reasons": []}})
    summary = _BUILDER.build_from_pool_and_state(pool, None)
    assert summary.metadata["quality_rollup"] == {"degraded": False, "degrade_reasons": []}


def test_feature_summary_surfaced():
    pool = _pool_data(metadata={"feature_summary": {"selected": ["playwright"], "blocked": []}})
    summary = _BUILDER.build_from_pool_and_state(pool, None)
    assert summary.metadata["feature_summary"]["selected"] == ["playwright"]


def test_plan_revision_required_surfaced():
    pool = _pool_data(metadata={"plan_revision_required": True})
    summary = _BUILDER.build_from_pool_and_state(pool, None)
    assert summary.metadata["plan_revision_required"] is True


def test_critique_clarification_options_surfaced():
    opts = {"options": [{"option_id": "revise_0", "merit": "x", "risk": "y"}]}
    pool = _pool_data(metadata={"critique_clarification_options": opts})
    summary = _BUILDER.build_from_pool_and_state(pool, None)
    assert summary.metadata["critique_clarification_options"] == opts


# ── compute_run_quality_rollup feeds quality_rollup to autopilot metadata ──────

def test_rollup_degrade_reasons_empty_when_all_good(tmp_path):
    pool = _ns_pool(metadata={})
    rollup = compute_run_quality_rollup(pool, [_result()], project_path=str(tmp_path))
    assert rollup["degraded"] is False
    assert rollup["degrade_reasons"] == []


def test_rollup_degrades_on_no_evidence(tmp_path):
    reqs = AtlasRequirementTracer().extract_requirements("Add a renderer module.")
    pool = _ns_pool(metadata={"requirement_trace": reqs})
    rollup = compute_run_quality_rollup(pool, [_result(status="failed", changed_files=[])],
                                        project_path=str(tmp_path))
    assert rollup["degraded"] is True
    assert "requirement_coverage_incomplete" in rollup["degrade_reasons"]


# ── structured clarification options shape ────────────────────────────────────

def test_clarification_options_have_required_fields():
    opts = {
        "options": [
            {"option_id": "revise_0", "label": "Security", "description": "Fix auth",
             "merit": "safer", "risk": "delay", "recommendation": "revise"}
        ],
        "ambiguity_signals": [],
        "gate_evaluation": {"clarification_required": False, "gate_status": "passed"},
    }
    # Options must contain required keys
    for o in opts["options"]:
        assert "option_id" in o
        assert "merit" in o
        assert "risk" in o
        assert "recommendation" in o
