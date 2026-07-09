from agent.atlas_patch_proposal_schema import AtlasPatchProposal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService


def _multi_file_payload(target_files, *, existing_content: dict[str, str]) -> dict:
    return {
        "pool_id": "pool",
        "item_id": "step_1",
        "run_id": "run",
        "source_type": "plan_item",
        "item": {"title": "t", "description": "d", "goal": "g", "target_files": target_files},
        "current_target_contents": {
            path: {"content": existing_content.get(path, ""), "exists": bool(existing_content.get(path))}
            for path in target_files
        },
    }


def test_per_file_split_targets_splits_pure_multi_file_create():
    # None of the targets exist yet (a brand-new multi-file CREATE step): the combined existing
    # content is 0, which the overflow heuristic alone would treat as "cheap enough together" — but
    # this is exactly the case a single generation call unreliably completes (see
    # multi_file_content_missing failures). Must split regardless of size.
    svc = AtlasPatchProposalService(journal=None, storage=None)
    payload = _multi_file_payload(["index.html", "style.css"], existing_content={})

    assert svc._per_file_split_targets(payload) == ["index.html", "style.css"]


def test_per_file_split_targets_keeps_single_shot_for_small_existing_edit():
    # Two small EXISTING files being edited together: unchanged behavior, still single-shot.
    svc = AtlasPatchProposalService(journal=None, storage=None)
    payload = _multi_file_payload(
        ["a.py", "b.py"], existing_content={"a.py": "x" * 100, "b.py": "y" * 100}
    )

    assert svc._per_file_split_targets(payload) == []


def test_per_file_split_targets_splits_large_existing_edit():
    # Existing behavior preserved: large combined existing content still splits to avoid overflow.
    svc = AtlasPatchProposalService(journal=None, storage=None)
    payload = _multi_file_payload(
        ["a.py", "b.py"],
        existing_content={"a.py": "x" * 6000, "b.py": "y" * 6000},
    )

    assert svc._per_file_split_targets(payload) == ["a.py", "b.py"]


def test_per_file_split_recovers_content_via_proposed_content_field(monkeypatch):
    # The model often answers with a whole-file "proposed_content" rather than a file_changes
    # entry. The synthesized change MUST use keys _normalize_file_changes actually keeps
    # ("proposed_content"/"action_type") — using "content"/"change_type" silently drops the
    # recovered content during normalization, shipping an empty change.
    svc = AtlasPatchProposalService(journal=None, storage=None)

    child = AtlasPatchProposal(
        proposal_id="child", pool_id="pool", item_id="step_1", status="proposed",
        target_files=["style.css"], proposed_fix="style the page",
        metadata={"proposed_content": "body { margin: 0; }"},
    )
    monkeypatch.setattr(svc, "_generate_proposal_with_llm_core", lambda payload: child)
    monkeypatch.setattr(
        svc,
        "_single_file_input_payload",
        lambda payload, target: {"item": {"target_files": [target], "target_file_exists": False}},
    )

    payload = _multi_file_payload(["index.html", "style.css"], existing_content={})
    proposal = svc._generate_per_file_split(payload, ["style.css"])

    changes = proposal.metadata["file_changes"]
    assert changes == [{
        "path": "style.css",
        "action_type": "create",
        "proposed_content": "body { margin: 0; }",
        "content_mode": "full_content",
    }]


def test_per_file_split_target_dedicated_pass_overrides_earlier_byproduct(monkeypatch):
    # index.html's generation pass incidentally sketches style.css too (a "byproduct"). style.css's
    # OWN dedicated pass later produces real content. The merged proposal must keep style.css's own
    # content, not the earlier byproduct placeholder from index.html's pass.
    svc = AtlasPatchProposalService(journal=None, storage=None)

    def fake_generate(payload: dict) -> AtlasPatchProposal:
        target = payload["item"]["target_files"][0]
        if target == "index.html":
            return AtlasPatchProposal(
                proposal_id="p1", pool_id="pool", item_id="step_1", status="proposed",
                target_files=["index.html"],
                metadata={"file_changes": [
                    {"path": "index.html", "action_type": "create", "proposed_content": "<html>real</html>"},
                    {"path": "style.css", "action_type": "create", "proposed_content": "/* placeholder */"},
                ]},
            )
        return AtlasPatchProposal(
            proposal_id="p2", pool_id="pool", item_id="step_1", status="proposed",
            target_files=["style.css"],
            metadata={"file_changes": [
                {"path": "style.css", "action_type": "create", "proposed_content": "body { color: red; }"},
            ]},
        )

    monkeypatch.setattr(svc, "_generate_proposal_with_llm_core", fake_generate)
    monkeypatch.setattr(
        svc,
        "_single_file_input_payload",
        lambda payload, target: {"item": {"target_files": [target], "target_file_exists": False}},
    )

    payload = _multi_file_payload(["index.html", "style.css"], existing_content={})
    proposal = svc._generate_per_file_split(payload, ["index.html", "style.css"])

    changes = {c["path"]: c for c in proposal.metadata["file_changes"]}
    assert changes["style.css"]["proposed_content"] == "body { color: red; }"
    assert changes["index.html"]["proposed_content"] == "<html>real</html>"


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
