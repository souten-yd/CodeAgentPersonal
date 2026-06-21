"""TA16: runtime generation policy reaches the patch proposal payload (E2E proof)."""
from __future__ import annotations

# Establish the model_forge import order first to avoid a pre-existing circular-import
# fragility (method_router <-> twin_control_plane.contracts) when collected in isolation.
import agent.model_forge.execution_policy  # noqa: F401

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _service(tmp_path, capture):
    def fake_llm(system_prompt, user_prompt):
        capture["system"] = system_prompt
        return {"target_files": ["a.py"], "proposed_content": "print(1)\n", "risk_level": "low"}

    return AtlasPatchProposalService(
        journal=AtlasJournal(tmp_path, workspace_id="default"),
        storage=AtlasPlanPoolStorage(tmp_path),
        llm_json_fn=fake_llm,
    )


def _payload(runtime_policy=None, twin_section=None):
    payload = {"item": {"item_id": "i1", "goal": "add feature", "target_files": ["a.py"],
                        "target_file_exists": False, "patch_task_kind": "implementation"}}
    if runtime_policy is not None:
        payload["runtime_policy"] = runtime_policy
    if twin_section is not None:
        payload["twin_control_section"] = twin_section
    return payload


def _policy(selection_mode, *, route="sliced_impact", method="patch_dsl_json", optimal=True):
    return {
        "selection_mode": selection_mode,
        "optimal_routing_enabled": optimal,
        "policy": {"policy_id": "execpol_test"},
        "fallback_recommendation": {
            "route": route, "method_variant": method,
            "method_fallbacks": ["edit_intent_list", "review_only"],
            "twin_injection_level": 3,
        },
    }


def test_runtime_policy_reaches_patch_proposal_payload(tmp_path):
    capture: dict = {}
    proposal = _service(tmp_path, capture).generate_proposal_with_llm(_payload(_policy("benchmark_optimized")))
    delivery = proposal.metadata["runtime_policy_delivery"]
    assert delivery["selection_mode"] == "benchmark_optimized"
    assert delivery["route"] == "sliced_impact"
    assert delivery["method_variant"] == "patch_dsl_json"
    assert delivery["twin_injection_level"] == 3
    assert delivery["production_routing_changed"] is False


def test_runtime_policy_prompt_contains_selected_instruction(tmp_path):
    capture: dict = {}
    proposal = _service(tmp_path, capture).generate_proposal_with_llm(
        _payload(_policy("benchmark_optimized"), twin_section="# Atlas Implementation Instruction\nSafe Apply boundary."))
    assert "Twin Control Plane" in capture["system"]
    assert "Safe Apply boundary" in capture["system"]
    assert proposal.metadata["runtime_policy_delivery"]["compiled_instruction_present"] is True


def test_off_policy_does_not_claim_benchmark(tmp_path):
    capture: dict = {}
    proposal = _service(tmp_path, capture).generate_proposal_with_llm(
        _payload(_policy("forge_optimal_routing_off", optimal=False)))
    delivery = proposal.metadata["runtime_policy_delivery"]
    assert delivery["selection_mode"] == "forge_optimal_routing_off"
    assert delivery["selection_mode"] != "benchmark_optimized"
    assert delivery["optimal_routing_enabled"] is False


def test_unbenchmarked_policy_recorded(tmp_path):
    capture: dict = {}
    proposal = _service(tmp_path, capture).generate_proposal_with_llm(
        _payload(_policy("unbenchmarked_default", route="patch_dsl")))
    assert proposal.metadata["runtime_policy_delivery"]["selection_mode"] == "unbenchmarked_default"
    assert proposal.metadata["runtime_policy_delivery"]["route"] == "patch_dsl"


def test_no_runtime_policy_means_no_delivery_record(tmp_path):
    capture: dict = {}
    proposal = _service(tmp_path, capture).generate_proposal_with_llm(_payload())
    assert "runtime_policy_delivery" not in (proposal.metadata or {})


def test_hints_from_evidence_carries_generation_policy():
    from agent.twin_control_plane.patch_injection import hints_from_evidence
    evidence = {
        "available": True, "mode": "active", "route": "patch_dsl",
        "instruction_style": "constrained_patch", "twin_injection_level": 3,
        "policy_id": "execpol_test", "compiled_instruction": "do the thing",
        "instruction_id": "instr1",
        "atlas_generation_policy": {"selection_mode": "benchmark_optimized"},
    }
    hints = hints_from_evidence(evidence)["twin_generation_hints"]
    assert hints["atlas_generation_policy"]["selection_mode"] == "benchmark_optimized"
