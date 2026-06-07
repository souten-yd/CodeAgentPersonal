from __future__ import annotations

import hashlib
from pathlib import Path

from app.atlas.candidate_workspace_manager import create_candidate_workspace_plan, write_candidate_workspace_plan
from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import AtlasAutopilotItemResult, AtlasMultiItemAutopilotRequest, AtlasMultiItemAutopilotResult
from agent.atlas_patch_proposal_schema import AtlasPatchProposalResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _item(item_id: str, *, risk_level: str = "low", action_type: str = "create", metadata: dict | None = None) -> AtlasPlanItem:
    md = {"action_type": action_type}
    if metadata:
        md.update(metadata)
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_1",
        title=f"Item {item_id}",
        goal=f"Do {item_id}",
        item_type="implementation",
        status="ready",
        risk_level=risk_level,
        target_files=[f"src/{item_id}.py"],
        metadata=md,
    )


def _pool(items, *, status: str = "ready", metadata: dict | None = None) -> AtlasPlanPool:
    return AtlasPlanPool(pool_id="pool_1", root_goal="Goal", project_path="/tmp/proj", status=status, items=items, metadata=metadata or {})


def _active_envelope() -> dict:
    return {
        "envelope_id": "pre_authorized_bounded_dev_envelope",
        "status": "active",
        "bounds": {
            "allowed_paths": ["src/"],
            "blocked_paths": [".git/"],
            "max_actions_per_loop": 5,
            "max_files_changed": 5,
            "max_runtime_seconds": 60,
            "max_risk_level": "medium",
        },
    }


class FakeProposalService:
    """Fills proposed_content for the requested item (mirrors the real service persisting to pool)."""

    def __init__(self, storage: AtlasPlanPoolStorage, *, produce_content: bool = True):
        self.storage = storage
        self.produce_content = produce_content
        self.calls: list[str] = []

    def propose_for_item(self, request):
        self.calls.append(request.item_id)
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        available = False
        if item is not None and self.produce_content:
            item.metadata["proposed_content"] = f"# generated {request.item_id}\n"
            self.storage.save_pool(pool)
            available = True
        return AtlasPatchProposalResult(
            pool_id=request.pool_id,
            item_id=request.item_id,
            run_id=request.run_id,
            status="proposed",
            metadata={
                "patch_content_available": available,
                "patch_generation": {
                    "run_id": request.run_id,
                    "state": "succeeded" if available else "failed",
                    "outcome": "success" if available else "failure",
                    "patch_content_available": available,
                },
            },
            warnings=[] if available else ["patch_content_unavailable"],
        )


class FakeAutopilotService:
    def __init__(self, status: str = "completed"):
        self.status = status
        self.last_request: AtlasMultiItemAutopilotRequest | None = None
        self.requests: list[AtlasMultiItemAutopilotRequest] = []

    def run(self, request: AtlasMultiItemAutopilotRequest) -> AtlasMultiItemAutopilotResult:
        self.last_request = request
        self.requests.append(request)
        item_id = request.item_ids[0] if request.item_ids else "i1"
        return AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id,
            run_id=request.run_id,
            autopilot_run_id="auto_test",
            policy_id=request.policy_id,
            status=self.status,
            processed_count=len(request.item_ids) or 1,
            completed_count=1 if self.status in {"completed", "partial"} else 0,
            failed_count=1 if self.status in {"failed", "needs_revision"} else 0,
            item_results=[
                AtlasAutopilotItemResult(
                    item_id=item_id,
                    status=self.status,
                    changed_files=[f"src/{item_id}.py"] if self.status in {"completed", "partial"} else [],
                    verification_result={"status": "passed"} if self.status in {"completed", "partial"} else {"status": "failed"},
                    metadata={"bounded_retry_result": {"status": "not_needed"}},
                )
            ],
            created_at="2026-06-01T00:00:00+00:00",
        )


def _orchestrator(tmp_path: Path, pool: AtlasPlanPool, *, produce_content: bool = True, autopilot_status: str = "completed", draft_pr_client=None):
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    journal = AtlasJournal(tmp_path, workspace_id="default")
    proposal = FakeProposalService(storage, produce_content=produce_content)
    autopilot = FakeAutopilotService(status=autopilot_status)
    svc = AtlasAutonomousCodegenOrchestratorService(
        storage=storage,
        journal=journal,
        patch_proposal_service=proposal,
        multi_item_autopilot_service=autopilot,
        draft_pr_client=draft_pr_client,
    )
    return svc, storage, proposal, autopilot


class FakeDraftPrClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def create_draft_pull_request(self, *, base_ref: str, head_branch: str, title: str, body: str) -> dict[str, object]:
        self.calls.append({"base_ref": base_ref, "head_branch": head_branch, "title": title, "body": body})
        return {"number": 88, "html_url": "https://example.test/pull/88", "url": "https://api.example.test/pull/88", "draft": True}


def test_generates_missing_patch_then_applies(tmp_path: Path) -> None:
    svc, storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == ["i1"]  # content was missing -> generated
    assert out.generated_count == 1
    assert autopilot.last_request is not None  # apply phase ran
    assert autopilot.last_request.policy_id == "full_auto_multi_item_v1"
    assert autopilot.last_request.require_approval is False
    assert out.phase == "final_summary"
    assert out.status == "completed"
    assert out.metadata["draft_pr_artifact"]["ready"] is True
    assert Path(out.metadata["draft_pr_artifact"]["artifact_path"]).exists()
    # The pool is tagged full_autopilot so the single-item pipeline also relaxes.
    assert storage.load_pool("pool_1").automation_level == "full_autopilot"


def test_successful_run_produces_pr_artifact_body(tmp_path: Path) -> None:
    item = _item("i1")
    item.rollback_plan = ["Restore src/i1.py from snapshot."]
    pool = _pool(
        [item],
        metadata={
            "clarification_answers": [{"question_id": "q1", "answer": "Use narrow scope"}],
            "critical_decisions": [{"event_id": "crit1", "decision": "reject"}],
        },
    )
    svc, _storage, _proposal, _autopilot = _orchestrator(tmp_path, pool)

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    artifact = out.metadata["draft_pr_artifact"]
    body = Path(artifact["body_path"]).read_text(encoding="utf-8")
    for heading in [
        "## Summary",
        "## Scope",
        "## Safety constraints",
        "## Changed files",
        "## Tests / verification",
        "## Clarification decisions",
        "## Critical events / user decisions",
        "## Repair attempts",
        "## Remaining risks",
        "## Rollback notes",
    ]:
        assert heading in body
    assert "Use narrow scope" in body
    assert "crit1" in body
    assert "Restore src/i1.py from snapshot." in body


def test_draft_pr_creation_uses_injected_client_only(tmp_path: Path) -> None:
    client = FakeDraftPrClient()
    svc, _storage, _proposal, _autopilot = _orchestrator(tmp_path, _pool([_item("i1")]), draft_pr_client=client)

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            metadata={
                "base_ref": "main",
                "head_branch": "codex/atlas-generated",
                "draft_pr_title": "Atlas generated change",
            },
            envelope={"allow_draft_pr_creation": True},
        )
    )

    creation = out.metadata["draft_pr_artifact"]["creation_result"]
    assert creation["draft_pr_created"] is True
    assert creation["draft_pr_url"] == "https://example.test/pull/88"
    assert creation["remote_git_push_performed"] is False
    assert creation["direct_merge_performed"] is False
    assert client.calls[0]["base_ref"] == "main"
    assert client.calls[0]["head_branch"] == "codex/atlas-generated"


def test_draft_pr_creation_requires_envelope_permission(tmp_path: Path) -> None:
    client = FakeDraftPrClient()
    svc, _storage, _proposal, _autopilot = _orchestrator(tmp_path, _pool([_item("i1")]), draft_pr_client=client)

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            metadata={"allow_draft_pr_creation": True},
        )
    )

    creation = out.metadata["draft_pr_artifact"]["creation_result"]
    assert creation["draft_pr_created"] is False
    assert creation["allowed"] is False
    assert creation["blocked_reasons"] == ["draft_pr_envelope_permission_required"]
    assert client.calls == []


