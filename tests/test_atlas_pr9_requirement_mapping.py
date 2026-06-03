from __future__ import annotations

from types import SimpleNamespace

from agent.atlas_requirement_tracer import AtlasRequirementTracer
from agent.atlas_run_quality_rollup import compute_run_quality_rollup

_TRACER = AtlasRequirementTracer()


def _pool(metadata=None, items=None, project_path=""):
    return SimpleNamespace(metadata=metadata or {}, items=items or [], project_path=project_path)


def _result(status="completed", changed_files=None, vr_status="passed"):
    return SimpleNamespace(status=status, changed_files=changed_files or [],
                           verification_result={"status": vr_status})


# ── map_requirements_to_evidence ──────────────────────────────────────────────

def test_matched_changed_file_is_implemented():
    reqs = [{"requirement_id": "req_001", "description": "add a renderer module for the canvas",
             "planned_files": [], "implementation_evidence": [], "verification_method": "", "status": "planned"}]
    mapped = _TRACER.map_requirements_to_evidence(reqs, changed_files=["js/renderer.js"], verified_files=[])
    assert mapped[0]["status"] == "implemented"
    assert "js/renderer.js" in mapped[0]["implementation_evidence"]


def test_matched_and_verified_is_verified():
    reqs = [{"requirement_id": "req_001", "description": "add a renderer module",
             "planned_files": [], "implementation_evidence": [], "verification_method": "", "status": "planned"}]
    mapped = _TRACER.map_requirements_to_evidence(reqs, changed_files=["js/renderer.js"],
                                                  verified_files=["js/renderer.js"])
    assert mapped[0]["status"] == "verified"
    assert mapped[0]["verification_method"] == "verification_passed"


def test_unmapped_requirement_stays_partial():
    reqs = [{"requirement_id": "req_001", "description": "support keyboard input handling",
             "planned_files": [], "implementation_evidence": [], "verification_method": "", "status": "planned"}]
    # changed file does not share keywords with the requirement
    mapped = _TRACER.map_requirements_to_evidence(reqs, changed_files=["css/style.css"], verified_files=[])
    assert mapped[0]["status"] == "partial"


def test_no_changes_is_missing():
    reqs = [{"requirement_id": "req_001", "description": "add a collision system",
             "planned_files": [], "implementation_evidence": [], "verification_method": "", "status": "planned"}]
    mapped = _TRACER.map_requirements_to_evidence(reqs, changed_files=[], verified_files=[])
    assert mapped[0]["status"] == "missing"


# ── coverage in rollup ────────────────────────────────────────────────────────

def test_rollup_coverage_reports_mapped_statuses(tmp_path):
    reqs = _TRACER.extract_requirements("Add a renderer module. Add a collision system.")
    pool = _pool(metadata={"requirement_trace": reqs}, project_path=str(tmp_path))
    # only renderer changed + verified
    rollup = compute_run_quality_rollup(
        pool, [_result(changed_files=["js/renderer.js"], vr_status="passed")], project_path=str(tmp_path))
    cov = rollup["requirement_coverage"]
    assert cov["by_status"].get("verified", 0) >= 1
    # collision requirement unmapped → partial
    assert cov["by_status"].get("partial", 0) >= 1
    assert cov["all_verified"] is False


def test_requirement_checked_only_when_all_verified(tmp_path):
    reqs = _TRACER.extract_requirements("Add a renderer module.")
    pool = _pool(metadata={"requirement_trace": reqs}, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(
        pool, [_result(changed_files=["js/renderer.js"], vr_status="passed")], project_path=str(tmp_path))
    cov = rollup["requirement_coverage"]
    assert cov["all_verified"] is True


def test_no_evidence_marks_missing_and_degrades(tmp_path):
    reqs = _TRACER.extract_requirements("Add a renderer module. Add collision.")
    pool = _pool(metadata={
        "requirement_trace": reqs,
        "automation_features": {"requirement_coverage_enforcement": "enforce"},
    }, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(pool, [_result(status="failed", changed_files=[])],
                                        project_path=str(tmp_path))
    assert rollup["requirement_coverage"]["no_implementation_evidence"] is True
    assert "requirement_coverage_incomplete" in rollup["degrade_reasons"]


def test_no_evidence_warns_without_degrading_by_default(tmp_path):
    reqs = _TRACER.extract_requirements("Add a renderer module.")
    pool = _pool(metadata={"requirement_trace": reqs}, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(pool, [_result(status="failed", changed_files=[])],
                                        project_path=str(tmp_path))
    assert rollup["requirement_coverage"]["no_implementation_evidence"] is True
    assert rollup["requirement_coverage"]["enforcement"] == "warn"
    assert "requirement_coverage_incomplete" in rollup["warnings"]
    assert "requirement_coverage_incomplete" not in rollup["degrade_reasons"]


def test_partial_does_not_degrade(tmp_path):
    (tmp_path / "css").mkdir()
    (tmp_path / "css" / "style.css").write_text("body{color:red}", encoding="utf-8")
    reqs = _TRACER.extract_requirements("Support keyboard input handling here.")
    pool = _pool(metadata={"requirement_trace": reqs}, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(pool, [_result(changed_files=["css/style.css"], vr_status="passed")],
                                        project_path=str(tmp_path))
    assert rollup["requirement_coverage"]["by_status"].get("partial", 0) >= 1
    assert "requirement_coverage_incomplete" not in rollup["degrade_reasons"]


def test_japanese_rainbow_html_maps_to_implementation_signal(tmp_path):
    (tmp_path / "index.html").write_text(
        "<!doctype html><html><body><div class='rainbow'>虹</div>"
        "<style>.rainbow{animation:shift 2s infinite;color:hsl(120 80% 50%)}"
        "@keyframes shift{from{filter:hue-rotate(0deg)}to{filter:hue-rotate(360deg)}}"
        "</style></body></html>",
        encoding="utf-8",
    )
    reqs = _TRACER.extract_requirements("レインボー表示を追加する。")
    pool = _pool(metadata={"requirement_trace": reqs}, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(pool, [_result(changed_files=["index.html"], vr_status="passed")],
                                        project_path=str(tmp_path))
    assert rollup["requirement_coverage"]["by_status"].get("verified", 0) == len(reqs)
    assert "requirement_coverage_incomplete" not in rollup["warnings"]
    assert "requirement_coverage_incomplete" not in rollup["degrade_reasons"]
