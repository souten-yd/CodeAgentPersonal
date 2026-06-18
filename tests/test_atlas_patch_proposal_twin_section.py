"""Step 3 — the compiled Twin instruction reaches the real generation prompt."""
from __future__ import annotations

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
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


def test_direct_patch_generation_builds_and_uses_project_twin(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    monkeypatch.delenv("ATLAS_TWIN_AUTOBUILD", raising=False)
    project = tmp_path / "project"
    target = project / "js" / "game.js"
    target.parent.mkdir(parents=True)
    target.write_text(
        "document.addEventListener('click', () => { enemy.destroyed = false; });\n",
        encoding="utf-8",
    )
    data_root = tmp_path / "ca"
    storage = AtlasPlanPoolStorage(data_root)
    journal = AtlasJournal(data_root, workspace_id="default")
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Fix Enemy Destruction Logic",
        goal="Destroy an enemy when it is hit",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["js/game.js"],
        requirement_ids=["req_001"],
        metadata={"action_type": "update"},
    )
    pool = AtlasPlanPool(
        pool_id="pool_1",
        root_goal="Fix enemy destruction",
        project_path=str(project),
        status="ready",
        items=[item],
        requirements=[{"requirement_id": "req_001", "description": "Enemy is destroyed on hit", "required": True}],
        requirement_item_map={"req_001": ["item_1"]},
    )
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    capture: dict = {}

    def fake_llm(system_prompt, _user_prompt):
        capture["system"] = system_prompt
        return {
            "target_files": ["js/game.js"],
            "proposed_content": "document.addEventListener('click', () => { enemy.destroyed = true; });\n",
            "satisfied_requirement_ids": ["req_001"],
            "implemented_symbols": ["enemy.destroyed"],
            "behavioral_cases": ["Enemy is destroyed on hit"],
            "verification_cases": ["Click hit destroys enemy"],
            "risk_level": "low",
        }

    result = AtlasPatchProposalService(
        journal=journal,
        storage=storage,
        llm_json_fn=fake_llm,
    ).propose_for_item(
        AtlasPatchProposalRequest(
            pool_id="pool_1",
            item_id="item_1",
            run_id="run_twin",
            source_type="plan_item",
        )
    )

    twin = result.metadata["twin_control_plane_generation"]
    assert result.status == "proposed"
    assert twin["mode"] == "active"
    assert twin["used_twin"] is True
    assert twin["project_twin_available"] is True
    assert twin["impact"]["available"] is True
    assert twin["instruction_id"]
    assert "Twin Control Plane" in capture["system"]
    assert list((data_root / "twin_control_plane" / "project_twin").glob("pool_1.sqlite3"))