def test_failed_run_does_not_claim_pr_ready(tmp_path: Path) -> None:
    svc, _storage, _proposal, _autopilot = _orchestrator(tmp_path, _pool([_item("i1")]), autopilot_status="needs_revision")

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    artifact = out.metadata["draft_pr_artifact"]
    assert artifact["ready"] is False
    assert artifact["status"] == "not_ready"
    assert out.metadata["draft_pr_readiness"]["ready"] is False


def test_missing_project_path_stops_safely(tmp_path: Path) -> None:
    pool = _pool([_item("i1")])
    pool.project_path = ""
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, pool)

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "stopped"
    assert out.phase == "understanding_goal"
    assert out.stop_reason == "missing_project_path"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_unsafe_path_stops_before_generation(tmp_path: Path) -> None:
    item = _item("i1")
    item.target_files = ["../outside.py"]
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([item]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "stopped"
    assert out.stop_reason == "unsafe_path"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_blocked_path_stops_before_generation(tmp_path: Path) -> None:
    item = _item("i1")
    item.target_files = ["secrets/token.txt"]
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([item]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            blocked_paths=["secrets/"],
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "blocked_path"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_request_allowed_paths_cannot_expand_active_envelope(tmp_path: Path) -> None:
    item = _item("i1")
    item.target_files = ["docs/guide.md"]
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([item]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_paths=["docs/"],
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "allowed_paths_expand_envelope"
    assert out.metadata["preflight"]["requested_allowed_paths"] == ["docs/"]
    assert out.metadata["preflight"]["paths"] == ["docs/guide.md"]
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_envelope_bounds_clamp_autonomous_request_limits(tmp_path: Path) -> None:
    items = [_item(f"i{i}") for i in range(1, 8)]
    svc, _storage, _proposal, autopilot = _orchestrator(tmp_path, _pool(items))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            max_actions=20,
            max_items=20,
            max_runtime_seconds=600,
            max_changed_files_total=20,
            max_changed_files_per_item=20,
        )
    )

    assert out.status == "completed"
    effective = out.metadata["preflight"]["effective_limits"]
    assert effective["max_actions"] == 5
    assert effective["max_items"] == 5
    assert effective["max_runtime_seconds"] == 60
    assert effective["max_changed_files_total"] == 5
    assert effective["max_changed_files_per_item"] == 5
    assert "request_limits_clamped_to_envelope" in out.warnings
    assert autopilot.last_request is not None
    assert len(autopilot.requests) == 5
    assert autopilot.last_request.max_items == 1
    assert autopilot.last_request.max_runtime_seconds == 60
    assert autopilot.requests[0].max_changed_files_total == 5


def test_allowed_verification_commands_are_blocked_until_supported(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_verification_commands=["python -m pytest tests/test_example.py"],
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "allowed_verification_commands_unsupported"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_clarification_allowed_paths_block_unrevised_target_files(tmp_path: Path) -> None:
    item = _item("i1")
    item.target_files = ["src/unrevised.py"]
    pool = _pool(
        [item],
        metadata={
            "allowed_paths_after_clarification": ["src/revised.py"],
            "blocked_paths_after_clarification": [],
            "revised_plan_snapshot": {"root_goal": "Revised"},
            "gate_rerun_performed_after_clarification": True,
        },
    )
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, pool)

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "path_outside_clarification_allowed_paths"
    assert out.metadata["preflight"]["clarification_scope"]["allowed_paths"] == ["src/revised.py"]
    assert out.metadata["preflight"]["paths"] == ["src/unrevised.py"]
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_clarification_allowed_paths_allow_revised_target_files(tmp_path: Path) -> None:
    item = _item("i1")
    item.target_files = ["src/revised.py"]
    pool = _pool(
        [item],
        metadata={
            "allowed_paths_after_clarification": ["src/revised.py"],
            "blocked_paths_after_clarification": [],
            "revised_plan_snapshot": {"root_goal": "Revised"},
            "gate_rerun_performed_after_clarification": True,
        },
    )
    svc, _storage, _proposal, autopilot = _orchestrator(tmp_path, pool)

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
        )
    )

    assert out.status == "completed"
    assert out.metadata["preflight"]["clarification_scope"]["status"] == "active"
    assert autopilot.last_request is not None


