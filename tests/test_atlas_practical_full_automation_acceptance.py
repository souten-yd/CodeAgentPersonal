from __future__ import annotations

from pathlib import Path

from agent.atlas_approval_service import AtlasApprovalService
from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_critical_event_policy import normalize_critical_event
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import (
    AtlasAutopilotItemResult,
    AtlasMultiItemAutopilotRequest,
    AtlasMultiItemAutopilotResult,
)
from agent.atlas_patch_proposal_schema import AtlasPatchProposalResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from app.api.atlas_autonomous_codegen import _normalized_status


def _item(item_id: str, path: str, *, status: str = "ready", risk_level: str = "low") -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_accept",
        title=f"Item {item_id}",
        goal=f"Change {path}",
        item_type="implementation",
        status=status,
        risk_level=risk_level,
        target_files=[path],
        rollback_plan=[f"Restore {path} from snapshot."],
        metadata={"action_type": "modify", "proposed_content": f"# {item_id}\n"},
    )


def _pool(items: list[AtlasPlanItem], *, status: str = "ready", metadata: dict | None = None) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_accept",
        root_goal="Implement practical Atlas acceptance flow",
        project_path="/tmp/project",
        status=status,
        items=items,
        metadata=metadata or {},
    )


def _active_envelope() -> dict:
    return {
        "envelope_id": "pre_authorized_bounded_dev_envelope",
        "status": "active",
        "bounds": {"allowed_paths": ["docs/", "src/"], "blocked_paths": [".git/"], "max_actions_per_loop": 4},
    }


class _Proposal:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def propose_for_item(self, request) -> AtlasPatchProposalResult:
        self.calls.append(request.item_id)
        return AtlasPatchProposalResult(
            pool_id=request.pool_id,
            item_id=request.item_id,
            run_id=request.run_id,
            status="proposed",
            metadata={"patch_content_available": True},
        )


class _Autopilot:
    def __init__(self, *, status: str = "completed", item_results: list[AtlasAutopilotItemResult] | None = None) -> None:
        self.status = status
        self.item_results = item_results or []
        self.last_request: AtlasMultiItemAutopilotRequest | None = None

    def run(self, request: AtlasMultiItemAutopilotRequest) -> AtlasMultiItemAutopilotResult:
        self.last_request = request
        results = self.item_results or [
            AtlasAutopilotItemResult(
                item_id=item_id,
                status="completed" if self.status in {"completed", "partial"} else "failed",
                changed_files=[f"src/{item_id}.py"],
                verification_result={"status": "passed" if self.status in {"completed", "partial"} else "failed"},
            )
            for item_id in (request.item_ids or ["doc", "code"])
        ]
        return AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id,
            run_id=request.run_id,
            autopilot_run_id="auto_accept",
            policy_id=request.policy_id,
            status=self.status,
            processed_count=len(results),
            completed_count=sum(1 for item in results if item.status == "completed"),
            failed_count=sum(1 for item in results if item.status == "failed"),
            item_results=results,
            created_at="2026-06-01T00:00:00+00:00",
        )


def _service(tmp_path: Path, pool: AtlasPlanPool, autopilot: _Autopilot | None = None) -> tuple[AtlasAutonomousCodegenOrchestratorService, _Proposal, _Autopilot]:
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    journal = AtlasJournal(tmp_path, workspace_id="default")
    proposal = _Proposal()
    auto = autopilot or _Autopilot()
    return (
        AtlasAutonomousCodegenOrchestratorService(
            storage=storage,
            journal=journal,
            patch_proposal_service=proposal,
            multi_item_autopilot_service=auto,
            data_root=tmp_path,
        ),
        proposal,
        auto,
    )


class _Journal:
    def plan_pool_dir(self, pool_id: str) -> str:
        path = Path("/tmp") / pool_id
        path.mkdir(parents=True, exist_ok=True)
        return str(path)


def test_simple_doc_and_code_fix_complete_with_evidence_backed_pr_artifact(tmp_path: Path) -> None:
    items = [_item("doc", "docs/atlas.md"), _item("code", "src/fix.py")]
    svc, _proposal, auto = _service(tmp_path, _pool(items))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_paths=["docs/", "src/"],
        )
    )

    assert out.status == "completed"
    assert auto.last_request is not None
    assert out.metadata["draft_pr_readiness"]["ready"] is True
    assert out.metadata["draft_pr_readiness"]["direct_merge_enabled"] is False
    assert out.metadata["draft_pr_readiness"]["remote_git_push_enabled"] is False
    body = Path(out.metadata["draft_pr_artifact"]["body_path"]).read_text(encoding="utf-8")
    assert "## Tests / verification" in body
    assert "## Safety constraints" in body
    assert "no remote git push" in body


def test_ambiguous_and_critical_plans_block_before_implementation(tmp_path: Path) -> None:
    svc, proposal, auto = _service(tmp_path, _pool([_item("amb", "src/a.py")], status="needs_scope_confirmation"))
    ambiguous = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    assert ambiguous.status == "blocked_safety_review"
    assert ambiguous.phase == "needs_scope_confirmation"
    assert ambiguous.stop_reason == "clarification_required"
    assert proposal.calls == []
    assert auto.last_request is None

    critical_item = _item("crit", "src/security.py", status="waiting_for_critical_decision", risk_level="critical")
    critical = _pool([critical_item], status="waiting_for_critical_decision")
    svc, proposal, auto = _service(tmp_path / "critical", critical)
    blocked = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    assert blocked.status == "blocked_safety_review"
    assert blocked.phase == "waiting_for_critical_decision"
    assert blocked.stop_reason == "critical_event_waiting_for_user_decision"
    assert proposal.calls == []
    assert auto.last_request is None


