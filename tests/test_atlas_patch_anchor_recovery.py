"""Anchor recovery for insertion edits that omit a placement anchor.

Root cause (observed live against the local model on a Space Invaders step that edits an existing
index.html): a weak model writes CORRECT new code but returns it as an insertion with an EMPTY
old_string and NO insert_after/insert_before anchor, so the code cannot be placed in the right
scope. Previously this either applied a broken end-of-file append or failed with content_missing
after burning all retries. The generator now detects this and re-prompts for ONLY the anchor,
echoing the code back — and refuses to apply an unplaceable append on the terminal attempt.

These tests are GENUINE: each mechanism has both a should-recover and a should-NOT-fire branch, so
a regression that makes the recovery a no-op (or that fires it on valid edits) breaks a test.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage

CURRENT_HTML = (
    "<!doctype html><html><body><canvas id=\"c\"></canvas><script>\n"
    "const game = {\n"
    "  bullets: [], enemies: [], score: 0,\n"
    "  update: function() {},\n"
    "  draw: function() {},\n"
    "};\n"
    "</script></body></html>\n"
)

EVIDENCE = {
    "implemented_symbols": ["game.checkCollision"],
    "behavioral_cases": ["bullet hitting an invader removes both"],
    "verification_cases": ["fire a bullet at an invader and observe both disappear"],
}


def _make_service(llm):
    tmp = Path(tempfile.mkdtemp()); ca = tmp / "ca"; ca.mkdir()
    return AtlasPatchProposalService(journal=AtlasJournal(ca, workspace_id="default"),
                                     storage=AtlasPlanPoolStorage(ca), llm_json_fn=llm)


def _payload(target="index.html", exists=True, content=CURRENT_HTML):
    item = {
        "title": "Implement Collision Detection",
        "goal": "Detect bullet-invader collisions, remove both, increment score",
        "description": "Add collision detection",
        "target_files": [target],
        "original_target_files": [target],
        "target_file_exists": exists,
        "current_file_content": content if exists else "",
        "requirement_ids": [],
        "patch_task_kind": "",
        "action_type": "",
    }
    return {
        "pool_id": "p", "item_id": "step_7", "run_id": "r1",
        "source_type": "plan_item", "requested_source_type": "plan_item",
        "root_goal": "Space Invaders game", "item": item, "all_requirements": [],
        "plan_file_manifest": [{"path": target}], "plan_sibling_files": {},
        "base_file_revisions": {target: "rev"},
        "debug_review": {"root_cause_category": "plan_item", "proposed_fix": "add collision detection"},
    }


def test_anchorless_insertion_recovers_on_next_attempt():
    """First attempt: new code with an empty old_string and NO anchor (unplaceable). Second attempt
    (after the anchor-recovery re-prompt): the SAME code with a valid insert_after anchor. The
    generator must retry, not give up, and the recovery prompt must carry the new code back."""
    calls: list[str] = []

    def llm(system, user):
        calls.append(user)
        if len(calls) == 1:
            return {"target_files": ["index.html"],
                    "edits": [{"old_string": "", "new_string": "  checkCollision: function() { return true; },\n"}],
                    **EVIDENCE}
        return {"target_files": ["index.html"],
                "edits": [{"old_string": "", "insert_after": "  update: function() {},",
                           "new_string": "  checkCollision: function() { return true; },\n"}],
                **EVIDENCE}

    svc = _make_service(llm)
    prop = svc.generate_proposal_with_llm(_payload())
    pg = (prop.metadata or {}).get("patch_generation") or {}

    assert len(calls) == 2, "should have re-prompted exactly once for the anchor"
    # The recovery re-prompt must carry the anchor_recovery section AND echo the new code back.
    assert "anchor_recovery" in calls[1]
    assert "checkCollision" in calls[1]
    assert pg.get("state") == "succeeded" and pg.get("outcome") == "success"
    assert pg.get("patch_content_available") is True
    edits = (prop.metadata or {}).get("edits") or []
    assert edits and edits[0].get("insert_after") == "  update: function() {},"


def test_anchorless_insertion_terminal_fails_not_broken_append():
    """If EVERY attempt returns an anchorless insertion, the generator fails honestly with
    edit_anchor_missing instead of applying an unplaceable end-of-file append."""
    calls: list[str] = []

    def llm(system, user):
        calls.append(user)
        return {"target_files": ["index.html"],
                "edits": [{"old_string": "", "new_string": "  checkCollision: function() {},\n"}],
                **EVIDENCE}

    svc = _make_service(llm)
    prop = svc.generate_proposal_with_llm(_payload())
    pg = (prop.metadata or {}).get("patch_generation") or {}

    assert len(calls) == svc.MAX_LLM_GENERATION_ATTEMPTS, "should exhaust the retry budget"
    assert pg.get("state") == "failed" and pg.get("outcome") == "failure"
    assert pg.get("reason_code") == "edit_anchor_missing"
    assert pg.get("patch_content_available") is False
    assert "edit_anchor_missing" in (prop.warnings or [])


def test_replacement_edit_does_not_trigger_recovery():
    """Negative control: a proper replacement edit (non-empty old_string) is placeable, so recovery
    must NOT fire — it succeeds on the first attempt."""
    calls: list[str] = []

    def llm(system, user):
        calls.append(user)
        return {"target_files": ["index.html"],
                "edits": [{"old_string": "  update: function() {},",
                           "new_string": "  update: function() {},\n  checkCollision: function() {},"}],
                **EVIDENCE}

    svc = _make_service(llm)
    prop = svc.generate_proposal_with_llm(_payload())
    pg = (prop.metadata or {}).get("patch_generation") or {}

    assert len(calls) == 1, "a placeable replacement edit must not be re-prompted"
    assert pg.get("state") == "succeeded"
    strategies = [h.get("strategy") for h in (pg.get("history") or [])]
    assert "anchor_recovery" not in strategies


def test_anchored_insertion_does_not_trigger_recovery():
    """Negative control: an insertion that ALREADY has an insert_after anchor is placeable."""
    calls: list[str] = []

    def llm(system, user):
        calls.append(user)
        return {"target_files": ["index.html"],
                "edits": [{"old_string": "", "insert_after": "  update: function() {},",
                           "new_string": "  checkCollision: function() {},\n"}],
                **EVIDENCE}

    svc = _make_service(llm)
    prop = svc.generate_proposal_with_llm(_payload())
    pg = (prop.metadata or {}).get("patch_generation") or {}
    assert len(calls) == 1
    assert pg.get("state") == "succeeded"


def test_plaintext_target_allows_anchorless_append():
    """Negative control: a plain-text target (notes.txt) can legitimately take a trailing append, so
    an anchorless insertion there must NOT be treated as a placement defect."""
    calls: list[str] = []

    def llm(system, user):
        calls.append(user)
        return {"target_files": ["notes.txt"],
                "edits": [{"old_string": "", "new_string": "appended line\n"}],
                **EVIDENCE}

    svc = _make_service(llm)
    prop = svc.generate_proposal_with_llm(_payload(target="notes.txt", content="existing notes\n"))
    pg = (prop.metadata or {}).get("patch_generation") or {}
    assert len(calls) == 1, "plain-text append must not be re-prompted for an anchor"
    assert pg.get("state") == "succeeded"


def test_recovery_helpers_direct():
    svc = _make_service(lambda s, u: {})
    # structured existing single target -> the file; multi/new/plain -> "".
    assert svc._existing_structured_target(_payload()) == "index.html"
    assert svc._existing_structured_target(_payload(exists=False)) == ""
    assert svc._existing_structured_target(_payload(target="notes.txt")) == ""

    class _P:  # minimal proposal stand-in
        def __init__(self, meta, diff=""):
            self.metadata = meta
            self.unified_diff_preview = diff

    anchorless = _P({"edits": [{"old_string": "", "new_string": "x"}]})
    assert svc._anchorless_insertion_new_code(anchorless) == ["x"]
    assert svc._has_placeable_content(anchorless) is False

    anchored = _P({"edits": [{"old_string": "", "insert_after": "a", "new_string": "x"}]})
    assert svc._anchorless_insertion_new_code(anchored) == []
    assert svc._has_placeable_content(anchored) is True

    replacement = _P({"edits": [{"old_string": "a", "new_string": "b"}]})
    assert svc._has_placeable_content(replacement) is True

    full = _P({"proposed_content": "whole file"})
    assert svc._has_placeable_content(full) is True
