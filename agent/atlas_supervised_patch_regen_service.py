from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_journal import AtlasJournal
from agent.atlas_supervised_patch_regen_client import AtlasPatchRegenNullLLMClient
from agent.atlas_supervised_patch_regen_policies import get_patch_regen_policy
from agent.atlas_supervised_patch_regen_schema import *


class AtlasSupervisedPatchRegenService:
    def __init__(self, storage=None, journal=None, llm_client=None):
        self.storage = storage or AtlasPlanPoolStorage("ca_data")
        self.journal = journal or AtlasJournal("ca_data")
        self.llm_client = llm_client or AtlasPatchRegenNullLLMClient()

    def regenerate(self, request: AtlasPatchRegenRequest) -> AtlasPatchRegenResult:
        request.pool_id = validate_relative_path(request.pool_id); request.item_id = validate_relative_path(request.item_id)
        if request.run_id: request.run_id = validate_relative_path(request.run_id)
        regen_run_id = f"regen_{uuid4().hex[:10]}"; policy = get_patch_regen_policy(request.policy_id)
        pool = self.storage.load_pool(request.pool_id); item = pool.get_item(request.item_id)
        if item is None: raise KeyError("item not found")
        warnings, errors = [], []
        packet = self.build_input_packet(request, item, policy, warnings)
        assess = self.assess_regeneratability(packet, policy)
        status = "blocked" if not assess["allowed"] else "manual_required"
        raw = ""; prompt = ""
        if request.dry_run or policy.policy_id == "patch_regen_dry_run_v1":
            status = "dry_run"
            candidate = AtlasPatchProposalCandidate(proposal_id=f"proposal_{uuid4().hex[:8]}", status="dry_run", target_files=packet.target_files, summary="dry_run")
        elif not assess["allowed"]:
            status = assess.get("status", "blocked")
            candidate = AtlasPatchProposalCandidate(proposal_id=f"proposal_{uuid4().hex[:8]}", status=status, target_files=packet.target_files, summary=assess["reason"], warnings=assess.get("warnings", []))
        else:
            prompt = self.build_prompt(packet, policy, request.max_prompt_chars)
            raw = self.llm_client.generate(prompt, {"target_files": packet.target_files})
            candidate = self.parse_candidate(raw, packet)
            candidate = self.validate_candidate(candidate, packet, policy)
            status = candidate.status
        result = AtlasPatchRegenResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, regen_run_id=regen_run_id, policy_id=policy.policy_id, status=status, candidate=candidate, input_packet=packet, context_bundle_id=str(packet.metadata.get("context_bundle_id", "")), retry_run_id=str(packet.metadata.get("retry_run_id", "")), evaluator_result_id=str(packet.metadata.get("evaluator_result_id", "")), prompt_preview=prompt[:1000], raw_llm_output=raw[:4000], warnings=warnings, errors=errors, metadata={"approval_required": True, "approval_status": "pending", "safe_apply_ready": False})
        self.save_result(result); self.attach_candidate(pool, item, result)
        return result

    def build_input_packet(self, request, item, policy, warnings):
        md = dict(item.metadata or {})
        target_files = request.target_files or md.get("target_files") or []
        changed_files = request.changed_files or md.get("changed_files") or target_files
        original_patch = request.original_patch or md.get("patch") or ""
        vr = request.verification_result or md.get("verification") or md.get("auto_verification") or {}
        br = request.bounded_retry_result or md.get("bounded_retry_result") or {}
        fr = request.failure_stop_suggestion or md.get("failure_stop_suggestion") or {}
        cbid = request.context_bundle_id or md.get("context_bundle_id") or ""
        cb = {}
        if cbid:
            p = Path("ca_data") / "atlas" / "context_bundles" / request.pool_id / f"{validate_relative_path(cbid)}.json"
            if p.exists(): cb = json.loads(p.read_text(encoding="utf-8"))
            else: warnings.append("context_bundle_missing")
        return AtlasPatchRegenInputPacket(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, policy_id=policy.policy_id, project_path=request.project_path, target_files=target_files, changed_files=changed_files, original_patch_summary=original_patch[:200], original_patch=original_patch, verification_result=vr, bounded_retry_result=br, failure_stop_suggestion=fr, evaluator_result={}, context_bundle=cb, related_tests=cb.get("related_tests", []), dependency_edges=cb.get("dependency_edges", []), warnings=warnings, metadata={"context_bundle_id": cbid, "retry_run_id": request.retry_run_id, "evaluator_result_id": request.evaluator_result_id})

    def assess_regeneratability(self, packet, policy):
        if not packet.target_files: return {"allowed": False, "reason": "no_target_files", "status": "blocked", "warnings": []}
        if len(packet.target_files) > policy.max_target_files: return {"allowed": False, "reason": "too_many_target_files", "status": "blocked", "warnings": []}
        if policy.require_context_bundle and not packet.context_bundle: return {"allowed": False, "reason": "context_bundle_required", "status": "blocked", "warnings": []}
        evidence = json.dumps(packet.verification_result) + json.dumps(packet.bounded_retry_result) + json.dumps(packet.failure_stop_suggestion)
        if not evidence or evidence == "{}{}{}": return {"allowed": False, "reason": "failure_evidence_missing", "status": "not_regeneratable", "warnings": []}
        ev = evidence.lower()
        if any(k in ev for k in ["timeout", "transient", "environment"]): return {"allowed": False, "reason": "transient_failure", "status": "not_regeneratable", "warnings": []}
        if not packet.original_patch: return {"allowed": False, "reason": "original_patch_missing", "status": "not_regeneratable", "warnings": []}
        return {"allowed": True, "reason": "deterministic_failure", "status": "manual_required", "warnings": []}

    def build_prompt(self, packet, policy, max_chars):
        s = {"item_id": packet.item_id, "target_files": packet.target_files, "verification": packet.verification_result, "bounded_retry": packet.bounded_retry_result}
        return ("# Atlas Supervised Patch Regeneration\nOutput JSON only." + json.dumps(s, ensure_ascii=False))[:max_chars]

    def parse_candidate(self, raw, packet):
        try: data = json.loads(raw)
        except Exception:
            return AtlasPatchProposalCandidate(proposal_id=f"proposal_{uuid4().hex[:8]}", status="manual_required", target_files=packet.target_files, warnings=["llm_json_parse_failed"])
        data.setdefault("proposal_id", f"proposal_{uuid4().hex[:8]}")
        return AtlasPatchProposalCandidate(**data)

    def validate_candidate(self, c, packet, policy):
        allowed = set(policy.allowed_decisions + ["failed", "dry_run"])
        if c.status not in allowed: c.status = "manual_required"
        if c.patch_format != "unified_diff": c.status = "manual_required"; c.patch = ""
        if c.status == "proposal_ready" and not c.patch: c.status = "manual_required"
        if len(c.patch) > policy.max_patch_chars: c.status = "manual_required"; c.patch = ""; c.warnings.append("patch_too_large")
        text = c.patch
        if "/etc/" in text or "../" in text: c.status = "blocked"; c.errors.append("unsafe_patch_path")
        c.manual_review_required = True; c.approval_required = True; c.approval_status = "pending"; c.safe_apply_ready = False
        return c

    def save_result(self, result):
        root = Path("ca_data") / "atlas" / "patch_regen" / result.pool_id; root.mkdir(parents=True, exist_ok=True)
        (root / f"{result.regen_run_id}.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        patch_prev = (result.candidate.patch or "")[:3000]
        md = f"# Supervised Patch Regeneration\n\n## Summary\n- regen_run_id: {result.regen_run_id}\n- pool_id: {result.pool_id}\n- item_id: {result.item_id}\n- run_id: {result.run_id}\n- policy_id: {result.policy_id}\n- status: {result.status}\n- context_bundle_id: {result.context_bundle_id}\n- retry_run_id: {result.retry_run_id}\n- evaluator_result_id: {result.evaluator_result_id}\n- target_files: {result.candidate.target_files}\n- approval_status: {result.candidate.approval_status}\n- safe_apply_ready: {result.candidate.safe_apply_ready}\n\n## Patch Preview\n{patch_prev}\n\n## Safety\n- manual approval required: true\n- auto apply: false\n- safe_apply executed: false\n- verification executed: false\n- auto rollback: false\n- auto restore: false\n"
        (root / f"{result.regen_run_id}.md").write_text(md, encoding="utf-8")

    def attach_candidate(self, pool, item, result):
        md = dict(item.metadata or {})
        cands = list(md.get("patch_regen_candidates") or [])
        cands.append({"regen_run_id": result.regen_run_id, "proposal_id": result.candidate.proposal_id, "status": result.candidate.status, "summary": result.candidate.summary, "target_files": result.candidate.target_files, "approval_status": "pending", "safe_apply_ready": False, "created_at": datetime.now(timezone.utc).isoformat(), "result_path": f"ca_data/atlas/patch_regen/{result.pool_id}/{result.regen_run_id}.json"})
        md["patch_regen_candidates"] = cands
        item.metadata = md
        self.storage.save_pool(pool)