def test_critical_approval_scope_blocks_unapproved_continuation_files(tmp_path: Path) -> None:
    item = _item("i1")
    item.target_files = ["src/unapproved.py"]
    pool = _pool(
        [item],
        metadata={
            "critical_event": {"critical_event": True, "category": "security", "affected_files": ["src/approved.py"]},
            "critical_decision": {
                "scope": "pool",
                "decision": "approved",
                "approved_files": ["src/approved.py"],
                "approved_scope": ["src/approved.py"],
                "approved_item_ids": ["i1"],
                "bounded_continuation": True,
            },
        },
    )
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, pool)

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "critical_approval_scope_mismatch"
    assert out.metadata["preflight"]["critical_scope"]["unapproved_files"] == ["src/unapproved.py"]
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_critical_approval_scope_allows_approved_item_and_files(tmp_path: Path) -> None:
    item = _item("i1")
    item.target_files = ["src/approved.py"]
    pool = _pool(
        [item],
        metadata={
            "critical_event": {"critical_event": True, "category": "security", "affected_files": ["src/approved.py"]},
            "critical_decision": {
                "scope": "pool",
                "decision": "approved",
                "approved_files": ["src/approved.py"],
                "approved_scope": ["src/approved.py"],
                "approved_item_ids": ["i1"],
                "bounded_continuation": True,
            },
        },
    )
    svc, _storage, _proposal, autopilot = _orchestrator(tmp_path, pool)

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
        )
    )

    assert out.status == "completed"
    assert out.metadata["preflight"]["critical_scope"]["status"] == "approved_scope_valid"
    assert autopilot.last_request is not None


def test_unknown_profile_falls_back_safely_without_running(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1", selected_profile="mystery"))

    assert out.status == "stopped"
    assert out.stop_reason == "unknown_profile_fallback"
    assert "unknown_profile_fell_back_to_review_only" in out.warnings
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_autonomous_dev_agent_without_active_envelope_does_not_run(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1", selected_profile="autonomous_dev_agent"))

    assert out.status == "stopped"
    assert out.stop_reason == "selected_profile_inactive_envelope"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_active_bounded_envelope_allows_bounded_loop(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
        )
    )

    assert out.status == "completed"
    assert proposal.calls == ["i1"]
    assert autopilot.last_request is not None
    assert out.metadata["workspace_evidence"]["work_target"] == "ordinary_project"
    assert out.metadata["workspace_evidence"]["stable_runtime_mutation_performed"] is False


def test_self_improvement_without_strict_gate_stops(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            self_improvement=True,
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "self_improvement_without_strict_gate"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_self_improvement_with_strict_gate_requires_candidate_workspace(tmp_path: Path) -> None:
    envelope = {**_active_envelope(), "strict_gate_approved": True, "candidate_workspace_required": True}
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=envelope,
            self_improvement=True,
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "candidate_workspace_required"
    assert out.metadata["workspace_evidence"]["stable_runtime_mutation_performed"] is False
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_self_improvement_candidate_workspace_requires_level4_checkpoint(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    envelope = {**_active_envelope(), "strict_gate_approved": True, "candidate_workspace_required": True}
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=envelope,
            self_improvement=True,
            metadata={"candidate_workspace_path": str(candidate)},
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "stable_checkpoint_evidence_required"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_candidate_workspace_plan_uses_candidate_path_without_stable_runtime_mutation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    candidate = tmp_path / "candidate"
    repo.mkdir()
    candidate.mkdir()
    plan = create_candidate_workspace_plan(
        target_repo=repo,
        candidate_root=candidate,
        allowed_paths=["src"],
        blocked_paths=[".git"],
        stable_checkpoint_id="stable_1",
        max_files=4,
        max_risk_level="medium",
        self_improvement_scope="atlas_non_runtime",
        recovery_manifest_path=tmp_path / "recovery" / "manifest.json",
    )
    plan_path = write_candidate_workspace_plan(plan=plan, destination=tmp_path / "candidate_plan.json")
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            metadata={"candidate_workspace_plan_path": str(plan_path)},
        )
    )

    assert out.status == "completed"
    assert autopilot.last_request is not None
    assert autopilot.last_request.project_path == str(candidate.resolve())
    workspace_evidence = out.metadata["workspace_evidence"]
    assert workspace_evidence["work_target"] == "candidate_workspace"
    assert workspace_evidence["candidate_workspace_available"] is True
    assert workspace_evidence["candidate_workspace_plan_status"] == "ready"
    assert workspace_evidence["stable_runtime_mutation_performed"] is False


def test_candidate_workspace_target_without_workspace_stops(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            metadata={"work_target": "candidate_workspace"},
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "workspace_not_available"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_recovery_metadata_is_recorded_but_not_executed(tmp_path: Path) -> None:
    svc, _storage, _proposal, _autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            metadata={
                "recovery_manifest_path": "atlas/recovery/manifest.json",
                "restore_plan_ref": "atlas/recovery/restore.md",
                "rollback_plan_ref": "atlas/recovery/rollback.md",
            },
        )
    )

    recovery_evidence = out.metadata["recovery_evidence"]
    assert recovery_evidence["references"]["recovery_manifest_path"] == "atlas/recovery/manifest.json"
    assert recovery_evidence["restore_executed"] is False
    assert recovery_evidence["rollback_executed"] is False
    assert recovery_evidence["recovery_execution_performed"] is False


