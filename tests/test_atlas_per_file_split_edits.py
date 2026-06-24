from agent.atlas_patch_proposal_schema import AtlasPatchProposal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService


def test_per_file_split_preserves_child_edits_as_edits(monkeypatch):
    svc = AtlasPatchProposalService(journal=None, storage=None)

    child = AtlasPatchProposal(
        proposal_id="child",
        pool_id="pool",
        item_id="step_1",
        status="proposed",
        target_files=["src/app.js"],
        proposed_fix="replace a with b",
        metadata={"edits": [{"old_string": "a", "new_string": "b"}]},
    )
    monkeypatch.setattr(svc, "_generate_proposal_with_llm_core", lambda payload: child)
    monkeypatch.setattr(
        svc,
        "_single_file_input_payload",
        lambda payload, target: {"item": {"target_files": [target], "target_file_exists": True}},
    )

    payload = {
        "pool_id": "pool",
        "item_id": "step_1",
        "run_id": "run",
        "size_tier": "weak",
        "source_type": "plan_item",
        "item": {
            "title": "Edit app",
            "description": "replace a with b",
            "goal": "replace a with b",
            "target_files": ["src/app.js"],
            "target_file_exists": True,
        },
    }

    proposal = svc._generate_per_file_split(payload, ["src/app.js"])

    changes = proposal.metadata["file_changes"]
    assert changes == [
        {
            "path": "src/app.js",
            "action_type": "update",
            "content_mode": "edits",
            "edits": [{"old_string": "a", "new_string": "b"}],
        }
    ]
    assert "content" not in changes[0]
    assert "proposed_content" not in changes[0]
