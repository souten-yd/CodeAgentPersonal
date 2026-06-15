"""TFG-13 / Package 12-13 — End-to-end acceptance closure tests.

- deterministic tests drive the harness with a fake model and a real temp Git repo to
  prove the full loop (generate -> Safe Apply -> real pytest verify -> Patch Impact Gate
  -> Proof Ledger) accepts a correct patch and repairs/exhausts on a wrong one;
- a ``real_model``-gated test runs the same loop against the live local model and records
  real LLM + real runtime acceptance evidence, skipping when no server is reachable.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from agent.git_steward.local_adapter import (
    create_baseline_commit,
    harden_ignore_policy,
    initialize_repository,
)
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.acceptance_harness import LocalAcceptanceHooks, extract_code_block
from agent.twin_control_plane.active_integration import (
    ActiveIntegrationOrchestrator,
    PipelineMode,
    PipelineStatus,
)
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinInjectionLevel,
    default_hard_constraints,
)
from agent.twin_control_plane.real_llm_eval import ModelChatResponse, build_local_model_chat
from agent.twin_control_plane.shadow_integration import TwinShadowMode, TwinShadowReport

BASE_URL = os.environ.get("FORGE_LOCAL_BASE_URL", "http://localhost:8080").rstrip("/")
MODEL_ID = os.environ.get("FORGE_LOCAL_MODEL", "").strip()

TASK_PROMPT = (
    "Implement a Python module `solution.py` with a function `add(a, b)` that returns "
    "the sum of a and b."
)
SOLUTION_TEST = (
    "from solution import add\n\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
    "    assert add(-1, 1) == 0\n"
)


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_id="policyACC", route=ForgeRoute.DIRECT_PATCH, model_id="local-coder",
        instruction_style=InstructionStyle.CONSTRAINED_PATCH,
        model_capability_mode=ModelCapabilityMode.STANDARD,
        twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
        required_gates=["SafeApplyBoundary", "RemotePublishApprovalGate"],
        hard_constraints=default_hard_constraints(),
    )


def _brief() -> TwinBrief:
    return TwinBrief(
        brief_id="briefACC", goal="implement add()", allowed_refs=["py://solution.add"],
        hard_constraints=[TwinConstraint(constraint_id="c1", text="Keep add(a, b) signature.")],
        required_tests=["test://test_solution"], proof_requirements=["prove add behavior"],
    )


def _shadow() -> TwinShadowReport:
    return TwinShadowReport(report_id="twin_shadow:acc", mode=TwinShadowMode.SHADOW,
                            plan_item_ref="acc")


def _init_repo(path: Path) -> Path:
    initialize_repository(path)
    harden_ignore_policy(path)
    (path / "test_solution.py").write_text(SOLUTION_TEST, encoding="utf-8")
    create_baseline_commit(path)
    return path


def _verify_cmd() -> list[str]:
    return ["python", "-m", "pytest", "-q", "test_solution.py"]


def test_extract_code_block_handles_fences_and_raw():
    fenced = "Here:\n```python\nx = 1\n```\nthanks"
    assert extract_code_block(fenced) == "x = 1\n"
    assert extract_code_block("def f():\n    return 1") == "def f():\n    return 1\n"


def test_end_to_end_accepts_correct_patch_with_fake_model(tmp_path):
    repo = _init_repo(tmp_path / "repo")

    def chat(system, user):
        # A correct implementation in a fenced block.
        return ModelChatResponse(text="```python\ndef add(a, b):\n    return a + b\n```",
                                 available=True, latency_ms=3)

    harness = LocalAcceptanceHooks(
        chat=chat, repo_path=repo, target_file="solution.py",
        task_prompt=TASK_PROMPT, verify_command=_verify_cmd(),
    )
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE, max_repair_attempts=2)
    result = orch.run(
        policy=_policy(), brief=_brief(), hooks=harness.hooks(),
        requirement_ref="req-add", plan_item_ref="acc", repo_path=str(repo),
        shadow_report=_shadow(), before_twin_revision_id="tw_before",
    )
    assert result.status == PipelineStatus.ACCEPTED
    assert result.accepted is True
    assert result.ledger_entry is not None and result.ledger_entry.accepted is True
    # The real test actually ran and passed against the applied file.
    assert (repo / "solution.py").read_text(encoding="utf-8").strip().startswith("def add")
    assert "verify_" in " ".join(result.patch_report.passed_evidence_refs)


def test_end_to_end_repairs_then_exhausts_on_wrong_patch(tmp_path):
    repo = _init_repo(tmp_path / "repo")

    def chat(system, user):
        # A wrong implementation: real pytest will fail -> needs_repair each attempt.
        return ModelChatResponse(text="```python\ndef add(a, b):\n    return a - b\n```",
                                 available=True, latency_ms=3)

    harness = LocalAcceptanceHooks(
        chat=chat, repo_path=repo, target_file="solution.py",
        task_prompt=TASK_PROMPT, verify_command=_verify_cmd(),
    )
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE, max_repair_attempts=2)
    result = orch.run(
        policy=_policy(), brief=_brief(), hooks=harness.hooks(),
        plan_item_ref="acc", repo_path=str(repo), shadow_report=_shadow(),
        before_twin_revision_id="tw_before",
    )
    assert result.status == PipelineStatus.EXHAUSTED
    assert result.accepted is False
    assert result.repair_reports  # real failing runtime evidence drove repair guidance
    assert "verification_failed" in " ".join(result.patch_report.repair_reasons)


@pytest.mark.real_model
def test_real_model_end_to_end_acceptance(tmp_path):
    chat = build_local_model_chat(base_url=BASE_URL, model_id=MODEL_ID, timeout_seconds=180.0)
    if not chat("You are terse.", "Reply with the single word READY.").available:
        pytest.skip(f"no local model server reachable at {BASE_URL}")

    repo = _init_repo(tmp_path / "repo")
    harness = LocalAcceptanceHooks(
        chat=chat, repo_path=repo, target_file="solution.py",
        task_prompt=TASK_PROMPT, verify_command=_verify_cmd(),
    )
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE, max_repair_attempts=3)
    result = orch.run(
        policy=_policy(), brief=_brief(), hooks=harness.hooks(),
        requirement_ref="req-add", plan_item_ref="acc", repo_path=str(repo),
        shadow_report=_shadow(), before_twin_revision_id="tw_before",
    )

    # Record real LLM + real runtime acceptance evidence.
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence = {
        "package": "TFG-13 acceptance closure",
        "model_id": MODEL_ID or "local",
        "status": result.status.value,
        "accepted": result.accepted,
        "branch": result.branch,
        "attempts": [a.model_dump(mode="json") for a in result.attempts],
        "patch_decision": result.patch_report.decision.value if result.patch_report else "",
        "passed_evidence": result.patch_report.passed_evidence_refs if result.patch_report else [],
        "failed_evidence": result.patch_report.failed_evidence_refs if result.patch_report else [],
        "ledger_accepted": bool(result.ledger_entry and result.ledger_entry.accepted),
        "model_transcript": harness.transcript,
        "final_solution": (repo / "solution.py").read_text(encoding="utf-8") if (repo / "solution.py").exists() else "",
    }
    (out_dir / "tfg_acceptance_closure_real.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    # The model was really driven and the loop produced a truthful end-to-end decision.
    assert harness.model_available is True
    assert result.status in {PipelineStatus.ACCEPTED, PipelineStatus.EXHAUSTED,
                             PipelineStatus.NEEDS_REPAIR, PipelineStatus.BLOCKED}
    # The branch was prepared locally; the remote was never touched.
    branches = subprocess.run(["git", "branch"], cwd=str(repo), text=True,
                              capture_output=True).stdout
    assert "atlas/acc" in branches
    # Whatever the verdict, evidence is internally consistent (no fabricated pass).
    if result.status == PipelineStatus.ACCEPTED:
        assert result.patch_report.passed_evidence_refs
        assert not result.patch_report.failed_evidence_refs
