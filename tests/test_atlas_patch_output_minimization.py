"""Phase 4: tier-gated output minimisation for patch generation.

A weak/standard model editing a large EXISTING file must emit surgical edits, not re-emit the whole
file (output-token minimisation). A frontier-tier model is exempt. The prompt steers it; a soft
warning surfaces violations without ever blocking (the content still applies).
"""
from __future__ import annotations

from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.model_forge.decomposition_policy import resolve_size_tier
from agent.model_forge.forge_service import ForgeService


def _payload(*, size_tier: str, current_lines: int, target_exists: bool = True) -> dict:
    content = "\n".join(f"line {i}" for i in range(current_lines))
    return {
        "pool_id": "p", "item_id": "i", "run_id": "r", "source_type": "plan_item",
        "size_tier": size_tier,
        "item": {
            "title": "t", "goal": "g", "description": "d",
            "target_files": ["app.py"], "original_target_files": ["app.py"],
            "target_file_exists": target_exists, "current_file_content": content,
        },
    }


def _svc() -> AtlasPatchProposalService:
    return AtlasPatchProposalService(journal=None, storage=None)


def test_warns_when_weak_tier_emits_full_content_for_large_existing_file():
    payload = _payload(size_tier="weak", current_lines=200)
    output = {"proposed_content": "rewritten whole file\n" * 5, "risk_level": "low", "target_files": ["app.py"]}
    proposal, _ = _svc()._build_proposal_from_output(output, payload)
    assert "full_content_emitted_for_minimal_edit_tier" in proposal.warnings


def test_no_warning_for_frontier_tier_full_content():
    payload = _payload(size_tier="frontier", current_lines=200)
    output = {"proposed_content": "rewritten whole file\n" * 5, "risk_level": "low", "target_files": ["app.py"]}
    proposal, _ = _svc()._build_proposal_from_output(output, payload)
    assert "full_content_emitted_for_minimal_edit_tier" not in proposal.warnings


def test_no_warning_when_edits_are_used():
    payload = _payload(size_tier="weak", current_lines=200)
    output = {
        "edits": [{"old_string": "line 5", "new_string": "line 5 changed"}],
        "risk_level": "low", "target_files": ["app.py"],
    }
    proposal, _ = _svc()._build_proposal_from_output(output, payload)
    assert "full_content_emitted_for_minimal_edit_tier" not in proposal.warnings


def test_no_warning_for_small_existing_file():
    payload = _payload(size_tier="weak", current_lines=20)
    output = {"proposed_content": "small file\n", "risk_level": "low", "target_files": ["app.py"]}
    proposal, _ = _svc()._build_proposal_from_output(output, payload)
    assert "full_content_emitted_for_minimal_edit_tier" not in proposal.warnings


def _capture_prompt(payload: dict) -> str:
    captured: dict = {}

    def fake_llm(system_prompt: str, user_prompt: str):
        captured["user"] = user_prompt
        return {"edits": [{"old_string": "line 5", "new_string": "line 5 changed"}],
                "risk_level": "low", "target_files": ["app.py"]}

    AtlasPatchProposalService(journal=None, storage=None, llm_json_fn=fake_llm).generate_proposal_with_llm(payload)
    return captured.get("user", "")


def test_prompt_includes_output_budget_for_weak_tier_large_existing_file():
    user = _capture_prompt(_payload(size_tier="weak", current_lines=200))
    assert "OUTPUT BUDGET" in user


def test_prompt_omits_output_budget_for_frontier_tier():
    user = _capture_prompt(_payload(size_tier="frontier", current_lines=200))
    assert "OUTPUT BUDGET" not in user


def test_prompt_omits_output_budget_for_small_existing_file():
    user = _capture_prompt(_payload(size_tier="weak", current_lines=20))
    assert "OUTPUT BUDGET" not in user


def test_resolve_size_tier_weak_from_profile(tmp_path):
    svc = ForgeService(tmp_path, env={})
    svc.profiles.record_observation(
        model_id="weak-coder", provider_id="local_openai",
        dimensions={"patch_generation": 0.5, "large_file_editing": 0.2},
    )
    tier = resolve_size_tier(data_root=str(tmp_path), metadata={"model_id": "weak-coder", "provider_id": "local_openai"}, env={})
    assert tier == "weak"


def test_resolve_size_tier_frontier_from_profile(tmp_path):
    svc = ForgeService(tmp_path, env={})
    svc.profiles.record_observation(
        model_id="strong-coder", provider_id="local_openai",
        dimensions={"patch_generation": 0.85, "large_file_editing": 0.85},
    )
    tier = resolve_size_tier(data_root=str(tmp_path), metadata={"model_id": "strong-coder", "provider_id": "local_openai"}, env={})
    assert tier == "frontier"
