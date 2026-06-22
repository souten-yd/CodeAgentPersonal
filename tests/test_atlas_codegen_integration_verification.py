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


def test_integration_verification_skipped_when_nothing_applied(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    out = _out()
    _svc(tmp_path)._run_integration_verification(out, str(proj), _autopilot(applied=0))
    assert out.metadata["integration_verification"]["status"] == "skipped"
