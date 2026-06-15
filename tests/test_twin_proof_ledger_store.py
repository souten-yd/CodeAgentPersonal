"""Step 5 — durable Proof Ledger storage."""
from __future__ import annotations

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.contracts import (
    ExecutionPolicy, InstructionStyle, ModelCapabilityMode, TwinBrief,
    TwinInjectionLevel, default_hard_constraints,
)
from agent.twin_control_plane.patch_impact_gate import (
    PatchGateDecision, PatchImpactReport,
)
from agent.twin_control_plane.proof_ledger import (
    ProofLedgerStore, create_proof_ledger_entry,
)


def _policy():
    return ExecutionPolicy(policy_id="pol1", route=ForgeRoute.DIRECT_PATCH, model_id="m1",
                           instruction_style=InstructionStyle.CONSTRAINED_PATCH,
                           model_capability_mode=ModelCapabilityMode.STANDARD,
                           twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
                           hard_constraints=default_hard_constraints())


def _report(decision=PatchGateDecision.ACCEPTED):
    return PatchImpactReport(report_id="pir1", decision=decision,
                             accepted=decision == PatchGateDecision.ACCEPTED,
                             policy_id="pol1", brief_id="b1", base_ref="base", head_ref="head",
                             passed_evidence_refs=["v1"])


def _entry():
    return create_proof_ledger_entry(
        requirement_ref="req1", plan_item_ref="plan1", policy=_policy(),
        brief=TwinBrief(brief_id="b1"), patch_report=_report(),
        model_id="m1", provider_id="local")


def test_entry_persists_and_reloads(tmp_path):
    store = ProofLedgerStore(tmp_path / "ledger")
    store.append(_entry())
    reloaded = ProofLedgerStore(tmp_path / "ledger").load()
    assert len(reloaded.entries) == 1
    e = reloaded.entries[0]
    assert e.requirement_ref == "req1"
    assert e.accepted is True
    assert e.model_id == "m1" and e.provider_id == "local"
    assert "v1" in e.test_refs


def test_append_is_idempotent_by_entry_id(tmp_path):
    store = ProofLedgerStore(tmp_path / "ledger")
    store.append(_entry())
    store.append(_entry())  # same entry_id
    assert len(store.load().entries) == 1


def test_distinct_entries_accumulate(tmp_path):
    store = ProofLedgerStore(tmp_path / "ledger")
    store.append(_entry())
    blocked = create_proof_ledger_entry(
        requirement_ref="req2", plan_item_ref="plan2", policy=_policy(),
        brief=TwinBrief(brief_id="b1"), patch_report=_report(PatchGateDecision.BLOCKED))
    store.append(blocked)
    entries = store.load().entries
    assert len(entries) == 2
    assert {e.decision for e in entries} == {"accepted", "blocked"}
