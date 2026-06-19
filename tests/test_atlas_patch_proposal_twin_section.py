"""Step 3 — the compiled Twin instruction reaches the real generation prompt."""
from __future__ import annotations

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


def _payload(twin_section=None):
    payload = {"item": {"item_id": "i1", "goal": "add feature", "target_files": ["a.py"],
                        "target_file_exists": False, "patch_task_kind": "implementation"}}
    if twin_section is not None:
        payload["twin_control_section"] = twin_section
    return payload


def test_twin_section_reaches_generation_system_prompt(tmp_path):
    capture: dict = {}
    svc = _service(tmp_path, capture)
    try:
        svc.generate_proposal_with_llm(_payload("# Atlas Implementation Instruction\nSafe Apply boundary; remote requires approval."))
    except Exception:
        pass
    assert "system" in capture
    assert "Twin Control Plane" in capture["system"]
    assert "Safe Apply boundary" in capture["system"]


def test_no_twin_section_leaves_legacy_prompt_unchanged(tmp_path):
    capture: dict = {}
    svc = _service(tmp_path, capture)
    try:
        svc.generate_proposal_with_llm(_payload(None))
    except Exception:
        pass
    assert "system" in capture
    assert "Twin Control Plane" not in capture["system"]
    assert "advisory patch proposals only" in capture["system"]
