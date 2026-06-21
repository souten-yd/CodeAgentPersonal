from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from agent.atlas_plan_item_file_changes import validate_protected_relative_path
from agent.model_forge.schema import ForgeModel
from agent.model_forge.twin_assist_contracts import TwinAssistEvaluationReport
from agent.model_forge.twin_assist_eval_packs import load_twin_assist_cases
from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.pipeline_integration import evaluate_twin_post_apply
from agent.twin_control_plane.proof_ledger import ProofLedgerEntry, ProofLedgerStore


class PostApplyE2ERequest(ForgeModel):
    provider_id: str
    model_id: str
    twin_assist_report_path: str
    project_fixture_root: str = "tests/fixtures/twin_assist"
    case_ids: list[str] = Field(default_factory=list)
    apply_mode: str = "isolated"
    run_tests: bool = True
    timeout_seconds: float = Field(default=180.0, gt=0)


class PostApplyE2EAttempt(ForgeModel):
    case_id: str
    candidate_id: str
    assist_mode: str
    status: str
    proposal_score: float | None = None
    apply_status: str = ""
    changed_files: list[str] = Field(default_factory=list)
    focused_tests: list[str] = Field(default_factory=list)
    test_status: str = ""
    post_apply_twin_status: str = ""
    proof_ledger_ref: str = ""
    rollback_available: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    failed_reasons: list[str] = Field(default_factory=list)
    unavailable_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class PostApplyE2EReport(ForgeModel):
    report_id: str
    provider_id: str
    model_id: str
    attempts: list[PostApplyE2EAttempt]
    aggregate_scores: dict[str, float] = Field(default_factory=dict)
    recommended_policy_patch: dict = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = ""