def test_rejected_critical_path_creates_lower_impact_candidate_with_gate_rerun_markers() -> None:
    event = normalize_critical_event(category="security", affected_files=["src/security.py"])
    item = _item("crit", "src/security.py", status="waiting_for_critical_decision", risk_level="critical")
    item.target_files = ["src/security.py", "src/extra.py"]
    item.metadata["critical_event"] = event
    pool = _pool([item], status="waiting_for_critical_decision")

    AtlasApprovalService(_Journal()).decide(
        pool,
        item_id="crit",
        run_id="run_1",
        decision="rejected",
        reason="NG safer path",
        approver="tester",
        metadata={},
    )

    revised = pool.get_item(item.metadata["lower_impact_revised_item_id"])
    assert item.metadata["original_path_blocked"] is True
    assert revised is not None
    assert revised.metadata["lower_impact_revised_candidate"] is True
    assert revised.metadata["requires_critique_gate_rerun"] is True
    assert revised.metadata["requires_policy_gate_rerun"] is True
    assert revised.metadata["gate_rerun_performed"] is True
    assert revised.target_files == ["src/security.py"]


def test_verification_failure_repair_is_visible_and_failed_run_is_not_pr_ready(tmp_path: Path) -> None:
    repaired = _Autopilot(
        item_results=[
            AtlasAutopilotItemResult(
                item_id="code",
                status="completed",
                changed_files=["src/fix.py"],
                verification_result={"status": "passed", "recovered_by_self_correction": True},
                metadata={"self_correction_result": {"status": "recovered", "attempts": 2}},
            )
        ]
    )
    svc, _proposal, _auto = _service(tmp_path / "repaired", _pool([_item("code", "src/fix.py")]), repaired)
    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    status_view = _normalized_status(out.model_dump())
    assert status_view["evidence_summary"]["verification"]["statuses"]["passed"] == 1
    assert status_view["evidence_summary"]["repair_attempts"][0]["kind"] == "self_correction_result"

    failed = _Autopilot(status="failed")
    svc, _proposal, _auto = _service(tmp_path / "failed", _pool([_item("code", "src/fix.py")]), failed)
    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    assert out.status == "failed"
    assert out.metadata["draft_pr_readiness"]["ready"] is False
    assert out.metadata["draft_pr_artifact"]["ready"] is False


def test_envelope_and_forbidden_operation_acceptance(tmp_path: Path) -> None:
    svc, _proposal, auto = _service(tmp_path / "no_envelope", _pool([_item("code", "src/fix.py")]))
    no_envelope = svc.run(
        AtlasAutonomousCodegenRequest(pool_id="pool_accept", selected_profile="autonomous_dev_agent")
    )
    assert no_envelope.status == "stopped"
    assert no_envelope.stop_reason == "selected_profile_inactive_envelope"
    assert auto.last_request is None

    svc, _proposal, auto = _service(tmp_path / "with_envelope", _pool([_item("code", "src/fix.py")]))
    active = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_paths=["src/"],
        )
    )
    assert active.status == "completed"
    assert auto.last_request is not None
    safety = active.metadata["draft_pr_artifact"]["safety"]
    assert safety["direct_merge_enabled"] is False
    assert safety["remote_git_push_enabled"] is False
    assert safety["self_apply_enabled"] is False
    assert safety["stable_runtime_mutation_enabled"] is False

    svc, _proposal, auto = _service(tmp_path / "self_improvement", _pool([_item("code", "src/fix.py")]))
    self_improvement = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope={**_active_envelope(), "strict_gate_approved": True},
            self_improvement=True,
        )
    )
    assert self_improvement.status == "stopped"
    assert self_improvement.stop_reason == "candidate_workspace_required"
    assert auto.last_request is None

    svc, _proposal, auto = _service(tmp_path / "stable_runtime", _pool([_item("code", "src/fix.py")]))
    stable = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept", metadata={"work_target": "stable_runtime"}))
    assert stable.status == "stopped"
    assert stable.stop_reason == "stable_runtime_mutation_forbidden"
    assert auto.last_request is None


def test_ui_api_state_reports_decisions_verification_repair_and_final_summary(tmp_path: Path) -> None:
    autopilot = _Autopilot(
        item_results=[
            AtlasAutopilotItemResult(
                item_id="code",
                status="completed",
                changed_files=["src/fix.py"],
                verification_result={"status": "passed"},
                metadata={"bounded_retry_result": {"status": "recovered"}},
            )
        ]
    )
    svc, _proposal, _auto = _service(tmp_path, _pool([_item("code", "src/fix.py")]), autopilot)
    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    status_view = _normalized_status(out.model_dump())

    assert status_view["current_phase"] == "final_summary"
    assert status_view["evidence_summary"]["verification"]["visible"] is True
    assert status_view["evidence_summary"]["repair_attempts"]
    assert status_view["evidence_summary"]["final_summary"]["draft_pr_ready"] is True
    assert status_view["controls"]["execute_apply_visible"] is False
    assert status_view["raw_json_included"] is False
