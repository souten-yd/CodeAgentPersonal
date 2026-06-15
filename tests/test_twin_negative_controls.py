"""Part C — genuine negative controls for the Twin mechanisms.

Each Twin mechanism is exercised on BOTH its should-pass and should-fail branch, so a
regression that makes the Twin a no-op (or that vacuously accepts) breaks these tests.
No model is used; all assertions are deterministic.
"""
from __future__ import annotations

from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.contract_sentinel import ContractFinding, ContractSentinelReport
from agent.twin_control_plane.pipeline_integration import (
    build_twin_pipeline_evidence, evaluate_twin_post_apply,
)


# --- Twin instruction injection: present in ACTIVE, ABSENT in OFF ------------------

def test_active_injects_instruction_but_off_must_not():
    active = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x",
                                          pool_id="p", changed_refs=["a.py"])
    off = build_twin_pipeline_evidence(mode=PipelineMode.OFF, requirement="x",
                                       pool_id="p", changed_refs=["a.py"])
    assert active["compiled_instruction"]                 # should-pass branch
    assert "compiled_instruction" not in off              # should-fail-if-noop branch


# --- post-apply gate: accepts on pass, never on unavailable, blocks on hard boundary --

def _post(**kw):
    base = dict(mode=PipelineMode.ACTIVE, blocking=True, requirement="x", pool_id="p",
                changed_files=["a.py"], before_twin_revision_id="b", after_twin_revision_id="a")
    base.update(kw)
    return evaluate_twin_post_apply(**base)


def test_passed_accepts_but_unavailable_must_not_accept():
    accepted = _post(verification=[{"evidence_id": "v", "status": "passed"}])
    assert accepted["accepted"] is True                   # should-pass
    unavailable = _post(verification=[{"evidence_id": "v", "status": "unavailable"}])
    assert unavailable["accepted"] is False               # must NOT vacuously accept
    failed = _post(verification=[{"evidence_id": "v", "status": "failed"}])
    assert failed["needs_repair"] is True and failed["accepted"] is False


def test_hard_boundary_must_block_but_clean_run_must_not():
    sentinel = ContractSentinelReport(
        report_id="cs", accepted=False, blocked=True,
        findings=[ContractFinding(finding_id="contract.safe_apply_bypass", severity="hard",
                                  status="blocked", message="bypass")])
    blocked = _post(verification=[{"evidence_id": "v", "status": "passed"}], contract_sentinel=sentinel)
    assert blocked["gate_blocked"] is True                # should block
    clean = _post(verification=[{"evidence_id": "v", "status": "passed"}])
    assert clean["gate_blocked"] is False                 # must NOT block a clean run


# --- capability profile: weak raises >= strong gates (strict where it matters) ------

def test_weak_profile_raises_more_gates_than_strong(tmp_path):
    from agent.model_forge.profile_store import ProfileStore

    def seed(dims):
        d = tmp_path / f"prof_{abs(hash(tuple(sorted(dims.items()))))}"
        ProfileStore(d / "profiles").record_observation(
            model_id="m", provider_id="local", dimensions=dims, evidence_refs=["e"])
        return str(d / "profiles")

    weak_dir = seed({"flag_reasoning": 0.2, "impact_analysis": 0.2,
                     "contract_preservation": 0.2, "test_generation": 0.2})
    strong_dir = seed({d: 0.9 for d in ("flag_reasoning", "impact_analysis",
                                        "contract_preservation", "test_generation")})
    weak = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x", pool_id="p",
                                        changed_refs=["a.py"], model_id="m", provider_id="local",
                                        profile_store_dir=weak_dir)
    strong = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x", pool_id="p",
                                          changed_refs=["a.py"], model_id="m", provider_id="local",
                                          profile_store_dir=strong_dir)
    # The weak model surfaces the FeatureFlagBaseline gate; the strong one does not.
    assert "FeatureFlagBaseline" in weak["required_gates"]
    assert "FeatureFlagBaseline" not in strong["required_gates"]
    assert len(weak["required_gates"]) > len(strong["required_gates"])


# --- impact: available populates BlastMap; unavailable recorded, never crashes -------

def test_impact_available_vs_unavailable_branches(tmp_path):
    from datetime import datetime, timezone
    from agent.project_twin.contracts import TwinDelta, TwinEdge, TwinNode
    from agent.project_twin.store import SqliteProjectTwinStore
    from agent.twin_control_plane.pipeline_integration import try_project_twin_impact

    # Unavailable branch.
    ev_unavail = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x",
                                              pool_id="p", changed_refs=["py://m.f"], impact=None)
    assert ev_unavail["impact"]["available"] is False
    assert ev_unavail["shadow_report"]["blast_map"] is None

    # Available branch.
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    store = SqliteProjectTwinStore(":memory:")
    store.apply_delta(TwinDelta(project_id="p", idempotency_key="s", trigger_type="workspace.changed",
        nodes=[TwinNode(node_id="n1", project_id="p", domain="structural", node_type="function",
                        canonical_ref="py://m.f", label="f", source_kind="git", source_ref="m.py",
                        derivation="deterministic_static", confidence=0.9, status="declared",
                        valid_from=now, created_at=now, updated_at=now)]))
    impact = try_project_twin_impact(project_id="p", changed_refs=["py://m.f"], store=store)
    ev_avail = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x",
                                            pool_id="p", changed_refs=["py://m.f"], impact=impact)
    assert ev_avail["impact"]["available"] is True
    assert ev_avail["shadow_report"]["blast_map"] is not None
    store.close()