class PostApplyE2ERunner:
    def __init__(self, evidence_root: str | Path) -> None:
        self.root = Path(evidence_root)

    def run(self, request: PostApplyE2ERequest) -> PostApplyE2EReport:
        if request.apply_mode != "isolated":
            raise ValueError("direct_workspace_apply_forbidden")
        source_report = TwinAssistEvaluationReport.model_validate_json(Path(request.twin_assist_report_path).read_text(encoding="utf-8"))
        requested = set(request.case_ids or [item.case_id for item in source_report.comparisons])
        cases = {case.case_id: case for case in load_twin_assist_cases(requested)}
        report_id = "postapply_" + uuid4().hex[:12]; report_root = self.root / report_id; report_root.mkdir(parents=True)
        attempts = []
        for comparison in source_report.comparisons:
            if comparison.case_id not in requested: continue
            selected = [comparison.baseline] if comparison.baseline else []
            best = next((item for item in comparison.assisted if item.assist_mode == comparison.best_assist_mode), None)
            if best: selected.append(best)
            for attempt in selected:
                attempts.append(self._run_attempt(request, cases[comparison.case_id], attempt, report_root))
        by_case = {}
        for attempt in attempts: by_case.setdefault(attempt.case_id, []).append(attempt)
        lifts = []; harms = 0
        for values in by_case.values():
            baseline = next((item for item in values if item.assist_mode == "none"), None)
            assisted = next((item for item in values if item.assist_mode != "none"), None)
            if baseline and assisted:
                b = 1.0 if baseline.status == "passed" else 0.0; a = 1.0 if assisted.status == "passed" else 0.0
                lifts.append(a - b); harms += int(a < b)
        aggregate = {"e2e_mean_lift": round(sum(lifts) / len(lifts), 4) if lifts else 0.0, "e2e_harm_rate": round(harms / len(lifts), 4) if lifts else 0.0, "attempt_count": float(len(attempts))}
        report = PostApplyE2EReport(report_id=report_id, provider_id=request.provider_id, model_id=request.model_id, attempts=attempts, aggregate_scores=aggregate, evidence_refs=[str(report_root / "report.json")], created_at=datetime.now(timezone.utc).isoformat())
        (report_root / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report

    def _run_attempt(self, request, case, attempt, report_root: Path) -> PostApplyE2EAttempt:
        key = f"{case.case_id}__{attempt.assist_mode.value}"; root = report_root / key; workspace = root / "workspace"
        shutil.copytree(Path(request.project_fixture_root) / case.project_fixture_id, workspace)
        if not attempt.proposal_ref or not Path(attempt.proposal_ref).is_file():
            return PostApplyE2EAttempt(case_id=case.case_id, candidate_id=key, assist_mode=attempt.assist_mode.value, status="unavailable", proposal_score=attempt.score, unavailable_reasons=["proposal_evidence_unavailable"])
        proposal = json.loads(Path(attempt.proposal_ref).read_text(encoding="utf-8")); meta = proposal.get("metadata") or {}; changes = meta.get("file_changes") or []
        change_set = meta.get("change_set") or {}
        if change_set.get("apply_strategy") != "preflight_all_then_apply_all" or change_set.get("partial_apply_allowed") is not False:
            return PostApplyE2EAttempt(case_id=case.case_id, candidate_id=key, assist_mode=attempt.assist_mode.value, status="blocked", proposal_score=attempt.score, apply_status="blocked", blocked_reasons=["safe_apply_contract_missing"])
        backups = {}; normalized = []
        for change in changes:
            path = str(change.get("path") or ""); ok, reason, _ = validate_protected_relative_path(path); target = (workspace / path).resolve()
            if not ok or workspace.resolve() not in target.parents or path not in case.target_files:
                return PostApplyE2EAttempt(case_id=case.case_id, candidate_id=key, assist_mode=attempt.assist_mode.value, status="blocked", proposal_score=attempt.score, apply_status="blocked", blocked_reasons=[reason or "target_outside_isolated_scope"])
            content = change.get("proposed_content")
            if not isinstance(content, str):
                return PostApplyE2EAttempt(case_id=case.case_id, candidate_id=key, assist_mode=attempt.assist_mode.value, status="blocked", proposal_score=attempt.score, apply_status="blocked", blocked_reasons=["full_content_required_for_isolated_mvp"])
            backups[path] = target.read_bytes() if target.is_file() else None; normalized.append((path, target, content))
        if not normalized:
            return PostApplyE2EAttempt(case_id=case.case_id, candidate_id=key, assist_mode=attempt.assist_mode.value, status="unavailable", proposal_score=attempt.score, unavailable_reasons=["file_changes_unavailable"])
        snapshot = {path: (hashlib.sha256(data).hexdigest() if data is not None else "missing") for path, data in backups.items()}
        root.mkdir(parents=True, exist_ok=True); snapshot_path = root / "rollback_snapshot.json"; snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        for _path, target, content in normalized: target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content, encoding="utf-8")
        tests = [test for test in case.expected_tests if (workspace / test).is_file()]
        if not request.run_tests or not tests:
            test_status = "unavailable"; verification = [{"evidence_id": "focused_tests", "status": "unavailable"}]; test_ref = ""
        else:
            completed = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], cwd=workspace, capture_output=True, text=True, timeout=request.timeout_seconds, check=False)
            test_status = "passed" if completed.returncode == 0 else "failed"; test_ref = str(root / "focused_tests.txt"); Path(test_ref).write_text(completed.stdout + completed.stderr, encoding="utf-8"); verification = [{"evidence_id": test_ref, "status": test_status}]
        gate = evaluate_twin_post_apply(mode=PipelineMode.SHADOW, blocking=True, block_unverified=True, requirement=case.user_goal, pool_id=key, project_path=str(workspace), changed_files=[item[0] for item in normalized], verification=verification, requirement_ref=case.case_id, plan_item_ref=key, model_id=request.model_id, provider_id=request.provider_id)
        entry_dump = gate.get("ledger_entry"); ledger_ref = ""
        if entry_dump:
            entry = ProofLedgerEntry.model_validate(entry_dump); ProofLedgerStore(root / "proof_ledger").append(entry, ledger_id="postapply"); ledger_ref = entry.entry_id
        passed = test_status == "passed" and gate.get("accepted") and not gate.get("gate_blocked")
        status = "passed" if passed else ("unavailable" if test_status == "unavailable" else "failed")
        failure_reasons = [] if passed or status == "unavailable" else [
            *[str(value) for value in gate.get("blocked_reasons") or []],
            *[str(value) for value in gate.get("repair_reasons") or []],
        ]
        if not passed and status != "unavailable" and not failure_reasons:
            failure_reasons = [str(gate.get("block_reason") or f"post_apply_twin:{gate.get('decision') or 'unavailable'}")]
        return PostApplyE2EAttempt(case_id=case.case_id, candidate_id=key, assist_mode=attempt.assist_mode.value, status=status, proposal_score=attempt.score, apply_status="isolated_applied", changed_files=[item[0] for item in normalized], focused_tests=tests, test_status=test_status, post_apply_twin_status=str(gate.get("decision") or "unavailable"), proof_ledger_ref=ledger_ref, rollback_available=snapshot_path.is_file(), failed_reasons=failure_reasons, unavailable_reasons=(["focused_tests_unavailable"] if test_status == "unavailable" else []), evidence_refs=[ref for ref in [attempt.proposal_ref, str(snapshot_path), test_ref] if ref])