def test_stable_runtime_target_is_forbidden(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            metadata={"work_target": "stable_runtime"},
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "stable_runtime_mutation_forbidden"
    assert out.metadata["workspace_evidence"]["stable_runtime_mutation_enabled"] is False
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_does_not_regenerate_when_content_present(tmp_path: Path) -> None:
    item = _item("i1", metadata={"proposed_content": "already here\n"})
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([item]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == []  # content already present -> skipped
    assert out.skipped_generation_count == 1
    assert autopilot.last_request is not None


def test_stale_existing_proposal_is_regenerated_before_apply(tmp_path: Path) -> None:
    old_revision = hashlib.sha256("old\n".encode("utf-8")).hexdigest()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "i1.py").write_text("new\n", encoding="utf-8")
    item = _item(
        "i1",
        action_type="update",
        metadata={
            "proposed_content": "stale\n",
            "patch_proposal": {
                "metadata": {
                    "patch_content_available": True,
                    "base_file_revisions": {"src/i1.py": old_revision},
                },
                "proposed_content": "stale\n",
            },
        },
    )
    svc, storage, proposal, autopilot = _orchestrator(tmp_path, _pool([item]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == ["i1"]
    assert out.generated_count == 1
    assert autopilot.last_request is not None
    reloaded = storage.load_pool("pool_1").get_item("i1")
    assert reloaded is not None
    assert reloaded.metadata["proposed_content"] == "# generated i1\n"
    assert reloaded.metadata["patch_proposal_revision_mismatches"][0]["reason"] == "base_file_revision_mismatch"
    assert out.autopilot_result["metadata"]["revision_regenerations"][0]["item_id"] == "i1"


def test_blocks_on_plan_revision_required(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(
        tmp_path, _pool([_item("i1")], metadata={"plan_revision_required": True})
    )

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "blocked_safety_review"
    assert out.stop_reason == "plan_revision_required"
    assert proposal.calls == []  # never reached patch generation
    assert autopilot.last_request is None  # apply phase never ran


def test_blocks_on_approval_required_pool_status(tmp_path: Path) -> None:
    svc, _storage, _proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")], status="approval_required"))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "blocked_safety_review"
    assert out.stop_reason == "approval_required"
    assert autopilot.last_request is None


def test_skips_patch_generation_for_critical_and_delete_items(tmp_path: Path) -> None:
    items = [
        _item("crit", risk_level="critical"),
        _item("del", action_type="delete"),
        _item("ok", risk_level="medium"),
    ]
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool(items))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == ["ok"]  # only the applicable item gets a proposal
    assert out.skipped_generation_count == 2
    assert autopilot.last_request is not None  # apply still runs (engine hard-blocks crit/del)


def test_no_items_pool_short_circuits(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "no_items"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_weak_model_empty_proposal_is_not_counted(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]), produce_content=False)

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == ["i1"]
    assert out.generated_count == 0  # honest: no usable content produced
    assert out.proposal_results[0].patch_content_available is False
    assert out.status == "no_content"
    assert out.stop_reason == "no_patch_content"
    assert autopilot.last_request is None
