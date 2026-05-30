"""Pillar E: auto-resolve a verification command so generated tests actually run (and feed the loop)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_verification_resolver import resolve_verification_for_item


def test_python_test_file_resolves_to_pytest_file():
    assert resolve_verification_for_item(target_files=["tests/test_app.py"]) == {
        "command_id": "pytest_file", "test_file": "tests/test_app.py"}
    assert resolve_verification_for_item(target_files=["foo_test.py"]) == {
        "command_id": "pytest_file", "test_file": "foo_test.py"}


def test_non_test_without_project_is_empty():
    assert resolve_verification_for_item(target_files=["app.py"]) == {}


def test_unsafe_and_multi_target_are_empty():
    assert resolve_verification_for_item(target_files=["../x.py"]) == {}
    assert resolve_verification_for_item(target_files=["/abs/x.py"]) == {}
    assert resolve_verification_for_item(target_files=["a.py", "b.py"]) == {}


def test_non_test_with_related_test_resolves():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "app.py").write_text("def f(): pass\n", encoding="utf-8")
    (tmp / "tests").mkdir()
    (tmp / "tests" / "test_app.py").write_text("def test_f(): pass\n", encoding="utf-8")
    spec = resolve_verification_for_item(target_files=["app.py"], project_path=str(tmp))
    assert spec == {"command_id": "pytest_file", "test_file": "tests/test_app.py"}


def test_test_writing_item_gets_verification_wired_through_proposal():
    tmp = Path(tempfile.mkdtemp()); ca = tmp / "ca"; ca.mkdir(); ws = tmp / "ws"; ws.mkdir()
    storage = AtlasPlanPoolStorage(ca); journal = AtlasJournal(ca, workspace_id="default")
    item = AtlasPlanItem(item_id="s1", pool_id="p", title="write test", goal="add test",
                         item_type="implementation", status="ready", risk_level="low",
                         target_files=["tests/test_greet.py"], metadata={"action_type": "create"})
    pool = AtlasPlanPool(pool_id="p", root_goal="g", project_path=str(ws), items=[item])
    storage.save_pool(pool)
    svc = AtlasPatchProposalService(journal=journal, storage=storage,
        llm_json_fn=lambda s, u: {"proposed_content": "def test_greet():\n    assert True\n",
                                  "risk_level": "low", "target_files": ["tests/test_greet.py"]})
    svc.propose_for_item(AtlasPatchProposalRequest(pool_id="p", item_id="s1", source_type="plan_item"))
    it = storage.load_pool("p").get_item("s1")
    assert it.metadata.get("verification") == {"command_id": "pytest_file", "test_file": "tests/test_greet.py"}


def test_existing_verification_is_not_overridden():
    tmp = Path(tempfile.mkdtemp()); ca = tmp / "ca"; ca.mkdir(); ws = tmp / "ws"; ws.mkdir()
    storage = AtlasPlanPoolStorage(ca); journal = AtlasJournal(ca, workspace_id="default")
    item = AtlasPlanItem(item_id="s1", pool_id="p", title="write test", goal="add test",
                         item_type="implementation", status="ready", risk_level="low",
                         target_files=["tests/test_x.py"],
                         metadata={"action_type": "create", "verification": {"command_id": "pytest_selected", "test_path": "tests/"}})
    pool = AtlasPlanPool(pool_id="p", root_goal="g", project_path=str(ws), items=[item])
    storage.save_pool(pool)
    svc = AtlasPatchProposalService(journal=journal, storage=storage,
        llm_json_fn=lambda s, u: {"proposed_content": "def test_x():\n    assert True\n",
                                  "risk_level": "low", "target_files": ["tests/test_x.py"]})
    svc.propose_for_item(AtlasPatchProposalRequest(pool_id="p", item_id="s1", source_type="plan_item"))
    it = storage.load_pool("p").get_item("s1")
    # The planner-set verification must be preserved, not replaced.
    assert it.metadata["verification"]["command_id"] == "pytest_selected"
