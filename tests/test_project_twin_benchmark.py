"""PDT-14 end-to-end benchmark and rollout-flag tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.project_twin.benchmark import run_benchmark
from agent.project_twin.feature_flag import RolloutConfig, is_twin_enabled


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    _write(tmp_path, "m.py", "def helper():\n    return 1\ndef caller():\n    return helper()\n")
    _write(tmp_path, "api.py",
           "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/items')\ndef list_items():\n    open('f').read()\n")
    _write(tmp_path, "test_m.py", "def test_helper():\n    assert helper() == 1\n")
    _write(tmp_path, "ui.js", "btn.addEventListener('click', () => { fetch('/items'); });\n")
    _write(tmp_path, "skills/refactor/SKILL.md",
           "---\nname: refactor-helper\nversion: 1.0.0\nkeywords: refactor\nphases: planning\nallowed_paths: /etc\n---\nrefactor guide\n")
    return tmp_path


def test_all_benchmark_scenarios_pass(project: Path):
    report = run_benchmark(str(project), skills_dir=str(project / "skills"))
    failed = [r.scenario for r in report.results if not r.passed]
    assert not failed, f"failing scenarios: {failed}; details={[(r.scenario, r.evidence) for r in report.results]}"
    # all 14 documented scenarios are present
    assert len(report.results) == 14
    assert report.passed


# --- rollout flag (disabled by default; rollback path) -----------------------

def test_twin_disabled_by_default():
    assert is_twin_enabled({}) is False
    cfg = RolloutConfig.from_env({})
    assert cfg.enabled is False
    assert cfg.phase_active("planning") is False  # off => no augmentation (rollback path)


def test_twin_enabled_all_phases():
    cfg = RolloutConfig.from_env({"CODEAGENT_PROJECT_TWIN_ENABLED": "true"})
    assert cfg.enabled is True
    assert cfg.phase_active("planning") is True
    assert cfg.phase_active("generation") is True


def test_twin_enabled_specific_phase_only():
    cfg = RolloutConfig.from_env({"CODEAGENT_PROJECT_TWIN_ENABLED": "1", "CODEAGENT_PROJECT_TWIN_PHASES": "planning"})
    assert cfg.phase_active("planning") is True
    assert cfg.phase_active("generation") is False


def test_shadow_mode_never_augments_but_computes():
    cfg = RolloutConfig.from_env({"CODEAGENT_PROJECT_TWIN_ENABLED": "yes", "CODEAGENT_PROJECT_TWIN_SHADOW": "on"})
    assert cfg.phase_active("planning") is False     # shadow does not apply
    assert cfg.shadow_active("planning") is True     # but is computed for comparison
