"""Pillar A: read-before-edit — the patch generator grounds on the target file's CURRENT content,
and a mislabeled 'create' on an existing file applies as an update (preserving existing code)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _setup(target_files, action_type="create", seed_content=None):
    tmp = Path(tempfile.mkdtemp())
    ca = tmp / "ca"; ca.mkdir()
    ws = tmp / "ws"; ws.mkdir()
    if seed_content is not None and target_files:
        (ws / target_files[0]).write_text(seed_content, encoding="utf-8")
    storage = AtlasPlanPoolStorage(ca)
    journal = AtlasJournal(ca, workspace_id="default")
    item = AtlasPlanItem(item_id="step_1", pool_id="p", title="t", goal="g", item_type="implementation",
                         status="ready", risk_level="low", target_files=target_files,
                         metadata={"action_type": action_type})
    pool = AtlasPlanPool(pool_id="p", root_goal="g", project_path=str(ws), items=[item])
    storage.save_pool(pool); journal.save_plan_pool(pool)
    return storage, journal, ws


def test_existing_file_content_reaches_llm_and_is_preserved():
    storage, journal, ws = _setup(["app.py"], action_type="create",
                                  seed_content="import os\n\ndef existing():\n    return 42\n")
    seen = {}

    def fake_llm(system, user):
        item = json.loads(user).get("input", {}).get("item", {})
        seen["exists"] = item.get("target_file_exists")
        seen["current"] = item.get("current_file_content")
        seen["task_exists"] = "ALREADY EXISTS" in json.loads(user).get("task", "")
        # Preserve the existing content and append a new function.
        return {"proposed_content": item.get("current_file_content", "") + "\ndef greet():\n    return 'hi'\n",
                "risk_level": "low", "target_files": ["app.py"]}

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=fake_llm)
    res = svc.propose_for_item(AtlasPatchProposalRequest(pool_id="p", item_id="step_1", source_type="plan_item"))

    assert seen["exists"] is True
    assert "existing()" in (seen["current"] or "")
    assert seen["task_exists"] is True
    content = (res.proposal.metadata or {}).get("proposed_content", "")
    assert "existing()" in content and "def greet" in content


def test_mislabeled_create_on_existing_file_applies_as_update():
    storage, journal, ws = _setup(["app.py"], action_type="create",
                                  seed_content="def existing():\n    return 42\n")

    def fake_llm(system, user):
        item = json.loads(user).get("input", {}).get("item", {})
        return {"proposed_content": item.get("current_file_content", "") + "\ndef greet():\n    return 'hi'\n",
                "risk_level": "low", "target_files": ["app.py"]}

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=fake_llm)
    svc.propose_for_item(AtlasPatchProposalRequest(pool_id="p", item_id="step_1", source_type="plan_item"))

    pool = storage.load_pool("p")
    item = pool.get_item("step_1")
    executor = AtlasFileSafeApplyExecutor(workspace_root=ws)
    result = executor.apply_plan_item_safe(item=item, pool=pool)

    assert result["status"] == "applied"
    assert result["summary"].startswith("update")  # create -> update on existing file
    final = (ws / "app.py").read_text(encoding="utf-8")
    assert "def existing" in final and "def greet" in final


def test_new_file_path_unaffected():
    storage, journal, ws = _setup(["index.html"], action_type="create", seed_content=None)
    seen = {}

    def fake_llm(system, user):
        item = json.loads(user).get("input", {}).get("item", {})
        seen["exists"] = item.get("target_file_exists")
        seen["new_task"] = "new file write" in json.loads(user).get("task", "")
        return {"proposed_content": "<!doctype html><h1>hello</h1>", "risk_level": "low", "target_files": ["index.html"]}

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=fake_llm)
    res = svc.propose_for_item(AtlasPatchProposalRequest(pool_id="p", item_id="step_1", source_type="plan_item"))

    assert seen["exists"] is False
    assert seen["new_task"] is True
    assert res.metadata.get("patch_content_available") is True


def test_read_helper_ignores_unsafe_and_multi_target():
    # Absolute / traversal paths and multi-file items must not read anything.
    storage, journal, ws = _setup(["a.py", "b.py"], action_type="create", seed_content=None)
    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=lambda s, u: {})
    pool = storage.load_pool("p")
    item = pool.get_item("step_1")
    req = AtlasPatchProposalRequest(pool_id="p", item_id="step_1", source_type="plan_item")
    out = svc._read_existing_target_content(pool, item, req)
    assert out["exists"] is False  # multi-target -> no read
