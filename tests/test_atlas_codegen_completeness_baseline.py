from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_multi_item_autopilot_service import AtlasMultiItemAutopilotService
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest, AtlasPatchProposalResult
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_requirement_tracer import AtlasRequirementTracer
from agent.atlas_run_quality_rollup import compute_run_quality_rollup


def _complete_requirement_contract() -> dict:
    return {
        "root_goal": "Build a complete score widget",
        "original_user_request": "Create a score widget that increments and persists.",
        "selected_architecture": "single module with persisted state",
        "requirements": [
            {"requirement_id": "req_score", "description": "Score increments"},
            {"requirement_id": "req_persist", "description": "Score persists after reload"},
        ],
        "acceptance_criteria": ["Score increments", "Score persists after reload"],
        "verification_contract": {"contract_id": "browser_state_reload", "signals": ["increment", "reload"]},
        "preserve_behaviors": ["Do not remove existing reset control"],
    }


def _same_file_items(pool_id: str = "pool_1") -> list[AtlasPlanItem]:
    return [
        AtlasPlanItem(
            item_id="item_001",
            pool_id=pool_id,
            title="Add first behavior",
            goal="Add alpha behavior",
            item_type="implementation",
            status="ready",
            risk_level="low",
            target_files=["app.py"],
            metadata={"action_type": "update"},
        ),
        AtlasPlanItem(
            item_id="item_002",
            pool_id=pool_id,
            title="Add second behavior",
            goal="Add beta behavior",
            item_type="implementation",
            status="ready",
            risk_level="low",
            target_files=["app.py"],
            metadata={"action_type": "update"},
        ),
    ]


def _partial_stub_item(pool_id: str = "pool_1") -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id="item_stub",
        pool_id=pool_id,
        title="Stub content",
        goal="Render real score behavior",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["index.html"],
        metadata={"action_type": "create"},
    )


def _verification_unavailable_item(pool_id: str = "pool_1") -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id="item_unverified",
        pool_id=pool_id,
        title="Needs unavailable verification",
        goal="Apply code with unavailable verification",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["app.py"],
        metadata={"action_type": "create", "proposed_content": "print('ok')\n"},
    )


def _pool(tmp_path: Path, items: list[AtlasPlanItem], *, metadata: dict | None = None) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_1",
        root_goal="Build complete code",
        project_path=str(tmp_path),
        status="ready",
        automation_level="full_autopilot",
        items=items,
        metadata=metadata or {},
    )


def _storage_and_journal(tmp_path: Path, pool: AtlasPlanPool):
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return storage, journal


class _CapturingProposalService:
    def __init__(self, storage: AtlasPlanPoolStorage):
        self.storage = storage
        self.seen_current_content: list[tuple[str, str]] = []

    def propose_for_item(self, request: AtlasPatchProposalRequest) -> AtlasPatchProposalResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        assert item is not None
        target = Path(pool.project_path) / item.target_files[0]
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        self.seen_current_content.append((request.item_id, current))
        item.metadata["proposed_content"] = current + f"# proposal:{request.item_id}\n"
        self.storage.save_pool(pool)
        return AtlasPatchProposalResult(
            pool_id=request.pool_id,
            item_id=request.item_id,
            run_id=request.run_id,
            status="proposed",
            metadata={
                "patch_content_available": True,
                "patch_generation": {
                    "run_id": request.run_id,
                    "state": "succeeded",
                    "outcome": "success",
                    "patch_content_available": True,
                },
            },
        )


