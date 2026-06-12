"""PFG-32 — real Repair preset run.

A reproducible failing fixture (a buggy function + a failing check) is repaired by the
real local model. Repair success is decided by RE-RUNNING the check on the model's output
in a subprocess — never by the model's claim. The repair is applied only to a throwaway
fixture under tmp_path (no real workspace mutation, no Safe Apply bypass).

Skips when no local model server is reachable (FORGE_LOCAL_BASE_URL, default :8080).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from agent.model_forge.preset_runner import LocalForgePresetRunner, PresetRunnerTask, write_evidence
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.stage_taxonomy import ForgeStage

BASE_URL = os.environ.get("FORGE_LOCAL_BASE_URL", "http://localhost:8080").rstrip("/")
MODEL_ID = os.environ.get("FORGE_LOCAL_MODEL", "").strip()

# Reproducible failing fixture: subtract instead of add.
_BUGGY = "def add(a, b):\n    return a - b\n"
_CHECK = (
    "from solution import add\n"
    "assert add(2, 3) == 5, 'add(2,3) should be 5'\n"
    "assert add(10, 5) == 15, 'add(10,5) should be 15'\n"
    "print('REPAIR_OK')\n"
)

_SYSTEM = "You are a debugging assistant. Output only the corrected Python function, no prose."
_USER = (
    "This function is supposed to return the sum of a and b, but a test fails:\n\n"
    f"{_BUGGY}\n"
    "Failing test:\n"
    "assert add(2, 3) == 5\n\n"
    "Return ONLY the corrected `add` function definition."
)


def _extract_function(text: str) -> str:
    fenced = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    code = fenced.group(1) if fenced else text
    # Keep from the first 'def add' onward.
    idx = code.find("def add")
    return (code[idx:] if idx >= 0 else code).strip() + "\n"


def _run_check(work: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(work / "check.py")], cwd=str(work),
        capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
    )
    return proc.returncode == 0 and "REPAIR_OK" in (proc.stdout or ""), (proc.stdout or "") + (proc.stderr or "")


@pytest.mark.real_model
def test_real_repair_is_verified_by_rerunning_the_check(tmp_path):
    runner = LocalForgePresetRunner(base_url=BASE_URL, model_id=MODEL_ID, timeout_seconds=180.0)
    if not runner.probe():
        pytest.skip(f"no local model server reachable at {BASE_URL}: {runner.unavailable_reason}")

    work = tmp_path / "repair_fixture"
    work.mkdir()
    (work / "solution.py").write_text(_BUGGY, encoding="utf-8")
    (work / "check.py").write_text(_CHECK, encoding="utf-8")

    # The fixture really fails before repair.
    passed_before, _ = _run_check(work)
    assert passed_before is False, "fixture should fail before repair"

    # Real model produces a repair candidate through the Forge runner.
    run = runner.run(PresetRunnerTask(
        preset_id="repair_standard",
        stage=ForgeStage.REPAIR,
        change_class=ChangeClass.SMALL,
        task_category="repair",
        system_prompt=_SYSTEM,
        user_prompt=_USER,
        output_contract="text",
        requirement_coverage_ratio=1.0,
    ))
    assert run.execution_result.contract_valid is True, run.execution_result.errors
    fixed = _extract_function(run.raw_output)
    assert "def add" in fixed

    # Apply the candidate to the throwaway fixture and RE-RUN the check (runtime verdict).
    (work / "solution.py").write_text(fixed, encoding="utf-8")
    passed_after, output = _run_check(work)

    evidence = run.evidence_payload(package="PFG-32")
    evidence.update(
        passed_before=passed_before,
        passed_after=passed_after,
        runtime_verdict="passed" if passed_after else "failed",
        fixed_excerpt=fixed[:200],
        check_output=output.strip()[:200],
        legacy_direct_http_orchestration=False,
    )
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    write_evidence(out_dir / "pfg32_repair_local.json", evidence)
    print("PFG-32 evidence:", json.dumps(evidence, ensure_ascii=False))

    # Repair success is decided by the re-run, not the model's claim.
    assert passed_after is True, f"repair not verified by runtime: {output[:300]}"
