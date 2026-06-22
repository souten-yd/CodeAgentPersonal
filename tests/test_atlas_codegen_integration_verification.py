"""Opt-in integration (結合) verification phase: run the whole project test suite after items apply."""
from __future__ import annotations

from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenResult
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService


def _svc(tmp_path):
    return AtlasAutonomousCodegenOrchestratorService(
        storage=None, journal=None, patch_proposal_service=None,
        multi_item_autopilot_service=None, data_root=tmp_path)


def _out():
    return AtlasAutonomousCodegenResult(pool_id="p", run_id="r", orchestrator_run_id="o", created_at="t")


def _autopilot(applied=1):
    return type("A", (), {"completed_count": applied, "applied_no_verification_count": 0})()


def test_integration_verification_passes_on_green_suite(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    out = _out()
    _svc(tmp_path)._run_integration_verification(out, str(proj), _autopilot())
    iv = out.metadata["integration_verification"]
    assert iv["status"] == "passed" and iv["test_file_count"] == 1


def test_integration_verification_resolves_subdir_imports(tmp_path):
    # A module + test under src/: the integration run must put src/ on sys.path (like per-item
    # verification) so "from calc import subtract" resolves — a bare whole-dir run would fail import.
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "calc.py").write_text("def subtract(a, b):\n    return a - b\n", encoding="utf-8")
    (proj / "src" / "test_calc.py").write_text(
        "from calc import subtract\n\ndef test_sub():\n    assert subtract(5, 3) == 2\n", encoding="utf-8")
    out = _out()
    _svc(tmp_path)._run_integration_verification(out, str(proj), _autopilot())
    assert out.metadata["integration_verification"]["status"] == "passed"


def test_integration_verification_resolves_src_package_imports(tmp_path):
    # Models often write `from src.mathops import ...` (src-prefixed). python -m pytest puts the
    # project root on sys.path so `src` resolves as a namespace package — bare pytest would not.
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "mathops.py").write_text("def multiply(a, b):\n    return a * b\n", encoding="utf-8")
    (proj / "src" / "test_mathops.py").write_text(
        "from src.mathops import multiply\n\ndef test_mul():\n    assert multiply(2, 3) == 6\n", encoding="utf-8")
    out = _out()
    _svc(tmp_path)._run_integration_verification(out, str(proj), _autopilot())
    assert out.metadata["integration_verification"]["status"] == "passed"


def test_integration_verification_fails_and_warns_on_red_suite(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    out = _out()
    _svc(tmp_path)._run_integration_verification(out, str(proj), _autopilot())
    assert out.metadata["integration_verification"]["status"] == "failed"
    assert "integration_verification_failed" in out.warnings


def test_integration_verification_no_tests_is_noop(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    out = _out()
    _svc(tmp_path)._run_integration_verification(out, str(proj), _autopilot())
    assert out.metadata["integration_verification"]["status"] == "no_tests"


def test_idempotent_no_change_detected(tmp_path):
    # A regeneration that finds "no_effective_change" (prior apply already made the edit) is NOT a
    # failure: the goal is met. Detected so the repair loop keeps the prior successful result.
    svc = _svc(tmp_path)
    idem = type("A", (), {"item_results": [
        {"status": "blocked", "reason": "verification_skipped",
         "safe_apply_result": {"status": "blocked", "block_reasons": ["no_effective_change"]}}]})()
    assert svc._is_idempotent_no_change(idem) is True
    # A genuine other-reason block is not idempotent.
    failed = type("A", (), {"item_results": [
        {"status": "failed", "reason": "verification_failed", "safe_apply_result": {"status": "applied"}}]})()
    assert svc._is_idempotent_no_change(failed) is False
    # No items -> not idempotent.
    assert svc._is_idempotent_no_change(type("A", (), {"item_results": []})()) is False
    # Real shape: no_effective_change nested in file-level results (not top-level reasons).
    nested = type("A", (), {"item_results": [
        {"status": "applied_no_verification", "reason": "verification_skipped",
         "safe_apply_result": {"status": "blocked",
                               "file_results": [{"path": "src/calc.py", "status": "blocked",
                                                 "reasons": ["no_effective_change"]}]}}]})()
    assert svc._is_idempotent_no_change(nested) is True
    # A hard block token (content_missing) disqualifies idempotency even if no_effective_change present.
    hard = type("A", (), {"item_results": [
        {"status": "blocked", "safe_apply_result": {"status": "blocked",
         "file_results": [{"reasons": ["no_effective_change"]}, {"reasons": ["content_missing"]}]}}]})()
    assert svc._is_idempotent_no_change(hard) is False


def test_integration_verification_skipped_when_nothing_applied(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    out = _out()
    _svc(tmp_path)._run_integration_verification(out, str(proj), _autopilot(applied=0))
    assert out.metadata["integration_verification"]["status"] == "skipped"
