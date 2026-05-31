from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.atlas_repair_intent_classifier import classify_repair_intent
from agent.atlas_requirement_tracer import AtlasRequirementTracer
from agent.atlas_run_quality_rollup import compute_run_quality_rollup


def _pool(metadata=None, items=None, project_path=""):
    return SimpleNamespace(metadata=metadata or {}, items=items or [], project_path=project_path)


def _item(item_type="implementation", target_files=None, file_changes=None):
    return SimpleNamespace(item_type=item_type, target_files=target_files or [], metadata={"file_changes": file_changes or []})


def _result(status="completed", changed_files=None):
    return SimpleNamespace(status=status, changed_files=changed_files or [])


# ── Repair intent into planner metadata ───────────────────────────────────────

def test_repair_intent_passes_previous_changed_files():
    r = classify_repair_intent("color is not changing and movement is not linear",
                               previous_changed_files=["index.html"])
    assert r["is_repair"] is True
    assert "index.html" in r["primary_target_files"]


# ── Requirement coverage gating ───────────────────────────────────────────────

def test_no_implementation_evidence_degrades(tmp_path):
    reqs = AtlasRequirementTracer().extract_requirements("Show a wave animation. Move the ball.")
    pool = _pool(metadata={"requirement_trace": reqs}, project_path=str(tmp_path))
    # No completed items, no changed files → missing → degrade
    rollup = compute_run_quality_rollup(pool, [_result(status="failed", changed_files=[])], project_path=str(tmp_path))
    assert rollup["requirement_coverage"]["no_implementation_evidence"] is True
    assert rollup["degraded"] is True
    assert "requirement_coverage_incomplete" in rollup["degrade_reasons"]


def test_completed_with_changes_is_partial_not_degraded(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><html><body><canvas></canvas>"
                                         "<script>requestAnimationFrame(()=>{});</script></body></html>", encoding="utf-8")
    reqs = AtlasRequirementTracer().extract_requirements("Show a wave animation here.")
    pool = _pool(metadata={"requirement_trace": reqs}, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(pool, [_result(status="completed", changed_files=["index.html"])], project_path=str(tmp_path))
    # partial, but not a hard degrade
    assert rollup["requirement_coverage"]["by_status"].get("partial") == len(reqs)
    assert "requirement_coverage_incomplete" not in rollup["degrade_reasons"]


# ── Integration check: disconnected user-facing module ───────────────────────

def test_disconnected_user_facing_module_degrades(tmp_path):
    (tmp_path / "index.html").write_text('<!doctype html><html><body>'
                                         '<script src="js/main.js"></script></body></html>', encoding="utf-8")
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "main.js").write_text("console.log('hi');", encoding="utf-8")
    (tmp_path / "js" / "renderer.js").write_text("export function render(){return 1;}", encoding="utf-8")
    pool = _pool(metadata={}, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(
        pool,
        [_result(status="completed", changed_files=["index.html", "js/main.js", "js/renderer.js"])],
        project_path=str(tmp_path),
    )
    # renderer.js is not referenced from index.html → disconnected user-facing module
    assert any(f.get("type") == "disconnected_module" for f in rollup["integration_warnings"])
    assert rollup["degraded"] is True
    assert "integration_failed" in rollup["degrade_reasons"]


# ── Placeholder-only implementation ───────────────────────────────────────────

def test_placeholder_only_implementation_degrades(tmp_path):
    (tmp_path / "logic.py").write_text("def draw():\n    # placeholder\n    pass\n", encoding="utf-8")
    pool = _pool(metadata={}, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(pool, [_result(status="completed", changed_files=["logic.py"])],
                                        project_path=str(tmp_path))
    assert rollup["degraded"] is True
    assert "placeholder_only" in rollup["degrade_reasons"]


def test_real_implementation_not_degraded(tmp_path):
    (tmp_path / "logic.py").write_text(
        "def draw(canvas):\n    canvas.fillRect(0,0,100,100)\n    canvas.stroke()\n    return True\n",
        encoding="utf-8",
    )
    pool = _pool(metadata={}, project_path=str(tmp_path))
    rollup = compute_run_quality_rollup(pool, [_result(status="completed", changed_files=["logic.py"])],
                                        project_path=str(tmp_path))
    assert "placeholder_only" not in rollup["degrade_reasons"]


# ── Test-only repair plan ─────────────────────────────────────────────────────

def test_test_only_repair_plan_degrades(tmp_path):
    pool = _pool(
        metadata={"repair_intent": {"is_repair": True, "primary_target_files": ["index.html"]}},
        items=[_item(item_type="implementation", target_files=["tests/test_x.py"])],
        project_path=str(tmp_path),
    )
    rollup = compute_run_quality_rollup(pool, [_result(status="completed", changed_files=["tests/test_x.py"])],
                                        project_path=str(tmp_path))
    assert rollup["repair_warning"] == "test_only_repair_plan"
    assert "test_only_repair_plan" in rollup["degrade_reasons"]


def test_repair_plan_touching_impl_not_degraded(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><html><body>fixed</body></html>", encoding="utf-8")
    pool = _pool(
        metadata={"repair_intent": {"is_repair": True, "primary_target_files": ["index.html"]}},
        items=[_item(item_type="implementation", target_files=["index.html"])],
        project_path=str(tmp_path),
    )
    rollup = compute_run_quality_rollup(pool, [_result(status="completed", changed_files=["index.html"])],
                                        project_path=str(tmp_path))
    assert rollup["repair_warning"] == ""
