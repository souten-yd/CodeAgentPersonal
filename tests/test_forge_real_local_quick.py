"""PFG-30 — real local-model Quick preset run.

Runs a Quick-preset task through the real LocalOpenAICompatibleProvider against a live
local OpenAI-compatible server. This is REAL model evidence: it is skipped (not failed)
when no server is reachable, so CI without a model stays green, and when a server is
present it requires a genuine, contract-valid model response.

Point it at a server with FORGE_LOCAL_BASE_URL (default http://localhost:8080).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent.model_forge.preset_runner import LocalForgePresetRunner, PresetRunnerTask, write_evidence
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.stage_taxonomy import ForgeStage

BASE_URL = os.environ.get("FORGE_LOCAL_BASE_URL", "http://localhost:8080").rstrip("/")
MODEL_ID = os.environ.get("FORGE_LOCAL_MODEL", "").strip()

_QUICK_SYSTEM = "You are a precise coding assistant. Output only what is asked, no prose."
_QUICK_USER = (
    "Write a single Python function `add(a, b)` that returns a + b. "
    "Respond with ONLY the function definition."
)


@pytest.mark.real_model
def test_real_local_quick_preset_run():
    runner = LocalForgePresetRunner(base_url=BASE_URL, model_id=MODEL_ID, timeout_seconds=120.0)
    if not runner.probe():
        pytest.skip(f"no local model server reachable at {BASE_URL}: {runner.unavailable_reason}")

    run = runner.run(PresetRunnerTask(
        preset_id="quick_standard",
        stage=ForgeStage.PATCH_GENERATION,
        change_class=ChangeClass.MICRO,
        task_category="quick",
        system_prompt=_QUICK_SYSTEM,
        user_prompt=_QUICK_USER,
        output_contract="text",
        requested_route=ForgeRoute.MICRO_PATCH,
        requirement_coverage_ratio=1.0,
    ))

    # Real model evidence: a genuine, contract-valid response through the Forge runner.
    assert run.execution_result.contract_valid is True, run.execution_result.errors
    assert run.execution_result.errors == []
    assert run.execution_result.latency_ms > 0
    assert run.execution_result.usage.output_tokens > 0
    assert "def add" in run.raw_output
    assert run.evaluation.verdict == "eligible"

    evidence = run.evidence_payload(package="PFG-30")
    evidence.update(
        base_url=BASE_URL,
        legacy_direct_http_orchestration=False,
    )
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    write_evidence(out_dir / "pfg30_quick_local.json", evidence)
    print("PFG-30 evidence:", json.dumps(evidence, ensure_ascii=False))
