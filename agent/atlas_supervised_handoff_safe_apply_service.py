from __future__ import annotations
import hashlib, json, re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_safe_apply_execution_schema import AtlasSafeApplyExecutionRequest
from agent.atlas_safe_apply_execution_service import AtlasSafeApplyExecutionService
from agent.atlas_supervised_handoff_safe_apply_policies import get_supervised_handoff_safe_apply_policy
from agent.atlas_supervised_handoff_safe_apply_schema import AtlasSupervisedHandoffSafeApplyRequest, AtlasSupervisedHandoffSafeApplyResult


class AtlasSupervisedHandoffSafeApplyService:
    def __init__(self, *, storage=None, journal=None, automation_gate=None, safe_apply_service=None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))
        self.automation_gate = automation_gate or AtlasAutomationGateService()
        self.safe_apply_service = safe_apply_service or AtlasSafeApplyExecutionService(journal=self.journal, storage=self.storage)

    def execute(self, request: AtlasSupervisedHandoffSafeApplyRequest) -> AtlasSupervisedHandoffSafeApplyResult:
        now = datetime.now(timezone.utc).isoformat(); execution_id = f"safehandoff_{uuid4().hex[:12]}"
        policy = get_supervised_handoff_safe_apply_policy(request.policy_id)
        pool = self.storage.load_pool(request.pool_id); item = pool.get_item(request.item_id)
        handoff = self._load_handoff(request.pool_id, request.handoff_id)
        before = {"safe_apply_executed": bool(handoff.get("safe_apply_executed", False)), "status": str(handoff.get("status", ""))}
        errs = self._validate_handoff(handoff, request, policy)
        gate = self._gate_recheck(pool, item, handoff)
        gate_bad = gate.get("decision") != "allow" or gate.get("decision") == "manual_required" or gate.get("risk_level") in {"medium", "high"}
        if errs or gate_bad:
            res = AtlasSupervisedHandoffSafeApplyResult(pool_id=request.pool_id,item_id=request.item_id,run_id=request.run_id,handoff_id=request.handoff_id,execution_id=execution_id,policy_id=policy.policy_id,status="dry_run" if request.dry_run else "blocked",gate_decision=gate,metadata={"validation_errors":errs,"would_apply":False,"gate_rechecked":True,"patch_sha256":handoff.get("metadata",{}).get("patch_sha256","")},handoff_status_before=before,handoff_status_after=before,warnings=errs,errors=[],created_at=now)
            self._save_result(res, handoff)
            self._emit(request, execution_id, "supervised_handoff_safe_apply_blocked", res)
            return res
        if request.dry_run or policy.policy_id.endswith("dry_run_v1"):
            res = AtlasSupervisedHandoffSafeApplyResult(pool_id=request.pool_id,item_id=request.item_id,run_id=request.run_id,handoff_id=request.handoff_id,execution_id=execution_id,policy_id=policy.policy_id,status="dry_run",gate_decision=gate,metadata={"validation_errors":[],"would_apply":True,"gate_rechecked":True,"target_files":handoff.get("target_files",[]),"patch_sha256":handoff.get("metadata",{}).get("patch_sha256","")},handoff_status_before=before,handoff_status_after=before,created_at=now)
            self._save_result(res, handoff); self._emit(request, execution_id, "supervised_handoff_result_saved", res); return res
        temp = deepcopy(item); temp.metadata = {**dict(item.metadata or {}), "patch": handoff.get("patch",""), "target_files": handoff.get("target_files",[]), "action_type":"patch", "approval": {"decision":"approved"}}; temp.target_files = list(handoff.get("target_files") or [])
        orig = pool.get_item(item.item_id); pool.items = [temp if x.item_id==item.item_id else x for x in pool.items]; self.storage.save_pool(pool)
        safe = self.safe_apply_service.execute_item(AtlasSafeApplyExecutionRequest(pool_id=request.pool_id,item_id=request.item_id,run_id=request.run_id or execution_id,workspace_id=request.workspace_id,requested_by="atlas_supervised_handoff_safe_apply"))
        pool = self.storage.load_pool(request.pool_id); pool.items = [orig if x.item_id==item.item_id else x for x in pool.items]; self.storage.save_pool(pool)
        sp = safe.model_dump(); sf = sp.get("safe_apply_result") or {}; changed = list((sp.get("metadata") or {}).get("executor_result",{}).get("changed_files") or sf.get("changed_files") or [])
        snap = ((sp.get("metadata") or {}).get("change_snapshot") or sf.get("change_snapshot") or {}).get("snapshot_id","")
        st = "applied" if sp.get("status")=="applied" else "failed"
        after = dict(before); after.update({"safe_apply_executed": st=="applied", "status": "applied" if st=="applied" else handoff.get("status","ready")})
        res = AtlasSupervisedHandoffSafeApplyResult(pool_id=request.pool_id,item_id=request.item_id,run_id=request.run_id,handoff_id=request.handoff_id,execution_id=execution_id,policy_id=policy.policy_id,status=st,safe_apply_result=sf,handoff_status_before=before,handoff_status_after=after,gate_decision=gate,changed_files=changed,snapshot_id=snap,created_at=now,metadata={"gate_rechecked":True})
        self._update_handoff_item(request, res, handoff)
        self._save_result(res, handoff); self._emit(request, execution_id, "supervised_handoff_safe_apply_completed" if st=="applied" else "supervised_handoff_safe_apply_failed", res)
        return res

    def _load_handoff(self, pool_id, hid):
        if not hid.startswith("handoff_"): raise ValueError("invalid_handoff_id")
        p = Path(self.storage.root_dir)/"atlas"/"safe_apply_handoffs"/validate_relative_path(pool_id)/f"{validate_relative_path(hid)}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def _validate_handoff(self, h, r, p):
        e=[]; patch=str(h.get("patch") or ""); tf=list(h.get("target_files") or [])
        if h.get("pool_id")!=r.pool_id: e.append("pool_id_mismatch")
        if h.get("item_id")!=r.item_id: e.append("item_id_mismatch")
        if h.get("approval_status")!="approved": e.append("not_approved")
        if not h.get("safe_apply_ready",False): e.append("safe_apply_not_ready")
        if h.get("safe_apply_executed",False): e.append("already_executed")
        if h.get("patch_format")!="unified_diff" or not patch.strip(): e.append("invalid_patch")
        if len(tf)==0 or len(tf)>p.max_target_files: e.append("invalid_target_files")
        if len(patch)>p.max_patch_chars: e.append("patch_too_large")
        sha=(h.get("metadata") or {}).get("patch_sha256","")
        if sha!=hashlib.sha256(patch.encode()).hexdigest(): e.append("patch_hash_mismatch")
        x=self._extract_patch_paths(patch)
        if any(z not in set(tf) for z in x): e.append("patch_outside_target_files")
        if any(z.startswith('/') or '..' in z.split('/') for z in x): e.append("unsafe_target_path")
        if "GIT binary patch" in patch: e.append("binary_patch_not_allowed")
        return sorted(set(e))

    def _extract_patch_paths(self, patch):
        out=set()
        for ln in patch.splitlines():
            m1=re.match(r"^diff --git\s+(.+)\s+(.+)$",ln); m2=re.match(r"^(---|\+\+\+)\s+(.+)$",ln)
            pts=[m1.group(1),m1.group(2)] if m1 else ([m2.group(2)] if m2 else [])
            for p in pts:
                p=p.strip().strip('"').removeprefix('a/').removeprefix('b/')
                if p and p!="/dev/null": out.add(p)
        return out

    def _gate_recheck(self,pool,item,h):
        g=type("GateItem",(),{"item_id":item.item_id,"risk_level":"low","item_type":"implementation","status":"ready","target_files":list(h.get("target_files") or []),"metadata":{"action_type":"patch","patch":h.get("patch","") ,"target_files":list(h.get("target_files") or []),"approval":{"decision":"approved"}}})()
        d=self.automation_gate.decide_pre_safe_apply(pool,g,atlas_auto_policy_presets()["guarded_low_risk"])
        return {"decision":d.decision,"reasons":list(d.reasons),"risk_level":(d.metadata or {}).get("risk_level","")}

    def _update_handoff_item(self, req, res, handoff):
        hp=Path(self.storage.root_dir)/"atlas"/"safe_apply_handoffs"/req.pool_id/f"{req.handoff_id}.json"
        handoff["safe_apply_executed"]=res.status=="applied"; handoff["safe_apply_execution_id"]=res.execution_id; handoff["verification_executed"]=False
        handoff["status"]="applied" if res.status=="applied" else handoff.get("status","ready")
        handoff.setdefault("metadata",{})["last_execution_status"]=res.status
        hp.write_text(json.dumps(handoff,ensure_ascii=False,indent=2),encoding="utf-8")

    def _save_result(self,res,handoff):
        d=Path(self.storage.root_dir)/"atlas"/"supervised_handoff_safe_apply"/res.pool_id; d.mkdir(parents=True,exist_ok=True)
        jp=d/f"{res.execution_id}.json"; mp=d/f"{res.execution_id}.md"
        jp.write_text(json.dumps(res.model_dump(),ensure_ascii=False,indent=2),encoding="utf-8")
        mp.write_text(f"# Supervised Handoff Safe Apply\n\n## Summary\n- execution_id: {res.execution_id}\n- pool_id: {res.pool_id}\n- item_id: {res.item_id}\n- handoff_id: {res.handoff_id}\n- policy_id: {res.policy_id}\n- status: {res.status}\n- snapshot_id: {res.snapshot_id}\n\n## Safety\n- verification executed: false\n- bounded retry executed: false\n- rollback executed: false\n- restore executed: false\n- debug review executed: false\n- patch regeneration executed: false\n",encoding="utf-8")

    def _emit(self, req, execution_id, event_type, res):
        rid = req.run_id or execution_id
        self.journal.append_event(req.pool_id, rid, {"event_type":event_type,"execution_id":execution_id,"pool_id":req.pool_id,"item_id":req.item_id,"run_id":rid,"handoff_id":req.handoff_id,"policy_id":req.policy_id,"status":res.status,"snapshot_id":res.snapshot_id,"changed_files":res.changed_files,"verification_executed":False,"rollback_executed":False,"restore_executed":False,"created_at":datetime.now(timezone.utc).isoformat()})