class _RecordingAutopilotService:
    def __init__(self, storage: AtlasPlanPoolStorage, project_path: Path):
        self.storage = storage
        self.project_path = project_path
        self.last_request: AtlasMultiItemAutopilotRequest | None = None
        self.requests: list[AtlasMultiItemAutopilotRequest] = []

    def run(self, request: AtlasMultiItemAutopilotRequest):
        self.last_request = request
        self.requests.append(request)
        item_id = request.item_ids[0]
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(item_id)
        assert item is not None
        content = str((item.metadata or {}).get("proposed_content") or "")
        (self.project_path / item.target_files[0]).write_text(content, encoding="utf-8")
        item.status = "completed"
        item.metadata.setdefault("safe_apply", {})["changed_files"] = list(item.target_files)
        if item.item_id not in pool.completed_item_ids:
            pool.completed_item_ids.append(item.item_id)
        self.storage.save_pool(pool)
        return SimpleNamespace(
            status="completed",
            stop_reason="",
            warnings=[],
            autopilot_run_id="auto_wp0",
            processed_count=1,
            completed_count=1,
            failed_count=0,
            blocked_count=0,
            item_results=[
                SimpleNamespace(
                    item_id=item_id,
                    status="completed",
                    changed_files=list(item.target_files),
                    verification_result={"status": "passed"},
                    model_dump=lambda: {"item_id": item_id, "status": "completed"},
                )
            ],
            model_dump=lambda: {
                "status": "completed",
                "item_results": [{"item_id": item_id, "status": "completed"}],
                "processed_count": 1,
            },
        )


def test_wp0_fixture_helpers_cover_required_baseline_shapes() -> None:
    contract = _complete_requirement_contract()
    same_file = _same_file_items()
    stub = _partial_stub_item()
    unavailable = _verification_unavailable_item()

    assert [item.target_files for item in same_file] == [["app.py"], ["app.py"]]
    assert contract["requirements"][0]["requirement_id"] == "req_score"
    assert stub.target_files == ["index.html"]
    assert unavailable.metadata["proposed_content"]


