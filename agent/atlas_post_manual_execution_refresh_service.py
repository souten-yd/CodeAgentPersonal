from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_next_action_orchestrator_schema import AtlasNextActionOrchestratorRequest
from agent.atlas_post_manual_execution_refresh_policies import get_post_manual_execution_refresh_policy
from agent.atlas_post_manual_execution_refresh_schema import AtlasPostManualExecutionRefreshRequest, AtlasPostManualExecutionRefreshResult
from agent.atlas_supervised_item_status_schema import AtlasSupervisedItemStatusFinalizeRequest

class AtlasPostManualExecutionRefreshService:
    def __init__(self, *, storage, journal, supervised_item_status_service, multi_status_service, next_action_orchestrator_service):
        self.storage=storage; self.journal=journal; self.supervised_item_status_service=supervised_item_status_service; self.multi_status_service=multi_status_service; self.next_action_orchestrator_service=next_action_orchestrator_service
    def refresh(self, request:AtlasPostManualExecutionRefreshRequest)->AtlasPostManualExecutionRefreshResult:
        rrid=f"postexec_{uuid4().hex[:10]}"; rid=request.run_id or rrid; p=get_post_manual_execution_refresh_policy(request.policy_id)
        r=AtlasPostManualExecutionRefreshResult(pool_id=request.pool_id,run_id=rid,refresh_run_id=rrid,executor_run_id=request.executor_run_id,policy_id=p.policy_id,status="blocked")
        self._emit(request,r,"post_manual_execution_refresh_started")
        try:
            self._validate_ids(request)
            m=self._load_manual(request.pool_id,request.executor_run_id); r.manual_execution_result=m; self._emit(request,r,"post_manual_execution_refresh_executor_loaded")
            ok, reason=self._validate_manual(m, request, p.policy_id)
            if not ok: r.errors.append(reason); r.status="blocked"; self._emit(request,r,"post_manual_execution_refresh_blocked"); return self._save(request,r)
            r.refreshed_item_id=str(m.get("selected_item_id") or ""); r.previous_next_action=str(m.get("selected_next_action") or "")
            self._emit(request,r,"post_manual_execution_refresh_validation_completed")
            if request.refresh_item_status and p.allow_refresh_item_status:
                self._emit(request,r,"post_manual_execution_refresh_item_status_started")
                try:
                    fin=self.supervised_item_status_service.finalize(AtlasSupervisedItemStatusFinalizeRequest(pool_id=request.pool_id,item_id=r.refreshed_item_id,run_id=rid,workspace_id=request.workspace_id,project_path=request.project_path,policy_id=request.item_status_policy_id,source_type="auto",source_run_id=str(m.get("execution_result_id") or m.get("executor_run_id") or ""),use_latest_artifacts=request.use_latest_artifacts,update_item_status=not request.dry_run,update_metadata=not request.dry_run,dry_run=request.dry_run,reviewer=request.reviewer,reason=request.reason,metadata={"source":"post_manual_execution_refresh","refresh_run_id":rrid,"executor_run_id":request.executor_run_id,"previous_next_action":r.previous_next_action}))
                    r.item_status_result=fin.model_dump(); self._emit(request,r,"post_manual_execution_refresh_item_status_completed")
                except Exception as exc:
                    r.warnings.append(f"item_status_refresh_failed:{exc.__class__.__name__}")
            if request.rebuild_multi_status_queue and p.allow_rebuild_multi_status_queue:
                self._emit(request,r,"post_manual_execution_refresh_multi_status_started")
                try:
                    ms=self.multi_status_service.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id=request.pool_id,run_id=rid,workspace_id=request.workspace_id,project_path=request.project_path,policy_id=request.multi_status_policy_id,item_ids=[],use_latest_artifacts=request.use_latest_artifacts,refresh_item_status=True,update_item_status=not request.dry_run,update_metadata=not request.dry_run,dry_run=request.dry_run,include_completed=True,include_blocked=True,include_manual_required=True,include_next_action_payloads=True,max_items=p.max_items,reviewer=request.reviewer,reason=request.reason,metadata={"source":"post_manual_execution_refresh","refresh_run_id":rrid,"executor_run_id":request.executor_run_id}))
                    r.multi_status_result=ms.model_dump(); self._emit(request,r,"post_manual_execution_refresh_multi_status_completed")
                except Exception as exc:
                    r.warnings.append(f"multi_status_rebuild_failed:{exc.__class__.__name__}")
            if request.prepare_next_action and p.allow_prepare_next_action:
                self._emit(request,r,"post_manual_execution_refresh_next_action_prepare_started")
                try:
                    orr=self.next_action_orchestrator_service.prepare(AtlasNextActionOrchestratorRequest(pool_id=request.pool_id,run_id=rid,workspace_id=request.workspace_id,project_path=request.project_path,policy_id=request.orchestrator_policy_id,multi_status_run_id=str((r.multi_status_result or {}).get("multi_status_run_id") or ""),build_queue_if_missing=False,refresh_queue=False,dry_run=request.dry_run,reviewer=request.reviewer,reason=request.reason,metadata={"source":"post_manual_execution_refresh","refresh_run_id":rrid,"executor_run_id":request.executor_run_id}))
                    r.next_action_orchestrator_result=orr.model_dump(); self._emit(request,r,"post_manual_execution_refresh_next_action_prepare_completed")
                except Exception as exc:
                    r.warnings.append(f"next_action_prepare_failed:{exc.__class__.__name__}")
            r.next_item_id=str((r.multi_status_result.get("next_item") or {}).get("item_id") or r.next_action_orchestrator_result.get("selected_item_id") or "")
            r.next_action=str((r.multi_status_result.get("next_item") or {}).get("next_action") or r.next_action_orchestrator_result.get("selected_next_action") or "")
            r.next_action_contract=dict(r.next_action_orchestrator_result.get("action_contract") or {})
            r.counts=dict(r.multi_status_result.get("counts") or {})
            r.status="dry_run" if request.dry_run else ("partial" if r.warnings else "refreshed")
            if not request.dry_run: self._update_item_metadata(request,r)
            self._emit(request,r,f"post_manual_execution_refresh_{r.status}")
            return self._save(request,r)
        except Exception as exc:
            r.status="failed_internal"; r.errors.append(f"unexpected_refresh_exception:{exc.__class__.__name__}"); self._emit(request,r,"post_manual_execution_refresh_failed_internal"); return self._save(request,r)
    def _validate_ids(self, req):
        validate_relative_path(req.pool_id); validate_relative_path(req.executor_run_id); req.run_id and validate_relative_path(req.run_id)
        if not req.executor_run_id.startswith("manualexec_"): raise ValueError("invalid_executor_run_id")
    def _load_manual(self,pool_id,executor_run_id):
        p=Path("ca_data")/"atlas"/"manual_next_action_executor"/validate_relative_path(pool_id)/f"{validate_relative_path(executor_run_id)}.json"
        if not p.exists(): raise FileNotFoundError("executor_result_not_found")
        return json.loads(p.read_text(encoding="utf-8"))
    def _validate_manual(self,m,req,policy_id):
        if str(m.get("pool_id") or "")!=req.pool_id: return False,"pool_mismatch"
        st=str(m.get("status") or "")
        if st not in {"executed","dry_run"}: return False,"invalid_executor_status"
        if policy_id.startswith("strict_") and st!="executed": return False,"strict_requires_executed"
        if not m.get("selected_item_id") or not m.get("selected_next_action") or not m.get("action_contract"): return False,"missing_required_fields"
        md=m.get("metadata") or {}; se=md.get("side_effects") or {}
        for k in ["auto_continue_executed","multi_item_autopilot_continued"]:
            if md.get(k) is True: return False,f"{k}_true"
        for k in ["rollback","restore","debug","remote_git"]:
            if se.get(k) is True: return False,f"side_effect_{k}_true"
        return True,""
    def _update_item_metadata(self, req, r):
        pool=self.storage.load_pool(req.pool_id); item=pool.get_item(r.refreshed_item_id)
        if not item: return
        md=item.metadata or {}; rows=list(md.get("post_manual_execution_refreshes") or [])
        rows.append({"refresh_run_id":r.refresh_run_id,"executor_run_id":r.executor_run_id,"previous_next_action":r.previous_next_action,"status":r.status,"item_status_finalize_run_id":(r.item_status_result.get("finalize_run_id") or ""),"multi_status_run_id":(r.multi_status_result.get("multi_status_run_id") or ""),"next_action_orchestrator_run_id":(r.next_action_orchestrator_result.get("orchestrator_run_id") or ""),"next_item_id":r.next_item_id,"next_action":r.next_action,"created_at":datetime.now(timezone.utc).isoformat(),"result_path":f"ca_data/atlas/post_manual_execution_refresh/{r.pool_id}/{r.refresh_run_id}.json"})
        md["post_manual_execution_refreshes"]=rows; md["latest_post_manual_execution_refresh_run_id"]=r.refresh_run_id; item.metadata=md; self.storage.save_pool(pool); self.journal.save_plan_pool(pool)
    def _save(self, req, r):
        side={"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"patch_regeneration_executed":False,"approval_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False,"remote_git_executed":False}
        r.metadata.update({"executor_status":(r.manual_execution_result or {}).get("status",""),"previous_next_action":r.previous_next_action,"refreshed_item_id":r.refreshed_item_id,"item_status_refreshed":bool(r.item_status_result),"multi_status_rebuilt":bool(r.multi_status_result),"next_action_prepared":bool(r.next_action_orchestrator_result),"next_action_executed":False,"auto_continue_executed":False,"multi_item_autopilot_continued":False,"side_effects":side})
        root=Path("ca_data")/"atlas"/"post_manual_execution_refresh"/req.pool_id; root.mkdir(parents=True, exist_ok=True)
        (root/f"{r.refresh_run_id}.json").write_text(json.dumps(r.model_dump(),ensure_ascii=False,indent=2),encoding="utf-8")
        (root/f"{r.refresh_run_id}.md").write_text(f"# Post Manual Execution Refresh\n\n## Summary\n- refresh_run_id: {r.refresh_run_id}\n- executor_run_id: {r.executor_run_id}\n- pool_id: {r.pool_id}\n- status: {r.status}\n- refreshed_item_id: {r.refreshed_item_id}\n- previous_next_action: {r.previous_next_action}\n- next_item_id: {r.next_item_id}\n- next_action: {r.next_action}\n\n## Manual Execution\n- executor status: {(r.manual_execution_result or {}).get('status','')}\n- selected_item_id: {(r.manual_execution_result or {}).get('selected_item_id','')}\n- selected_next_action: {(r.manual_execution_result or {}).get('selected_next_action','')}\n- execution_result_id: {(r.manual_execution_result or {}).get('execution_result_id','')}\n\n## Item Status Refresh\n- item_status_result_id: {(r.item_status_result or {}).get('finalize_run_id','')}\n- supervised_status_after: {(r.item_status_result or {}).get('supervised_status_after','')}\n- next_action_after: {(r.item_status_result or {}).get('next_action','')}\n\n## Multi-item Queue\n- multi_status_run_id: {(r.multi_status_result or {}).get('multi_status_run_id','')}\n- counts: {r.counts}\n- next_item_id: {r.next_item_id}\n- next_action: {r.next_action}\n\n## Next Manual Step\n- orchestrator_run_id: {(r.next_action_orchestrator_result or {}).get('orchestrator_run_id','')}\n- selected_item_id: {(r.next_action_orchestrator_result or {}).get('selected_item_id','')}\n- selected_next_action: {(r.next_action_orchestrator_result or {}).get('selected_next_action','')}\n- action_kind: {(r.next_action_contract or {}).get('action_kind','')}\n- target_api_path: {(r.next_action_contract or {}).get('target_api_path','')}\n- payload_valid: {(r.next_action_contract or {}).get('payload_valid',False)}\n- missing_fields: {(r.next_action_contract or {}).get('missing_fields',[])}\n\n## Safety\n- next action executed: false\n- auto continue executed: false\n- multi-item autopilot continued: false\n- safe_apply executed by refresh: false\n- verification executed by refresh: false\n- retry executed by refresh: false\n- patch regeneration executed by refresh: false\n- approval executed by refresh: false\n- rollback/restore/debug/remote git executed: false\n",encoding="utf-8")
        self._emit(req,r,"post_manual_execution_refresh_result_saved"); return r
    def _emit(self, req, r, event):
        self.journal.append_event(req.pool_id, req.run_id or r.refresh_run_id,{"event_type":event,"refresh_run_id":r.refresh_run_id,"executor_run_id":r.executor_run_id,"pool_id":req.pool_id,"run_id":req.run_id or r.refresh_run_id,"refreshed_item_id":r.refreshed_item_id,"previous_next_action":r.previous_next_action,"item_status_finalize_run_id":(r.item_status_result or {}).get("finalize_run_id","") if isinstance(r.item_status_result,dict) else "","multi_status_run_id":(r.multi_status_result or {}).get("multi_status_run_id","") if isinstance(r.multi_status_result,dict) else "","orchestrator_run_id":(r.next_action_orchestrator_result or {}).get("orchestrator_run_id","") if isinstance(r.next_action_orchestrator_result,dict) else "","next_item_id":r.next_item_id,"next_action":r.next_action,"status":r.status,"warning_count":len(r.warnings),"error_count":len(r.errors),"next_action_executed":False,"auto_continue_executed":False,"multi_item_autopilot_continued":False,"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"patch_regeneration_executed":False,"approval_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False,"remote_git_executed":False,"created_at":datetime.now(timezone.utc).isoformat()})
