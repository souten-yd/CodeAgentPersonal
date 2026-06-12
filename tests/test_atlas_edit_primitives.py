"""Pillar B: partial-edit primitives wired into the autopilot's safe-apply executor.

Covers surgical string edits (old->new, unique), append, hunk-aware unified diff (preserving lines
outside the hunk), no-op detection, and the full proposal->executor edits flow.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _apply(ws, target, metadata, seed=None):
    if seed is not None:
        (ws / target).write_text(seed, encoding="utf-8")
    item = AtlasPlanItem(item_id="i", pool_id="p", title="t", goal="g", item_type="implementation",
                         status="ready", risk_level="low", target_files=[target], metadata=metadata)
    pool = AtlasPlanPool(pool_id="p", root_goal="g", project_path=str(ws), items=[item])
    return AtlasFileSafeApplyExecutor(workspace_root=ws).apply_plan_item_safe(item=item, pool=pool)


def test_string_edits_apply_and_preserve_surroundings():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "a.py", {"action_type": "update", "edits": [{"old_string": "return 1", "new_string": "return 100"}]},
               seed="def foo():\n    return 1\n\ndef bar():\n    return 2\n")
    assert r["status"] == "applied" and "(edits)" in r["summary"]
    final = (ws / "a.py").read_text()
    assert "return 100" in final and "def bar" in final and "return 1\n" not in final


def test_string_edit_non_unique_is_blocked():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "b.py", {"action_type": "update", "edits": [{"old_string": "x=1", "new_string": "x=2"}]},
               seed="x=1\nx=1\n")
    assert r["status"] == "blocked" and "edit_not_applicable" in r["reasons"]


def test_html_tag_gap_whitespace_edit_applies_once():
    ws = Path(tempfile.mkdtemp())
    r = _apply(
        ws,
        "index.html",
        {
            "action_type": "update",
            "edits": [
                {
                    "old_string": "<h1>Atlas Existing Baseline</h1>\n<p>Status: pending</p>",
                    "new_string": "<h1>Atlas Existing Project Ready</h1>\n<p>Status: ready</p>",
                }
            ],
        },
        seed="<!doctype html><html><body><h1>Atlas Existing Baseline</h1><p>Status: pending</p></body></html>\n",
    )

    assert r["status"] == "applied"
    final = (ws / "index.html").read_text()
    assert "Atlas Existing Project Ready" in final
    assert "Status: ready" in final


def test_edits_require_existing_file():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "missing.py", {"action_type": "update", "edits": [{"old_string": "a", "new_string": "b"}]})
    assert r["status"] == "blocked" and "edits_require_existing_file" in r["reasons"]


def test_append_to_existing_file():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "c.txt", {"action_type": "update", "append_content": "line2\n"}, seed="line1\n")
    assert r["status"] == "applied" and "(append)" in r["summary"]
    assert (ws / "c.txt").read_text() == "line1\nline2\n"


def test_insert_after_anchor_adds_new_code_in_scope():
    ws = Path(tempfile.mkdtemp())
    seed = "<script>\n  function shoot() {}\n</script>\n"
    r = _apply(ws, "index.html", {"action_type": "update", "edits": [
        {"old_string": "", "insert_after": "  function shoot() {}",
         "new_string": "  function moveEnemies() {}"},
    ]}, seed=seed)
    assert r["status"] == "applied" and "(edits)" in r["summary"]
    final = (ws / "index.html").read_text()
    # New function landed inside <script>, right after the anchor, not after </script>.
    assert final.index("moveEnemies") < final.index("</script>")
    assert "function shoot() {}\n  function moveEnemies() {}" in final


def test_insert_before_anchor():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "a.py", {"action_type": "update", "edits": [
        {"old_string": "", "insert_before": "def bar():", "new_string": "def baz():\n    return 3\n"},
    ]}, seed="def foo():\n    return 1\n\ndef bar():\n    return 2\n")
    assert r["status"] == "applied"
    final = (ws / "a.py").read_text()
    assert final.index("def baz") < final.index("def bar")


def test_insert_after_non_unique_anchor_blocked():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "b.py", {"action_type": "update", "edits": [
        {"old_string": "", "insert_after": "pass", "new_string": "x = 1\n"},
    ]}, seed="def a():\n    pass\ndef b():\n    pass\n")
    assert r["status"] == "blocked" and "edit_not_applicable" in r["reasons"]


def test_empty_old_string_without_anchor_appends():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "c.py", {"action_type": "update", "edits": [
        {"old_string": "", "new_string": "# trailing note\n"},
    ]}, seed="x = 1\n")
    assert r["status"] == "applied"
    assert (ws / "c.py").read_text() == "x = 1\n# trailing note\n"


def test_hunk_aware_diff_preserves_unrelated_lines():
    ws = Path(tempfile.mkdtemp())
    diff = "@@ -2,1 +2,1 @@\n-b\n+B\n"
    r = _apply(ws, "d.py", {"action_type": "update", "unified_diff_preview": diff}, seed="a\nb\nc\nd\n")
    assert r["status"] == "applied" and "(unified_diff)" in r["summary"]
    assert (ws / "d.py").read_text() == "a\nB\nc\nd\n"


def test_no_effective_change_blocked():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "e.txt", {"action_type": "update", "proposed_content": "same\n"}, seed="same\n")
    assert r["status"] == "blocked" and "no_effective_change" in r["reasons"]


def test_full_content_create_still_works():
    ws = Path(tempfile.mkdtemp())
    r = _apply(ws, "new.html", {"action_type": "create", "proposed_content": "<h1>hi</h1>"})
    assert r["status"] == "applied" and "(full_content)" in r["summary"]
    assert (ws / "new.html").read_text() == "<h1>hi</h1>"


def _make_service():
    tmp = Path(tempfile.mkdtemp()); ca = tmp / "ca"; ca.mkdir()
    return AtlasPatchProposalService(journal=AtlasJournal(ca, workspace_id="default"),
                                     storage=AtlasPlanPoolStorage(ca), llm_json_fn=lambda s, u: {})


def test_normalize_edits_accepts_insertions_and_drops_anchorless_empty():
    svc = _make_service()
    warnings: list[str] = []
    out = svc._normalize_edits([
        {"old_string": "foo", "new_string": "bar"},
        {"old_string": "", "insert_after": "anchor", "new_string": "added"},
        {"old_string": "", "new_string": ""},  # malformed: nothing to add, no anchor -> dropped
    ], warnings)
    assert out == [
        {"old_string": "foo", "new_string": "bar"},
        {"old_string": "", "new_string": "added", "insert_after": "anchor"},
    ]
    assert "some_edits_dropped" in warnings


def test_normalize_file_changes_validates_nested_edits():
    # Regression: nested file_changes[].edits previously bypassed edit validation, so an empty
    # old_string with no anchor slipped through and blocked the atomic apply with edit_not_applicable.
    svc = _make_service()
    warnings: list[str] = []
    out = svc._normalize_file_changes([
        {"path": "index.html", "action_type": "update", "edits": [
            {"old_string": "real", "new_string": "new"},
            {"old_string": "", "new_string": "orphan"},  # would land nowhere -> appended (has new_string)
            {"old_string": "", "new_string": ""},          # dropped
        ]},
    ], warnings)
    assert len(out) == 1
    nested = out[0]["edits"]
    assert {"old_string": "real", "new_string": "new"} in nested
    assert {"old_string": "", "new_string": "orphan"} in nested
    assert all(not (e["old_string"] == "" and not e["new_string"]) for e in nested)


def test_proposal_to_executor_edits_flow():
    tmp = Path(tempfile.mkdtemp()); ca = tmp / "ca"; ca.mkdir(); ws = tmp / "ws"; ws.mkdir()
    (ws / "app.py").write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n", encoding="utf-8")
    storage = AtlasPlanPoolStorage(ca); journal = AtlasJournal(ca, workspace_id="default")
    item = AtlasPlanItem(item_id="s1", pool_id="p", title="t", goal="make foo return 100",
                         item_type="implementation", status="ready", risk_level="low",
                         target_files=["app.py"], metadata={"action_type": "update"})
    pool = AtlasPlanPool(pool_id="p", root_goal="g", project_path=str(ws), items=[item])
    storage.save_pool(pool)

    def llm(s, u):
        return {"edits": [{"old_string": "def foo():\n    return 1", "new_string": "def foo():\n    return 100"}],
                "risk_level": "low", "target_files": ["app.py"]}

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm)
    res = svc.propose_for_item(AtlasPatchProposalRequest(pool_id="p", item_id="s1", source_type="plan_item"))
    assert res.metadata.get("patch_content_available") is True

    reloaded = storage.load_pool("p"); it = reloaded.get_item("s1")
    assert it.metadata.get("edits") and it.metadata.get("action_type") == "update"
    r = AtlasFileSafeApplyExecutor(workspace_root=ws).apply_plan_item_safe(item=it, pool=reloaded)
    assert r["status"] == "applied"
    final = (ws / "app.py").read_text()
    assert "return 100" in final and "def bar" in final
