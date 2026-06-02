from __future__ import annotations

import json
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
    assert "no Vue authority" in body
    assert "## Recovery info" in body
    assert "## Remaining manual review steps" in body
    assert out.metadata["draft_pr_artifact"]["readiness"]["verification_evidence_present"] is True
    assert out.metadata["draft_pr_readiness"]["blocked_reasons"] == []
    assert out.metadata["draft_pr_readiness"]["draft_pr_url"] == ""


def test_no_content_patch_proposal_is_skipped_and_not_applied(tmp_path: Path) -> None:
    item = _item("empty", "src/empty.py")
    item.metadata.pop("proposed_content", None)
    svc, proposal, auto = _service(tmp_path / "no_content", _pool([item]))

    def no_content(_request) -> AtlasPatchProposalResult:
        proposal.calls.append(_request.item_id)
        return AtlasPatchProposalResult(
            pool_id=_request.pool_id,
            item_id=_request.item_id,
            run_id=_request.run_id,
            status="proposed",
            warnings=["llm_returned_no_patch"],
            metadata={"patch_content_available": False},
        )

    proposal.propose_for_item = no_content
    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_paths=["src/"],
        )
    )

    assert proposal.calls == ["empty"]
    assert auto.last_request is None
    assert out.status == "no_content"
    assert out.stop_reason == "no_patch_content"
    assert out.proposal_results[0].status == "no_content"
    assert out.proposal_results[0].patch_content_available is False
    assert out.metadata["no_content_item_ids"] == ["empty"]
    assert out.metadata["draft_pr_readiness"]["ready"] is False
    assert out.metadata["draft_pr_artifact"]["ready"] is False


def test_no_content_item_is_excluded_from_apply_when_other_patch_content_exists(tmp_path: Path) -> None:
    ready = _item("ready", "src/ready.py")
    empty = _item("empty", "src/empty.py")
    empty.metadata.pop("proposed_content", None)
    svc, proposal, auto = _service(tmp_path / "mixed_no_content", _pool([ready, empty]))

    def no_content(_request) -> AtlasPatchProposalResult:
        proposal.calls.append(_request.item_id)
        return AtlasPatchProposalResult(
            pool_id=_request.pool_id,
            item_id=_request.item_id,
            run_id=_request.run_id,
            status="proposed",
            warnings=["llm_returned_no_patch"],
            metadata={"patch_content_available": False},
        )

    proposal.propose_for_item = no_content
    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_paths=["src/"],
            item_ids=["ready", "empty"],
        )
    )

    assert proposal.calls == ["empty"]
    assert auto.last_request is not None
    assert auto.last_request.item_ids == ["ready"]
    assert out.proposal_results[0].status == "no_content"
    assert out.proposal_results[0].reason == "llm_returned_no_patch"
    assert out.status == "completed"
    assert out.metadata["draft_pr_readiness"]["ready"] is True


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
    assert "autonomous_run_not_successful" in out.metadata["draft_pr_readiness"]["blocked_reasons"]


def test_draft_pr_readiness_requires_changed_files_and_verification_evidence(tmp_path: Path) -> None:
    missing_verification = _Autopilot(
        item_results=[
            AtlasAutopilotItemResult(
                item_id="code",
                status="completed",
                changed_files=["src/fix.py"],
                verification_result={},
            )
        ]
    )
    svc, _proposal, _auto = _service(
        tmp_path / "missing_verification",
        _pool([_item("code", "src/fix.py")]),
        missing_verification,
    )
    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    assert out.status == "completed"
    assert out.metadata["draft_pr_readiness"]["ready"] is False
    assert out.metadata["draft_pr_readiness"]["changed_files_present"] is True
    assert out.metadata["draft_pr_readiness"]["verification_evidence_present"] is False
    assert "verification_evidence_required" in out.metadata["draft_pr_readiness"]["blocked_reasons"]

    missing_changes = _Autopilot(
        item_results=[
            AtlasAutopilotItemResult(
                item_id="code",
                status="completed",
                changed_files=[],
                verification_result={"status": "passed"},
            )
        ]
    )
    svc, _proposal, _auto = _service(
        tmp_path / "missing_changes",
        _pool([_item("code", "src/fix.py")]),
        missing_changes,
    )
    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    assert out.status == "completed"
    assert out.metadata["draft_pr_readiness"]["ready"] is False
    assert out.metadata["draft_pr_readiness"]["changed_files_present"] is False
    assert out.metadata["draft_pr_readiness"]["verification_evidence_present"] is True
    assert "changed_files_required" in out.metadata["draft_pr_readiness"]["blocked_reasons"]


