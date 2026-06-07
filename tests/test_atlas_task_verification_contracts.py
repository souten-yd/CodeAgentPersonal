from __future__ import annotations

from types import SimpleNamespace

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_task_verification_contracts import select_task_verification_contract


class _Runner:
    def __init__(self, *, stdout: str = "", status: str = "passed"):
        self.stdout = stdout
        self.status = status

    def run_command(self, *_args, **_kwargs):
        return SimpleNamespace(
            status=self.status,
            returncode=0 if self.status == "passed" else 1,
            stdout=self.stdout,
            stderr="",
            warnings=[],
            errors=[],
            model_dump=lambda: {"status": self.status, "stdout": self.stdout, "stderr": ""},
        )


def _service(tmp_path, pool, *, stdout: str = "", status: str = "passed"):
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=_Runner(stdout=stdout, status=status)), storage


def _item(*, contract: dict, goal: str = "ok", target: str = "app.py") -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Task",
        goal=goal,
        item_type="implementation",
        status="ready",
        target_files=[target],
        done_definition=[goal],
        metadata={
            "action_type": "update",
            "safe_apply": {"status": "applied", "changed_files": [target]},
            "verification": {"command_id": "pytest_selected", "test_path": "tests/test_ok.py"},
            "verification_contract": contract,
        },
    )


def test_python_module_contract_persists_evidence(tmp_path):
    (tmp_path / "app.py").write_text("def ok():\n    return 'valid result'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    item = _item(contract={"contract_id": "python_module"}, goal="valid result")
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="valid result", project_path=str(tmp_path), items=[item])
    svc, storage = _service(tmp_path, pool)

    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="pool_1", item_id="item_1", run_id="run_1"))

    assert out.status == "passed"
    contract = out.metadata["task_verification_contract"]
    assert contract["contract_id"] == "python_module_v1"
    reloaded = storage.load_pool("pool_1").get_item("item_1")
    assert reloaded.metadata["task_verification_contract"]["status"] == "passed"
    assert storage.load_pool("pool_1").metadata["task_verification_contracts"]["item_1"]["contract_id"] == "python_module_v1"


def test_api_endpoint_contract_requires_expected_response_signal(tmp_path):
    (tmp_path / "api.py").write_text("def route():\n    return {'status':'wrong'}\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    item = _item(
        contract={"contract_id": "api_endpoint", "expected_signals": ["status:ok"]},
        goal="status",
        target="api.py",
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Verify API endpoint response", project_path=str(tmp_path), items=[item])
    svc, _storage = _service(tmp_path, pool, stdout="status:wrong")

    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="pool_1", item_id="item_1", run_id="run_1"))

    assert out.status == "failed"
    assert "task_signal_missing:status:ok" in out.warnings
    assert any(w.startswith("repair_instruction:Verify the endpoint response") for w in out.warnings)


def test_api_endpoint_contract_passes_when_response_signal_is_observed(tmp_path):
    (tmp_path / "api.py").write_text("def route():\n    return 'status:ok'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    item = _item(
        contract={"contract_id": "api_endpoint", "expected_signals": ["status:ok"]},
        goal="status ok",
        target="api.py",
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Verify API endpoint response", project_path=str(tmp_path), items=[item])
    svc, _storage = _service(tmp_path, pool, stdout="HTTP 200 status:ok")

    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="pool_1", item_id="item_1", run_id="run_1"))

    assert out.status == "passed"
    assert out.metadata["task_verification_contract"]["matched_signals"] == ["status:ok"]


def test_persistence_contract_requires_reload_signal(tmp_path):
    (tmp_path / "state.py").write_text("STATE = 'saved after reload'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    item = _item(
        contract={"contract_id": "persistence", "expected_signals": ["reload:persisted"]},
        goal="reload persisted",
        target="state.py",
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Persist state after reload", project_path=str(tmp_path), items=[item])
    svc, _storage = _service(tmp_path, pool, stdout="reload:persisted")

    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id="pool_1", item_id="item_1", run_id="run_1"))

    assert out.status == "passed"
    assert out.metadata["task_verification_contract"]["contract_id"] == "persistence_state_reload_v1"


def test_browser_and_canvas_contracts_are_selected_from_task_shape(tmp_path):
    html_item = AtlasPlanItem(item_id="html", pool_id="pool_1", title="UI", goal="render UI", target_files=["index.html"])
    game_item = AtlasPlanItem(item_id="game", pool_id="pool_1", title="Game", goal="canvas game with score", target_files=["index.html"])
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="canvas game with score", project_path=str(tmp_path), items=[html_item, game_item])

    assert select_task_verification_contract(html_item, pool).contract_id == "browser_html_ui_v1"
    assert select_task_verification_contract(game_item, pool).contract_id == "canvas_game_v1"


def test_multifile_integration_contract_is_selected_from_multiple_targets(tmp_path):
    item = AtlasPlanItem(
        item_id="multi",
        pool_id="pool_1",
        title="Wire service into endpoint",
        goal="wire endpoint service",
        target_files=["api.py", "service.py"],
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="wire endpoint service", project_path=str(tmp_path), items=[item])

    contract = select_task_verification_contract(item, pool)

    assert contract.contract_id == "multi_file_integration_v1"
    assert "integration_graph" in contract.required_evidence
