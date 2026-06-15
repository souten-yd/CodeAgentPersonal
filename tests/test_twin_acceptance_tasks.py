"""Step 9 — representative acceptance tasks beyond add(a, b).

Each task runs end-to-end through the gated ActiveIntegrationOrchestrator with a
deterministic fake model and a REAL pytest verification in an isolated repo:
1. schema/persistence (save + reload round-trip),
2. backend/UI projection state (UI must mirror backend authority),
3. feature-flag judgment (behavior gated behind a flag).

Each includes a positive (accepted) and a negative (gate prevents unsafe acceptance) case.
"""
from __future__ import annotations

from pathlib import Path

from agent.git_steward.local_adapter import (
    create_baseline_commit, harden_ignore_policy, initialize_repository,
)
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.acceptance_harness import LocalAcceptanceHooks
from agent.twin_control_plane.active_integration import (
    ActiveIntegrationOrchestrator, PipelineMode, PipelineStatus,
)
from agent.twin_control_plane.contracts import (
    ExecutionPolicy, InstructionStyle, ModelCapabilityMode, TwinBrief,
    TwinInjectionLevel, default_hard_constraints,
)
from agent.twin_control_plane.real_llm_eval import ModelChatResponse
from agent.twin_control_plane.shadow_integration import TwinShadowMode, TwinShadowReport


def _policy():
    return ExecutionPolicy(policy_id="polT", route=ForgeRoute.DIRECT_PATCH, model_id="local",
                           instruction_style=InstructionStyle.CONSTRAINED_PATCH,
                           model_capability_mode=ModelCapabilityMode.STANDARD,
                           twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
                           required_gates=["SafeApplyBoundary", "RemotePublishApprovalGate"],
                           hard_constraints=default_hard_constraints())


def _brief(goal):
    return TwinBrief(brief_id="briefT", goal=goal, required_tests=["test://t"],
                     proof_requirements=["prove behavior"])


def _shadow():
    return TwinShadowReport(report_id="tw:t", mode=TwinShadowMode.SHADOW, plan_item_ref="t")


def _repo(path: Path, test_name: str, test_src: str) -> Path:
    initialize_repository(path)
    harden_ignore_policy(path)
    (path / test_name).write_text(test_src, encoding="utf-8")
    create_baseline_commit(path)
    return path


def _fixed_model(code: str):
    def chat(system, user):
        return ModelChatResponse(text=f"```python\n{code}```", available=True, latency_ms=1)
    return chat


def _run(repo, target, code, test_name, goal):
    harness = LocalAcceptanceHooks(
        chat=_fixed_model(code), repo_path=repo, target_file=target, task_prompt=goal,
        verify_command=["python", "-m", "pytest", "-q", test_name])
    orch = ActiveIntegrationOrchestrator(PipelineMode.ACTIVE, max_repair_attempts=2)
    return orch.run(policy=_policy(), brief=_brief(goal), hooks=harness.hooks(),
                    plan_item_ref="t", repo_path=str(repo), shadow_report=_shadow(),
                    before_twin_revision_id="tw_before")


# 1. schema / persistence round-trip ------------------------------------------------
PERSIST_TEST = (
    "import os\nfrom store import save, load\n\n"
    "def test_roundtrip(tmp_path):\n"
    "    p = str(tmp_path / 'd.txt')\n"
    "    save(p, 'hello')\n"
    "    assert load(p) == 'hello'\n"
)
PERSIST_OK = ("def save(path, value):\n    open(path, 'w').write(value)\n\n"
              "def load(path):\n    return open(path).read()\n")
PERSIST_BAD = ("def save(path, value):\n    pass\n\n"
               "def load(path):\n    return 'WRONG'\n")


def test_persistence_accepted(tmp_path):
    repo = _repo(tmp_path / "r", "test_store.py", PERSIST_TEST)
    res = _run(repo, "store.py", PERSIST_OK, "test_store.py", "implement save/load persistence")
    assert res.status == PipelineStatus.ACCEPTED
    assert res.patch_report.passed_evidence_refs


def test_persistence_negative_not_accepted(tmp_path):
    repo = _repo(tmp_path / "r", "test_store.py", PERSIST_TEST)
    res = _run(repo, "store.py", PERSIST_BAD, "test_store.py", "implement save/load persistence")
    # The gate prevents accepting a change whose real verification fails.
    assert res.status != PipelineStatus.ACCEPTED
    assert res.accepted is False


# 2. backend / UI projection state --------------------------------------------------
STATE_TEST = (
    "from workflow import can_execute\n\n"
    "def test_ui_mirrors_backend():\n"
    "    assert can_execute('ready') is True\n"
    "    assert can_execute('blocked') is False\n"
)
STATE_OK = "def can_execute(state):\n    return state == 'ready'\n"
STATE_BAD = "def can_execute(state):\n    return True  # UI exposes execute even when blocked\n"


def test_state_projection_accepted(tmp_path):
    repo = _repo(tmp_path / "r", "test_workflow.py", STATE_TEST)
    res = _run(repo, "workflow.py", STATE_OK, "test_workflow.py", "UI must mirror backend can_execute")
    assert res.status == PipelineStatus.ACCEPTED


def test_state_projection_negative_blocked_from_acceptance(tmp_path):
    repo = _repo(tmp_path / "r", "test_workflow.py", STATE_TEST)
    res = _run(repo, "workflow.py", STATE_BAD, "test_workflow.py", "UI must mirror backend can_execute")
    assert res.status != PipelineStatus.ACCEPTED


# 3. feature-flag judgment ----------------------------------------------------------
FLAG_TEST = (
    "from feature import behavior\n\n"
    "def test_flag_gated():\n"
    "    assert behavior(flag=False) == 'legacy'\n"
    "    assert behavior(flag=True) == 'new'\n"
)
FLAG_OK = "def behavior(flag):\n    return 'new' if flag else 'legacy'\n"
FLAG_BAD = "def behavior(flag):\n    return 'new'  # ignores the flag baseline\n"


def test_feature_flag_accepted(tmp_path):
    repo = _repo(tmp_path / "r", "test_feature.py", FLAG_TEST)
    res = _run(repo, "feature.py", FLAG_OK, "test_feature.py", "gate behavior behind a feature flag")
    assert res.status == PipelineStatus.ACCEPTED


def test_feature_flag_negative_not_accepted(tmp_path):
    repo = _repo(tmp_path / "r", "test_feature.py", FLAG_TEST)
    res = _run(repo, "feature.py", FLAG_BAD, "test_feature.py", "gate behavior behind a feature flag")
    assert res.status != PipelineStatus.ACCEPTED
    assert res.accepted is False