def test_visual_verification_failure_creates_bounded_repair_plan(tmp_path: Path) -> None:
    visual_failed = _Autopilot(
        status="failed",
        item_results=[
            AtlasAutopilotItemResult(
                item_id="game",
                status="failed",
                reason="verification_failed:visual_contract_failed",
                changed_files=["index.html", "style.css"],
                verification_result={
                    "status": "failed",
                    "warnings": [
                        "visual_contract_failed",
                        "visual_missing:animation_signal",
                        "visual_missing:motion_signal",
                        "browser_smoke_failed:playwright_error: timeout",
                    ],
                },
            )
        ],
    )
    svc, _proposal, _auto = _service(tmp_path / "visual_failed", _pool([_item("game", "index.html")]), visual_failed)
    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept", max_retries=2))

    assert out.status == "failed"
    assert out.phase == "failure_analysis"
    summary = out.metadata["verification_failure_summary"]
    assert summary["user_facing_title"] == "Visual verification failed: game does not show required motion/animation evidence"
    assert "visual_missing:animation_signal" in summary["failed_contracts"]
    assert summary["verification_tool_error"].startswith("browser_smoke_failed:playwright_error")
    assert summary["can_attempt_bounded_repair"] is True
    plan = out.metadata["repair_plan"]
    assert plan["allowed_repair_files"] == ["index.html", "style.css"]
    assert plan["post_repair_verification_required"] is True
    assert out.metadata["post_repair_verification_result"]["status"] == "not_run"
    assert out.metadata["draft_pr_readiness"]["ready"] is False
    assert "post_repair_verification_required" in out.metadata["draft_pr_readiness"]["blocked_reasons"]
    assert "verification_failure_unresolved" in out.metadata["draft_pr_readiness"]["blocked_reasons"]
    status_view = _normalized_status(out.model_dump())
    assert status_view["current_phase"] == "failure_analysis"
    assert status_view["evidence_summary"]["verification_failure_summary"]["failed_contracts"]
    assert status_view["evidence_summary"]["repair_plan"]["status"] == "planned"
    assert status_view["evidence_summary"]["repair_attempts"][0]["kind"] == "bounded_repair_plan"


def test_ci_failure_evidence_blocks_draft_readiness_until_bounded_repair_verified(tmp_path: Path) -> None:
    svc, _proposal, _auto = _service(tmp_path / "ci_failure", _pool([_item("code", "tests/test_app.py")]))
    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope={**_active_envelope(), "bounds": {"allowed_paths": ["tests/"], "blocked_paths": [".git/"], "max_actions_per_loop": 4}},
            allowed_paths=["tests/"],
            metadata={
                "ci_failure_evidence": {
                    "source": "github_actions",
                    "run_id": "run-1",
                    "job_id": "job-1",
                    "failing_command": "python -m pytest -q tests/test_app.py",
                    "log_text": "FAILED tests/test_app.py::test_feature - AssertionError",
                }
            },
        )
    )

    assert out.status == "completed"
    assert out.metadata["ci_failure_evidence"]["confidence"] == "high"
    assert out.metadata["ci_repair_plan"]["status"] == "planned"
    assert out.metadata["post_ci_repair_verification_required"] is True
    assert out.metadata["draft_pr_readiness"]["ready"] is False
    assert "post_ci_repair_verification_required" in out.metadata["draft_pr_readiness"]["blocked_reasons"]
    assert "ci_failure_repair_unverified" in out.metadata["draft_pr_readiness"]["blocked_reasons"]
    status_view = _normalized_status(out.model_dump())
    assert status_view["evidence_summary"]["ci_failure_evidence"]["source"] == "github_actions"
    assert status_view["evidence_summary"]["ci_repair_plan"]["post_repair_verification_required"] is True
    assert status_view["controls"]["can_execute"] is False


