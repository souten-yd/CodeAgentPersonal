from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_multi_item_supervised_status_policies import get_multi_item_supervised_status_policy
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedItemSummary, AtlasMultiItemSupervisedStatusRequest, AtlasMultiItemSupervisedStatusResult
from agent.atlas_supervised_item_status_schema import AtlasSupervisedItemStatusFinalizeRequest

class AtlasMultiItemSupervisedStatusService:
    def __init__(self, *, storage, journal, supervised_item_status_service):
        self.storage=storage; self.journal=journal; self.supervised_item_status_service=supervised_item_status_service
    def _emit(self, event_type, req, msid, **kw):
        rid=req.run_id or msid
        self.journal.append_event(req.pool_id, rid, {"event_type":event_type,"multi_status_run_id":msid,"pool_id":req.pool_id,"run_id":rid,"created_at":datetime.now(timezone.utc).isoformat(),**kw})
    def build_status(self, request: AtlasMultiItemSupervisedStatusRequest):
        policy=get_multi_item_supervised_status_policy(request.policy_id)
        msid=f"multistatus_{uuid4().hex[:10]}"
        pool=self.storage.load_pool(request.pool_id)
        ids=request.item_ids or [i.item_id for i in pool.items]
        ids=ids[:min(request.max_items, policy.max_items)]
        self._emit("multi_item_supervised_status_started", request, msid, item_count=len(ids))
        sums=[]; warnings=[]; errors=[]
        for iid in ids:
            try: validate_relative_path(iid)
            except Exception: warnings.append(f"invalid_item_id:{iid}"); continue
            item=pool.get_item(iid)
            if not item: warnings.append(f"missing_item_id:{iid}"); continue
            fin=None
            if request.refresh_item_status and policy.refresh_item_status:
                try:
                    fin=self.supervised_item_status_service.finalize(AtlasSupervisedItemStatusFinalizeRequest(pool_id=request.pool_id,item_id=iid,run_id=request.run_id or msid,workspace_id=request.workspace_id,project_path=request.project_path,policy_id="supervised_item_status_v1",use_latest_artifacts=request.use_latest_artifacts,update_item_status=(request.update_item_status and not request.dry_run and policy.update_item_status),update_metadata=(request.update_metadata and not request.dry_run),dry_run=(request.dry_run or not policy.update_item_status),reviewer=request.reviewer,reason=request.reason,metadata={"source":"multi_item_supervised_status","multi_status_run_id":msid}))
                    self._emit("multi_item_supervised_status_item_refreshed", request, msid, item_id=iid)
                except Exception as ex:
                    errors.append(f"finalize_failed:{iid}:{ex}")
                    self._emit("multi_item_supervised_status_item_failed", request, msid, item_id=iid)
            md=item.metadata or {}; sup=md.get("supervised_item_status") or {}
            status=(fin.transition.to_status if fin else sup.get("status") or item.status or "unchanged")
            action=(fin.next_action if fin else sup.get("next_action") or "manual_review")
            payload=(fin.next_action_payload if fin else sup.get("next_action_payload") or {})
            s=AtlasMultiItemSupervisedItemSummary(item_id=iid,item_title=str(getattr(item,'title','') or getattr(item,'name','') or getattr(item,'description',''))[:120],item_status=str(item.status or ''),supervised_status=str(status),next_action=str(action),next_action_payload=payload if request.include_next_action_payloads else {},evidence_type=str((fin.transition.evidence_type if fin else sup.get('evidence_type')) or ''),evidence_run_id=str((fin.transition.evidence_run_id if fin else sup.get('evidence_run_id')) or ''))
            if action=="approve_patch_candidate" and (not payload.get("regen_run_id") or not payload.get("proposal_id")): s.selectable=False; s.blocked_reason="missing_approval_payload"; s.warnings.append("missing_patch_candidate_ids")
            sums.append(s)
        if not sums and warnings: status="blocked"
        else: status="dry_run" if request.dry_run else ("partial" if errors else "ready")
        pri={"approve_patch_candidate":10,"run_supervised_safe_apply":20,"run_supervised_verification":30,"run_supervised_retry":40,"run_patch_regen_from_recommendation":50,"manual_review":80,"investigate_failure":90,"none":1000}
        groups={k:[] for k in ["approve_patch_candidate","run_supervised_safe_apply","run_supervised_verification","run_supervised_retry","run_patch_regen_from_recommendation","manual_review","investigate_failure","none"]}
        for s in sums: s.priority=pri.get(s.next_action,900)+(500 if not s.selectable else 0); groups.setdefault(s.next_action,[]).append(s.item_id)
        ordered=sorted([s for s in sums if s.selectable and s.supervised_status!="completed" and s.supervised_status!="failed_internal"], key=lambda x:x.priority)
        next_item=ordered[0] if ordered else None
        counts={}
        for s in sums: counts[s.supervised_status]=counts.get(s.supervised_status,0)+1
        res=AtlasMultiItemSupervisedStatusResult(pool_id=request.pool_id,run_id=request.run_id,multi_status_run_id=msid,policy_id=policy.policy_id,status=status,item_summaries=sums,next_item=next_item,next_actions_by_type=groups,counts=counts,warnings=warnings,errors=errors,metadata={"next_action_executed":False,"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"patch_regeneration_executed":False,"approval_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False})
        root=Path("ca_data")/"atlas"/"multi_item_supervised_status"/request.pool_id; root.mkdir(parents=True, exist_ok=True)
        (root/f"{msid}.json").write_text(json.dumps(res.model_dump(),ensure_ascii=False,indent=2),encoding="utf-8")
        (root/f"{msid}.md").write_text(f"# Multi-item Supervised Status\n\n## Summary\n- multi_status_run_id: {msid}\n- pool_id: {request.pool_id}\n- status: {status}\n- next_item_id: {next_item.item_id if next_item else ''}\n- next_action: {next_item.next_action if next_item else ''}\n",encoding='utf-8')
        self._emit("multi_item_supervised_status_result_saved", request, msid, next_item_id=(next_item.item_id if next_item else ""), next_action=(next_item.next_action if next_item else ""), counts=counts)
        return res
