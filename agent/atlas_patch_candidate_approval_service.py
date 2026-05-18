from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_candidate_approval_policies import get_patch_candidate_approval_policy
from agent.atlas_patch_candidate_approval_schema import AtlasPatchCandidateApprovalRequest, AtlasPatchCandidateApprovalResult, AtlasSafeApplyHandoff
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


class AtlasPatchCandidateApprovalService:
    def __init__(self, *, storage: AtlasPlanPoolStorage | None = None, journal: AtlasJournal | None = None, gate: AtlasAutomationGateService | None = None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))
        self.gate = gate or AtlasAutomationGateService()

    def decide(self, request: AtlasPatchCandidateApprovalRequest) -> AtlasPatchCandidateApprovalResult:
        approval_run_id = f"approval_{uuid4().hex[:12]}"
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        if item is None:
            return AtlasPatchCandidateApprovalResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, regen_run_id=request.regen_run_id, proposal_id=request.proposal_id, approval_run_id=approval_run_id, policy_id=request.policy_id, status="blocked", decision=request.decision, reviewer=request.reviewer, warnings=["item_not_found"])
        policy = get_patch_candidate_approval_policy(request.policy_id)
        self._emit(request, approval_run_id, "patch_candidate_approval_started", item.item_id, "started", [])
        result = self._do_decide(request, approval_run_id, pool, item, policy)
        self._save_result(result)
        return result

    def _do_decide(self, request, approval_run_id, pool, item, policy):
        regen_path = Path("ca_data") / "atlas" / "patch_regen" / validate_relative_path(request.pool_id) / f"{validate_relative_path(request.regen_run_id)}.json"
        if not request.regen_run_id.startswith("regen_") or not regen_path.exists():
            return self._blocked(request, approval_run_id, "regen_result_not_found")
        regen = json.loads(regen_path.read_text(encoding="utf-8"))
        cand = dict(regen.get("candidate") or {})
        if request.proposal_id and request.proposal_id != str(cand.get("proposal_id") or ""):
            return self._blocked(request, approval_run_id, "proposal_id_mismatch")
        if request.decision != "approve":
            self._update_item(item, request, None)
            self.storage.save_pool(pool); self.journal.save_plan_pool(pool)
            status = "rejected" if request.decision == "reject" else "request_changes"
            self._emit(request, approval_run_id, f"patch_candidate_{'rejected' if status=='rejected' else 'changes_requested'}", item.item_id, status, [])
            return AtlasPatchCandidateApprovalResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, regen_run_id=request.regen_run_id, proposal_id=str(cand.get("proposal_id") or request.proposal_id), approval_run_id=approval_run_id, policy_id=policy.policy_id, status=status, decision=request.decision, reviewer=request.reviewer, reason=request.reason)
        warnings = []
        if regen.get("status") != "proposal_ready" or cand.get("status") != "proposal_ready": warnings.append("status_not_proposal_ready")
        if cand.get("patch_format") != "unified_diff" or not str(cand.get("patch") or "").strip(): warnings.append("invalid_patch_format_or_empty")
        if len(str(cand.get("patch") or "")) > policy.max_patch_chars: warnings.append("patch_too_large")
        tf = list(cand.get("target_files") or [])
        if not tf or len(tf) > policy.max_target_files: warnings.append("invalid_target_files")
        if list((regen.get("candidate") or {}).get("target_files") or []) != tf: warnings.append("target_files_mismatch")
        if list(cand.get("errors") or []): warnings.append("candidate_errors_present")
        if "secret_like_content_detected" in list(cand.get("warnings") or []): warnings.append("secret_warning")
        if warnings:
            self._emit(request, approval_run_id, "patch_candidate_approval_blocked", item.item_id, "blocked", warnings)
            return AtlasPatchCandidateApprovalResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, regen_run_id=request.regen_run_id, proposal_id=str(cand.get("proposal_id") or ""), approval_run_id=approval_run_id, policy_id=policy.policy_id, status="blocked", decision=request.decision, reviewer=request.reviewer, warnings=warnings)
        decision = self.gate.decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()["guarded_low_risk"])
        gate_payload = {"decision": decision.decision, "reasons": list(decision.reasons), "risk_level": (decision.metadata or {}).get("risk_level", ""), "metadata": dict(decision.metadata or {})}
        if decision.decision != "allow" or (decision.metadata or {}).get("risk_level") in {"medium", "high"}:
            return AtlasPatchCandidateApprovalResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, regen_run_id=request.regen_run_id, proposal_id=str(cand.get("proposal_id") or ""), approval_run_id=approval_run_id, policy_id=policy.policy_id, status="blocked", decision=request.decision, reviewer=request.reviewer, warnings=["automation_gate_blocked"], metadata={"gate_decision": gate_payload})
        handoff = self._create_handoff(request, approval_run_id, cand, gate_payload, regen_path)
        self._update_item(item, request, handoff)
        self.storage.save_pool(pool); self.journal.save_plan_pool(pool)
        self._emit(request, approval_run_id, "patch_candidate_approved", item.item_id, "approved", [])
        self._emit(request, approval_run_id, "safe_apply_handoff_created", item.item_id, "ready", [])
        return AtlasPatchCandidateApprovalResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, regen_run_id=request.regen_run_id, proposal_id=str(cand.get("proposal_id") or ""), approval_run_id=approval_run_id, policy_id=policy.policy_id, status="approved", decision=request.decision, reviewer=request.reviewer, reason=request.reason, handoff=handoff)

    def _update_item(self, item, request, handoff):
        md = item.metadata or {}
        cands = list(md.get("patch_regen_candidates") or [])
        for c in cands:
            if c.get("regen_run_id") == request.regen_run_id and (not request.proposal_id or c.get("proposal_id") == request.proposal_id):
                if request.decision == "approve":
                    c.update({"approval_status": "approved", "approved_at": datetime.now(timezone.utc).isoformat(), "approved_by": request.reviewer, "approval_reason": request.reason, "handoff_id": handoff.handoff_id if handoff else "", "safe_apply_ready": True, "safe_apply_executed": False})
                elif request.decision == "reject": c.update({"approval_status": "rejected", "reviewed_by": request.reviewer, "review_reason": request.reason, "safe_apply_ready": False})
                else: c.update({"approval_status": "request_changes", "reviewed_by": request.reviewer, "review_reason": request.reason, "safe_apply_ready": False})
        md["patch_regen_candidates"] = cands
        if handoff:
            s = list(md.get("safe_apply_handoffs") or [])
            s.append({"handoff_id": handoff.handoff_id, "regen_run_id": request.regen_run_id, "proposal_id": handoff.proposal_id, "approval_status": "approved", "safe_apply_ready": True, "safe_apply_executed": False, "target_files": handoff.target_files, "created_at": datetime.now(timezone.utc).isoformat(), "handoff_path": f"ca_data/atlas/safe_apply_handoffs/{request.pool_id}/{handoff.handoff_id}.json"})
            md["safe_apply_handoffs"] = s
        item.metadata = md

    def _create_handoff(self, request, approval_run_id, cand, gate_payload, regen_path):
        hid = f"handoff_{uuid4().hex[:12]}"; now = datetime.now(timezone.utc).isoformat()
        handoff = AtlasSafeApplyHandoff(handoff_id=hid, status="ready", pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, regen_run_id=request.regen_run_id, proposal_id=str(cand.get("proposal_id") or ""), patch=str(cand.get("patch") or ""), patch_format="unified_diff", target_files=list(cand.get("target_files") or []), approval_status="approved", safe_apply_ready=True, safe_apply_executed=False, verification_executed=False, gate_decision=gate_payload, metadata={"approval_run_id": approval_run_id, "reviewer": request.reviewer, "policy_id": request.policy_id, "original_regen_result_path": str(regen_path)})
        root = Path("ca_data") / "atlas" / "safe_apply_handoffs" / request.pool_id; root.mkdir(parents=True, exist_ok=True)
        (root / f"{hid}.json").write_text(json.dumps({**handoff.model_dump(), "created_at": now}, ensure_ascii=False, indent=2), encoding="utf-8")
        preview = handoff.patch[:3000].replace("sk-", "[REDACTED]-")
        (root / f"{hid}.md").write_text(f"# Safe Apply Handoff\n\n- handoff_id: {hid}\n- safe_apply_executed: false\n- verification_executed: false\n\n## Patch Preview\n\n```diff\n{preview}\n```\n\n## Safety\n- manual approval recorded: true\n- safe_apply executed: false\n- verification executed: false\n- rollback executed: false\n- restore executed: false\n- debug review executed: false\n", encoding="utf-8")
        return handoff

    def _save_result(self, result):
        root = Path("ca_data") / "atlas" / "patch_candidate_approvals" / result.pool_id; root.mkdir(parents=True, exist_ok=True)
        (root / f"{result.approval_run_id}.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (root / f"{result.approval_run_id}.md").write_text(f"# Patch Candidate Approval\n\n- approval_run_id: {result.approval_run_id}\n- status: {result.status}\n- decision: {result.decision}\n- safe_apply executed: false\n", encoding="utf-8")

    def _emit(self, request, approval_run_id, event_type, item_id, status, warnings):
        if not request.run_id: return
        self.journal.append_event(request.pool_id, request.run_id, {"event_type": event_type, "approval_run_id": approval_run_id, "pool_id": request.pool_id, "item_id": item_id, "run_id": request.run_id, "regen_run_id": request.regen_run_id, "proposal_id": request.proposal_id, "decision": request.decision, "status": status, "reviewer": request.reviewer, "warnings": list(warnings or []), "errors": [], "safe_apply_executed": False, "created_at": datetime.now(timezone.utc).isoformat()})

    def _blocked(self, request, approval_run_id, reason):
        return AtlasPatchCandidateApprovalResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, regen_run_id=request.regen_run_id, proposal_id=request.proposal_id, approval_run_id=approval_run_id, policy_id=request.policy_id, status="blocked", decision=request.decision, reviewer=request.reviewer, warnings=[reason])