def test_bounded_repair_plan_limits_files_to_allowed_changed_paths(tmp_path: Path) -> None:
    visual_failed = _Autopilot(
        status="failed",
        item_results=[
            AtlasAutopilotItemResult(
                item_id="game",
                status="failed",
                changed_files=["index.html", "style.css", "docs/note.md"],
                verification_result={"status": "failed", "warnings": ["visual_contract_failed"]},
            )
        ],
    )
    svc, _proposal, _auto = _service(tmp_path / "visual_limited", _pool([_item("game", "index.html")]), visual_failed)
    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            allowed_paths=["index.html", "style.css"],
            blocked_paths=["docs/"],
        )
    )

    assert out.metadata["repair_plan"]["allowed_repair_files"] == ["index.html", "style.css"]


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
    workspace = active.metadata["workspace_evidence"]
    assert workspace["status"] == "ready"
    assert workspace["effective_project_path"] == "/tmp/project"
    assert workspace["stable_runtime_mutation_enabled"] is False
    assert workspace["self_apply_enabled"] is False
    recovery = active.metadata["recovery_evidence"]
    assert recovery["status"]
    assert sorted(recovery["changed_files"]) == ["src/code.py", "src/doc.py"]
    assert recovery["restore_available"] is False
    assert recovery["restore_executed"] is False
    assert recovery["rollback_executed"] is False
    assert recovery["recovery_execution_performed"] is False
    safety = active.metadata["draft_pr_artifact"]["safety"]
    assert safety["direct_merge_enabled"] is False
    assert safety["remote_git_push_enabled"] is False
    assert safety["self_apply_enabled"] is False
    assert safety["stable_runtime_mutation_enabled"] is False

    candidate_root = tmp_path / "candidate_root"
    recovery_manifest = tmp_path / "recovery.json"
    svc, _proposal, auto = _service(tmp_path / "candidate_workspace", _pool([_item("code", "src/fix.py")]))
    candidate = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope={**_active_envelope(), "candidate_workspace_required": True},
            allowed_paths=["src/"],
            metadata={
                "work_target": "candidate_workspace",
                "candidate_workspace_id": "cand-1",
                "candidate_workspace_path": str(candidate_root),
                "recovery_manifest_path": str(recovery_manifest),
            },
        )
    )
    assert candidate.status == "completed"
    assert auto.last_request is not None
    assert auto.last_request.project_path == str(candidate_root)
    workspace = candidate.metadata["workspace_evidence"]
    assert workspace["status"] == "ready"
    assert workspace["candidate_workspace_id"] == "cand-1"
    assert workspace["candidate_workspace_root"] == str(candidate_root)
    assert workspace["stable_runtime_mutation_enabled"] is False
    assert workspace["self_apply_enabled"] is False
    recovery = candidate.metadata["recovery_evidence"]
    assert recovery["snapshot_manifest_path"] == str(recovery_manifest)
    assert sorted(recovery["changed_files"]) == ["src/code.py", "src/doc.py"]
    assert recovery["restore_available"] is True
    assert recovery["restore_executed"] is False
    assert recovery["rollback_executed"] is False
    status_view = _normalized_status(candidate.model_dump())
    assert status_view["evidence_summary"]["workspace"]["candidate_workspace_root"] == str(candidate_root)
    assert status_view["evidence_summary"]["recovery"]["restore_available"] is True
    assert status_view["evidence_summary"]["recovery"]["restore_executed"] is False

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


