from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_safe_apply_adapter import AtlasSafeApplyAdapter
from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyRequest
from agent.atlas_safe_apply_execution_schema import AtlasSafeApplyExecutionRequest, AtlasSafeApplyExecutionResult

class AtlasSafeApplyExecutionService:
    def __init__(self, *, journal: AtlasJournal, storage: AtlasPlanPoolStorage, safe_apply_adapter: AtlasSafeApplyAdapter | None = None):
        self.journal = journal; self.storage = storage; self.safe_apply_adapter = safe_apply_adapter
    def execute_item(self, request: AtlasSafeApplyExecutionRequest) -> AtlasSafeApplyExecutionResult:
        pool = self.storage.load_pool(request.pool_id); item = pool.get_item(request.item_id)
        if item is None: return AtlasSafeApplyExecutionResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, status='blocked', warnings=['item_not_found'])
        ok,w = self.validate_item_for_safe_apply(pool,item)
        if not ok: return AtlasSafeApplyExecutionResult(pool_id=pool.pool_id,item_id=item.item_id,run_id=request.run_id,status='blocked',warnings=w,plan_pool=pool.model_dump())
        ar = self.safe_apply_adapter.apply_low_risk_item(item,pool,request=AtlasSafeApplyRequest(pool_id=pool.pool_id,item_id=item.item_id,dry_run=request.dry_run,require_approval=False,allow_simulation_without_executor=True,metadata=dict(request.metadata or {})))
        d = ar.model_dump() if hasattr(ar,'model_dump') else dict(ar)
        self.mark_item_from_result(pool,item,d); self.storage.save_pool(pool); self.journal.save_plan_pool(pool)
        jp,mp = self.save_execution_record(request.pool_id,request.item_id,{"request":request.model_dump(),"result":d,"pool":pool.model_dump()})
        st = 'applied' if d.get('status')=='applied' else ('blocked' if d.get('status') in {'blocked','skipped'} else 'failed')
        return AtlasSafeApplyExecutionResult(pool_id=pool.pool_id,item_id=item.item_id,run_id=request.run_id,status=st,safe_apply_result=d,plan_pool=pool.model_dump(),metadata={'execution_record_json':jp,'execution_record_md':mp})
    def validate_item_for_safe_apply(self, pool: AtlasPlanPool, item: AtlasPlanItem):
        w=[]
        if self.safe_apply_adapter is None: return False,['safe_apply_adapter_unavailable']
        if str((item.metadata.get('approval') or {}).get('decision','')).lower()!='approved': w.append('approval_not_approved')
        if str(item.risk_level or '').lower()!='low': w.append('risk_not_low')
        if str((item.metadata.get('action_type') or '')).lower() in {'delete','run_command'}: w.append('forbidden_action_type')
        if item.item_type not in {'implementation','documentation'}: w.append('unsupported_item_type')
        ev=self.safe_apply_adapter.evaluate_safe_apply(item,pool)
        if ev.decision!='allow': w.append('safe_apply_blocked')
        return len(w)==0,w
    def mark_item_from_result(self,pool,item,result):
        st=str(result.get('status') or '')
        if st=='applied': item.status='completed'; pool.completed_item_ids=list(dict.fromkeys(pool.completed_item_ids+[item.item_id]))
        elif st in {'blocked','skipped'}: item.status='blocked'; pool.blocked_item_ids=list(dict.fromkeys(pool.blocked_item_ids+[item.item_id]))
        else: item.status='failed'; pool.failed_item_ids=list(dict.fromkeys(pool.failed_item_ids+[item.item_id]))
        item.metadata.setdefault('safe_apply',{}); item.metadata['safe_apply'].update({'status':st,'applied_at':datetime.now(timezone.utc).isoformat()})
    def save_execution_record(self,pool_id,item_id,result):
        ts=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); d=Path(self.journal.paths(pool_id=pool_id).plan_pool_json).parent/'safe_apply'; d.mkdir(parents=True,exist_ok=True)
        jp=d/f'{item_id}_{ts}.json'; mp=d/f'{item_id}_{ts}.md'; jp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); mp.write_text(f"# Atlas Safe Apply Execution\n\n- Pool ID: {pool_id}\n- Item ID: {item_id}\n",encoding='utf-8'); return str(jp),str(mp)
