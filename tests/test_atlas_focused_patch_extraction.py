"""Focused patch-content extraction (weak-model recovery).

When the rich patch schema yields no Git-representable change (a weak local model returns the
describe-fields but skips edits/proposed_content), the service recovers by asking for the change
with a minimal schema in tiers:
  1. old_string/new_string surgical edit
  2. line-range op on a numbered view (file + start/end + change type + content), applied
     deterministically — the operator-proposed method, made robust here
  3. full proposed_content
"""
from agent.atlas_patch_proposal_schema import AtlasPatchProposal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService


def _svc(fake_fn=None):
    return AtlasPatchProposalService(journal=None, storage=None, llm_json_fn=fake_fn)


def _proposal():
    return AtlasPatchProposal(proposal_id="p1", pool_id="pool", item_id="step_1",
                              proposed_fix="fix add to return a + b")


# ----- line-range deterministic apply (operator's method) -----

def test_apply_line_range_replace():
    cur = "def add(a, b):\n    return a - b\n"
    out = AtlasPatchProposalService._apply_line_range_op(
        cur, {"change_type": "replace", "start_line": 2, "end_line": 2, "new_content": "    return a + b"})
    assert out == "def add(a, b):\n    return a + b\n"


def test_apply_line_range_insert_after():
    out = AtlasPatchProposalService._apply_line_range_op(
        "a\nb\n", {"change_type": "insert_after", "start_line": 1, "end_line": 1, "new_content": "x"})
    assert out == "a\nx\nb\n"


def test_apply_line_range_delete():
    out = AtlasPatchProposalService._apply_line_range_op(
        "a\nb\nc\n", {"change_type": "delete", "start_line": 2, "end_line": 2, "new_content": ""})
    assert out == "a\nc\n"


def test_apply_line_range_out_of_range_returns_none():
    assert AtlasPatchProposalService._apply_line_range_op(
        "a\n", {"change_type": "replace", "start_line": 5, "end_line": 6, "new_content": "x"}) is None


def test_apply_line_range_noop_returns_none():
    assert AtlasPatchProposalService._apply_line_range_op(
        "a\n", {"change_type": "replace", "start_line": 1, "end_line": 1, "new_content": "a"}) is None


# ----- focused extraction tiers -----

def test_tier1_old_string_edit():
    def fake(system, user):
        return {"old_string": "    return a - b", "new_string": "    return a + b"}
    svc = _svc(fake)
    payload = {"run_id": "r", "root_goal": "fix",
               "item": {"target_files": ["calc.py"], "target_file_exists": True,
                        "current_file_content": "def add(a, b):\n    return a - b\n"}}
    p = _proposal()
    assert svc._focused_edit_extraction(payload, p) is True
    assert p.metadata["edits"] == [{"old_string": "    return a - b", "new_string": "    return a + b"}]
    assert p.metadata["patch_content_available"] is True
    assert p.metadata["self_review"]["status"] == "passed"
    assert p.metadata["semantic_validation"]["status"] == "passed"
    assert p.metadata["focused_extraction"]["mode"] == "edits"


def test_tier2_line_range_when_anchor_fails():
    seq = [
        {"old_string": "nonexistent", "new_string": "x"},  # tier 1 anchor miss
        {"change_type": "replace", "start_line": 2, "end_line": 2, "new_content": "    return a + b"},  # tier 2
    ]
    svc = _svc(lambda system, user: seq.pop(0))
    payload = {"run_id": "r",
               "item": {"target_files": ["calc.py"], "target_file_exists": True,
                        "current_file_content": "def add(a, b):\n    return a - b\n"}}
    p = _proposal()
    assert svc._focused_edit_extraction(payload, p) is True
    assert p.metadata["proposed_content"] == "def add(a, b):\n    return a + b\n"
    assert p.metadata["focused_extraction"]["mode"] == "line_range"


def test_new_file_uses_proposed_content():
    svc = _svc(lambda system, user: {"proposed_content": "print('hi')\n"})
    payload = {"run_id": "r",
               "item": {"target_files": ["new.py"], "target_file_exists": False, "current_file_content": ""}}
    p = _proposal()
    assert svc._focused_edit_extraction(payload, p) is True
    assert p.metadata["proposed_content"] == "print('hi')\n"
    assert p.target_files == ["new.py"]


def test_multi_target_is_skipped():
    svc = _svc(lambda system, user: {"old_string": "x", "new_string": "y"})
    payload = {"item": {"target_files": ["a.py", "b.py"], "target_file_exists": True, "current_file_content": "x\n"}}
    assert svc._focused_edit_extraction(payload, _proposal()) is False


def test_no_llm_returns_false():
    assert _svc(None)._focused_edit_extraction(
        {"item": {"target_files": ["a.py"]}}, _proposal()) is False


# ----- eligibility gate: never override a quality rejection -----

def _no_content_proposal(**meta):
    p = _proposal()
    p.warnings = ["llm_no_patch_content_generated", "plan_item_patch_content_missing"]
    p.metadata.update(meta)
    return p


def test_eligible_when_no_patch_content_and_no_quality_rejection():
    p = _no_content_proposal(semantic_validation={"status": "failed", "reasons": ["satisfied_requirement_ids_missing", "remaining_todos_present"]})
    assert AtlasPatchProposalService._focused_extraction_eligible(p) is True


def test_not_eligible_without_no_patch_content_signal():
    p = _proposal()
    p.warnings = ["self_review_findings_unresolved"]
    assert AtlasPatchProposalService._focused_extraction_eligible(p) is False


def test_not_eligible_when_self_review_failed():
    p = _no_content_proposal(self_review={"status": "failed", "findings": [{"type": "stub"}]})
    assert AtlasPatchProposalService._focused_extraction_eligible(p) is False


def test_not_eligible_when_self_review_findings_unresolved_warning():
    p = _no_content_proposal()
    p.warnings.append("self_review_findings_unresolved")
    assert AtlasPatchProposalService._focused_extraction_eligible(p) is False


def test_not_eligible_when_content_quality_semantic_reason():
    p = _no_content_proposal(semantic_validation={"status": "failed", "reasons": ["content_too_large"]})
    assert AtlasPatchProposalService._focused_extraction_eligible(p) is False