def test_preflight_path_and_verification_command_acceptance(tmp_path: Path) -> None:
    svc, _proposal, auto = _service(tmp_path / "outside_allowed", _pool([_item("code", "src/fix.py")]))
    outside = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_paths=["docs/"],
        )
    )
    assert outside.status == "stopped"
    assert outside.stop_reason == "path_outside_allowed_paths"
    assert outside.metadata["preflight"]["paths"] == ["src/fix.py"]
    assert auto.last_request is None

    svc, _proposal, auto = _service(tmp_path / "blocked_path", _pool([_item("code", "src/fix.py")]))
    blocked = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            blocked_paths=["src/"],
        )
    )
    assert blocked.status == "stopped"
    assert blocked.stop_reason == "blocked_path"
    assert blocked.metadata["preflight"]["paths"] == ["src/fix.py"]
    assert auto.last_request is None

    svc, _proposal, auto = _service(tmp_path / "expanded_allowed", _pool([_item("code", "src/fix.py")]))
    expanded = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope={**_active_envelope(), "bounds": {"allowed_paths": ["src/"], "max_actions_per_loop": 4}},
            allowed_paths=["src/", "docs/"],
        )
    )
    assert expanded.status == "stopped"
    assert expanded.stop_reason == "allowed_paths_expand_envelope"
    assert expanded.metadata["preflight"]["requested_allowed_paths"] == ["src/", "docs/"]
    assert auto.last_request is None

    svc, _proposal, auto = _service(tmp_path / "verification_commands", _pool([_item("code", "src/fix.py")]))
    commands = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_verification_commands=["pytest tests/test_atlas.py"],
        )
    )
    assert commands.status == "stopped"
    assert commands.stop_reason == "allowed_verification_commands_unsupported"
    assert commands.metadata["preflight"]["allowed_verification_commands"] == ["pytest tests/test_atlas.py"]
    assert auto.last_request is None


def test_critical_approval_scope_acceptance_blocks_unapproved_continuation(tmp_path: Path) -> None:
    event = normalize_critical_event(category="security", affected_files=["src/approved.py"])
    item = _item("crit", "src/unapproved.py", risk_level="critical")
    pool = _pool(
        [item],
        metadata={
            "critical_event": event,
            "critical_decision": {
                "scope": "pool",
                "decision": "approved",
                "approved_files": ["src/approved.py"],
                "approved_paths": ["src/approved.py"],
                "approved_item_ids": ["crit"],
                "bounded_continuation": True,
            },
        },
    )
    svc, proposal, auto = _service(tmp_path, pool)

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "critical_approval_scope_mismatch"
    critical_scope = out.metadata["preflight"]["critical_scope"]
    assert critical_scope["approved_files"] == ["src/approved.py"]
    assert critical_scope["unapproved_files"] == ["src/unapproved.py"]
    assert proposal.calls == []
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


def test_ui_status_hides_execution_controls_for_safety_blocks(tmp_path: Path) -> None:
    clarification = _pool(
        [_item("amb", "src/a.py")],
        status="needs_scope_confirmation",
        metadata={
            "clarification_required": True,
            "pending_question_count": 1,
            "clarification_questions": [{"question_id": "q1", "status": "pending"}],
        },
    )
    svc, _proposal, _auto = _service(tmp_path / "clarification", clarification)
    blocked = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    status_view = _normalized_status(blocked.model_dump())
    assert status_view["decision_targets"]["clarification"]["required"] is True
    assert status_view["controls"]["can_execute"] is False
    assert status_view["controls"]["can_continue"] is False
    assert status_view["controls"]["execute_apply_visible"] is False
    assert status_view["next_action"] == "Answer remaining clarification"

    critical_item = _item("crit", "src/security.py", status="waiting_for_critical_decision", risk_level="critical")
    critical_pool = _pool([critical_item], status="waiting_for_critical_decision")
    svc, _proposal, _auto = _service(tmp_path / "critical_ui", critical_pool)
    blocked = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
        )
    )
    status_view = _normalized_status(blocked.model_dump())
    assert status_view["decision_targets"]["critical_event"]["required"] is True
    assert status_view["controls"]["can_execute"] is False
    assert status_view["controls"]["can_continue"] is False
    assert status_view["controls"]["execute_apply_visible"] is False
    assert status_view["next_action"] == "Make critical event decision"