def test_wp3_autonomous_generation_is_interleaved_and_reads_latest_same_file_content(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("BASE = 1\n", encoding="utf-8")
    pool = _pool(tmp_path, _same_file_items())
    storage, journal = _storage_and_journal(tmp_path, pool)
    proposals = _CapturingProposalService(storage)
    autopilot = _RecordingAutopilotService(storage, tmp_path)
    service = AtlasAutonomousCodegenOrchestratorService(
        storage=storage,
        journal=journal,
        patch_proposal_service=proposals,
        multi_item_autopilot_service=autopilot,
        data_root=tmp_path / "ca",
    )

    out = service.run(AtlasAutonomousCodegenRequest(pool_id="pool_1", run_id="run_1"))

    assert out.status == "completed"
    assert out.generated_count == 2
    assert proposals.seen_current_content == [
        ("item_001", "BASE = 1\n"),
        ("item_002", "BASE = 1\n# proposal:item_001\n"),
    ]
    assert autopilot.last_request is not None
    assert [request.item_ids for request in autopilot.requests] == [["item_001"], ["item_002"]]


def test_wp0_proposal_input_now_carries_full_context_and_multifile_content(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def existing():\n    return 'app'\n", encoding="utf-8")
    (tmp_path / "style.css").write_text(".existing { color: blue; }\n", encoding="utf-8")
    contract = _complete_requirement_contract()
    item = AtlasPlanItem(
        item_id="item_001",
        pool_id="pool_1",
        title="Implement score widget",
        goal="Implement score and persistence",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["app.py", "style.css"],
        requirement_ids=["req_score", "req_persist"],
        acceptance_criteria=contract["acceptance_criteria"],
        verification_contract=contract["verification_contract"],
        done_definition=contract["acceptance_criteria"],
        metadata={
            "action_type": "update",
            "requirement_ids": ["req_score", "req_persist"],
            "acceptance_criteria": contract["acceptance_criteria"],
            "verification_contract": contract["verification_contract"],
        },
    )
    pool = _pool(
        tmp_path,
        [item],
        metadata={
            "original_user_request": contract["original_user_request"],
            "selected_architecture": contract["selected_architecture"],
            "requirement_trace": contract["requirements"],
            "preserve_behaviors": contract["preserve_behaviors"],
        },
    )
    storage, journal = _storage_and_journal(tmp_path, pool)
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=None)

    payload = service.build_proposal_input(pool, item, AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001"))

    assert payload["root_goal"] == "Build complete code"
    assert payload["original_user_request"] == contract["original_user_request"]
    assert [r["requirement_id"] for r in payload["all_requirements"]] == ["req_score", "req_persist"]
    assert [r["requirement_id"] for r in payload["requirements_for_this_item"]] == ["req_score", "req_persist"]
    assert payload["item"]["target_files"] == ["app.py", "style.css"]
    assert payload["current_target_contents"]["app.py"]["content"].startswith("def existing")
    assert payload["current_target_contents"]["style.css"]["content"].startswith(".existing")
    assert payload["item"]["current_file_truncated"] is False


def test_wp4_generation_quality_failure_returns_no_applicable_content(tmp_path: Path) -> None:
    item = _partial_stub_item()
    pool = _pool(tmp_path, [item])
    storage, journal = _storage_and_journal(tmp_path, pool)

    def llm_stub(_system: str, _user: str) -> dict:
        return {
            "target_files": ["index.html"],
            "proposed_content": "<!doctype html>\n<script>\n// TODO implement score behavior\n</script>\n",
            "risk_level": "low",
            "implemented_symbols": ["score"],
            "behavioral_cases": ["Render real score behavior"],
            "verification_cases": ["browser smoke"],
        }

    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm_stub)
    payload = service.build_proposal_input(pool, item, AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_stub", source_type="plan_item"))

    proposal = service.generate_proposal_with_llm(payload)

    assert "semantic_validation_failed" in proposal.warnings or "self_review_findings_unresolved" in proposal.warnings
    assert proposal.metadata["patch_content_available"] is False
    assert proposal.metadata["generation_failed"] is True
    assert "proposed_content" not in proposal.metadata


def test_wp6_partial_requirement_coverage_blocks_success(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def alphaunique():\n    return 'alphaunique'\n", encoding="utf-8")
    pool = _pool(
        tmp_path,
        [],
        metadata={
            "requirement_trace": [
                {"requirement_id": "req_alpha", "description": "alphaunique capability"},
                {"requirement_id": "req_beta", "description": "betazzz capability"},
            ]
        },
    )
    item_result = SimpleNamespace(status="completed", changed_files=["app.py"], verification_result={"status": "passed"})

    rollup = compute_run_quality_rollup(pool, [item_result], project_path=str(tmp_path))

    coverage = rollup["requirement_coverage"]
    assert coverage["by_status"].get("verified", 0) == 1
    assert coverage["by_status"].get("partial", 0) == 1
    assert coverage["all_verified"] is False
    assert coverage["success_eligible"] is False
    assert "req_beta" in coverage["incomplete_requirement_ids"]
    assert rollup["degraded"] is True
    assert "requirement_coverage_incomplete" in rollup["degrade_reasons"]


def test_wp0_verification_skipped_can_still_complete_item(tmp_path: Path) -> None:
    pool = _pool(tmp_path, [_verification_unavailable_item()])

    class Storage:
        def load_pool(self, _pool_id: str):
            return pool

        def save_pool(self, _pool: AtlasPlanPool):
            return None

    class Journal:
        def append_event(self, *_args, **_kwargs):
            return None

    class AutoSafe:
        def execute_one(self, _request):
            return SimpleNamespace(
                status="applied",
                changed_files=["app.py"],
                model_dump=lambda: {
                    "status": "applied",
                    "changed_files": ["app.py"],
                    "actual_file_changed": True,
                    "file_results": [{"path": "app.py", "status": "applied"}],
                },
            )

    class Verification:
        def run_after_auto_safe_apply(self, _request):
            return SimpleNamespace(status="skipped", warnings=["external_verifier_skipped"], model_dump=lambda: {"status": "skipped", "warnings": ["external_verifier_skipped"]})

    service = AtlasMultiItemAutopilotService(
        storage=Storage(),
        journal=Journal(),
        automation_gate=SimpleNamespace(decide_pre_safe_apply=lambda *_args, **_kwargs: SimpleNamespace(decision="allow", reasons=[])),
        auto_safe_apply_service=AutoSafe(),
        auto_verification_service=Verification(),
        context_refresh_service=SimpleNamespace(refresh=lambda _request: SimpleNamespace(status="available", bundle_id="ctx1")),
        evaluator_service=SimpleNamespace(evaluate=lambda _request: SimpleNamespace(metadata={}, decision=SimpleNamespace(model_dump=lambda: {"decision": "continue"}))),
    )

    out = service.run(
        AtlasMultiItemAutopilotRequest(
            pool_id="pool_1",
            project_path=str(tmp_path),
            policy_id="full_auto_multi_item_v1",
            require_approval=False,
            include_context_refresh=False,
            include_evaluator=False,
            include_harness_provisioning=False,
            include_self_correction=False,
        )
    )

    assert out.status == "applied_unverified"
    assert out.item_results[0].status == "applied_no_verification"
    assert out.item_results[0].reason == "verification_skipped"


def test_wp0_existing_requirement_tracer_summary_already_rejects_partial_requirements() -> None:
    tracer = AtlasRequirementTracer()
    mapped = [
        {"requirement_id": "req_1", "status": "verified"},
        {"requirement_id": "req_2", "status": "partial"},
    ]

    summary = tracer.coverage_summary(mapped)

    assert summary["success_eligible"] is False
    assert summary["missing_or_partial_count"] == 1


def test_wp6_explicit_requirement_mapping_records_verified_and_unverified(tmp_path: Path) -> None:
    (tmp_path / "score.py").write_text("def increment_score():\n    return 'score persists'\n", encoding="utf-8")
    item_score = AtlasPlanItem(
        item_id="item_score",
        pool_id="pool_1",
        title="Implement score",
        goal="Score increments",
        item_type="implementation",
        status="completed",
        target_files=["score.py"],
        requirement_ids=["req_score"],
        metadata={"action_type": "update", "implemented_symbols": ["increment_score"]},
    )
    item_persist = AtlasPlanItem(
        item_id="item_persist",
        pool_id="pool_1",
        title="Implement persistence",
        goal="Score persists",
        item_type="implementation",
        status="completed",
        target_files=["score.py"],
        requirement_ids=["req_persist"],
        metadata={"action_type": "update"},
    )
    pool = _pool(
        tmp_path,
        [item_score, item_persist],
        metadata={
            "requirement_trace": [
                {"requirement_id": "req_score", "description": "Score increments", "required": True},
                {"requirement_id": "req_persist", "description": "Score persists", "required": True},
            ]
        },
    )
    item_results = [
        SimpleNamespace(item_id="item_score", status="completed", changed_files=["score.py"], verification_result={"status": "passed", "metadata": {"evidence_path": "reports/score.txt"}}),
        SimpleNamespace(item_id="item_persist", status="applied_no_verification", changed_files=["score.py"], verification_result={"status": "skipped"}),
    ]

    rollup = compute_run_quality_rollup(pool, item_results, project_path=str(tmp_path))
    mapped = {req["requirement_id"]: req for req in rollup["requirement_coverage"]["mapped"]}

    assert mapped["req_score"]["status"] == "verified"
    assert mapped["req_score"]["planned_items"] == ["item_score"]
    assert mapped["req_score"]["changed_files"] == ["score.py"]
    assert mapped["req_score"]["implemented_symbols"] == ["increment_score"]
    assert mapped["req_score"]["evidence_path"] == "reports/score.txt"
    assert mapped["req_persist"]["status"] == "unverified"
    assert rollup["requirement_coverage"]["success_eligible"] is False


def test_wp6_static_visual_evidence_can_verify_japanese_requirement_id(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><h1>レインボー表示</h1>", encoding="utf-8")
    item = AtlasPlanItem(
        item_id="item_visual",
        pool_id="pool_1",
        title="Visual",
        goal="レインボー表示",
        item_type="implementation",
        status="completed",
        target_files=["index.html"],
        requirement_ids=["要件_虹"],
        metadata={"action_type": "create"},
    )
    pool = _pool(
        tmp_path,
        [item],
        metadata={"requirement_trace": [{"requirement_id": "要件_虹", "description": "レインボー表示", "required": True}]},
    )
    item_result = SimpleNamespace(
        item_id="item_visual",
        status="completed",
        changed_files=["index.html"],
        verification_result={"status": "passed", "metadata": {"verify_level": "static_checked", "evidence_path": "visual/static.json"}},
    )

    rollup = compute_run_quality_rollup(pool, [item_result], project_path=str(tmp_path))
    mapped = rollup["requirement_coverage"]["mapped"][0]

    assert mapped["requirement_id"] == "要件_虹"
    assert mapped["status"] == "verified_static"
    assert rollup["requirement_coverage"]["success_eligible"] is True