def test_manifest_truthfulness_acceptance_flags_remain_corrective_checkpoint() -> None:
    manifest = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))

    assert manifest["practical_full_automation_truthfulness_status"] == "corrective_checkpoint_in_progress"
    assert manifest["practical_full_automation_acceptance_tests"] == "tests/test_atlas_practical_full_automation_acceptance.py"
    assert manifest["practical_full_automation_complete"] is False
    assert manifest["ui_practical_experience_complete"] is False
    assert manifest["stable_runtime_mutation_apply_complete"] is False
    assert manifest["self_improvement_practical_loop_complete"] is False


def test_practical_full_automation_e2e_acceptance_matrix_preserves_blockers(tmp_path: Path) -> None:
    happy_items = [_item("doc", "docs/atlas.md"), _item("code", "src/fix.py")]
    svc, proposal, auto = _service(tmp_path / "happy", _pool(happy_items))
    happy = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_paths=["docs/", "src/"],
        )
    )
    happy_status = _normalized_status(happy.model_dump())
    assert happy.status == "completed"
    assert proposal.calls == []
    assert auto.last_request is not None
    assert sorted(happy.metadata["changed_files"]) == ["src/code.py", "src/doc.py"]
    assert happy_status["evidence_summary"]["final_summary"]["draft_pr_ready"] is True
    assert happy_status["controls"]["can_execute"] is False

    clarification_pool = _pool(
        [_item("amb", "src/a.py")],
        status="needs_scope_confirmation",
        metadata={"clarification_required": True, "clarification_questions": [{"question_id": "q1", "status": "pending"}]},
    )
    svc, proposal, auto = _service(tmp_path / "clarification_matrix", clarification_pool)
    clarification = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    clarification_status = _normalized_status(clarification.model_dump())
    assert clarification.stop_reason == "clarification_required"
    assert proposal.calls == []
    assert auto.last_request is None
    assert clarification_status["controls"]["can_answer_clarification"] is True
    assert clarification_status["controls"]["can_execute"] is False

    critical_item = _item("crit", "src/security.py", status="waiting_for_critical_decision", risk_level="critical")
    critical_pool = _pool([critical_item], status="waiting_for_critical_decision")
    svc, proposal, auto = _service(tmp_path / "critical_matrix", critical_pool)
    critical = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept"))
    critical_status = _normalized_status(critical.model_dump())
    assert critical.stop_reason == "critical_event_waiting_for_user_decision"
    assert proposal.calls == []
    assert auto.last_request is None
    assert critical_status["controls"]["can_approve_critical_event"] is True
    assert critical_status["controls"]["can_execute"] is False

    visual_failed = _Autopilot(
        status="failed",
        item_results=[
            AtlasAutopilotItemResult(
                item_id="game",
                status="failed",
                reason="verification_failed:visual_contract_failed",
                changed_files=["index.html"],
                verification_result={"status": "failed", "warnings": ["visual_contract_failed", "visual_missing:motion_signal"]},
            )
        ],
    )
    svc, _proposal, _auto = _service(tmp_path / "visual_matrix", _pool([_item("game", "index.html")]), visual_failed)
    visual = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_accept", max_retries=1))
    assert visual.phase == "failure_analysis"
    assert visual.metadata["repair_plan"]["post_repair_verification_required"] is True
    assert visual.metadata["draft_pr_readiness"]["ready"] is False

    svc, proposal, auto = _service(tmp_path / "path_matrix", _pool([_item("blocked", "src/blocked.py")]))
    path_blocked = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_accept",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            allowed_paths=["docs/"],
        )
    )
    assert path_blocked.stop_reason == "path_outside_allowed_paths"
    assert proposal.calls == []
    assert auto.last_request is None

    manifest = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    policy = Path("docs/atlas_autonomous_execution_readiness_policy.md").read_text(encoding="utf-8")
    assert manifest["practical_full_automation_complete"] is False
    assert manifest["direct_merge_enabled"] is False
    assert manifest["remote_git_push_enabled"] is False
    assert manifest["self_apply_enabled"] is False
    assert manifest["vue_source_of_truth"] is False
    assert "critical events always require user judgment" in policy.lower()
