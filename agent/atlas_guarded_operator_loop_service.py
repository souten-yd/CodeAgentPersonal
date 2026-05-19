from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_guarded_operator_loop_policies import get_guarded_operator_loop_policy
from agent.atlas_guarded_operator_loop_schema import AtlasGuardedOperatorLoopRequest, AtlasGuardedOperatorLoopResult, AtlasGuardedOperatorLoopStep
from agent.atlas_manual_next_action_executor_schema import AtlasManualNextActionExecutorRequest
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_next_action_orchestrator_schema import AtlasNextActionOrchestratorRequest
from agent.atlas_post_manual_execution_refresh_schema import AtlasPostManualExecutionRefreshRequest

class AtlasGuardedOperatorLoopService:
    def __init__(self, *, journal, multi_status_service, next_action_orchestrator_service, manual_executor_service, post_refresh_service, data_root):
        self.journal=journal; self.multi_status_service=multi_status_service; self.next_action_orchestrator_service=next_action_orchestrator_service; self.manual_executor_service=manual_executor_service; self.post_refresh_service=post_refresh_service; self.data_root=Path(data_root).expanduser().resolve()

    def run(self, request: AtlasGuardedOperatorLoopRequest) -> AtlasGuardedOperatorLoopResult:
        lid=f"guardloop_{uuid4().hex[:10]}"; rid=request.run_id or lid; p=get_guarded_operator_loop_policy(request.policy_id)
        r=AtlasGuardedOperatorLoopResult(pool_id=request.pool_id,run_id=rid,loop_run_id=lid,policy_id=p.policy_id,mode=request.mode,status='blocked',created_at=datetime.now(timezone.utc).isoformat())
        md={"mode":request.mode,"confirmed_action_executed":False,"followup_action_executed":False,"auto_continue_executed":False,"execute_all_executed":False,"manual_executor_execute_calls":0,"manual_executor_dry_run_calls":0,"post_refresh_calls":0,"followup_executor_calls":0}
        self._emit(r,'guarded_operator_loop_started')
        try:
            if p.max_actions_per_request!=1: raise ValueError('max_actions_per_request_must_be_1')
            validate_relative_path(request.pool_id)
            if request.mode=='advance_to_confirmation':
                ms=self.multi_status_service.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id=request.pool_id,run_id=rid,workspace_id=request.workspace_id,project_path=request.project_path,dry_run=False,reviewer=request.reviewer,reason=request.reason,metadata={"source":"guarded_operator_loop"}))
                r.multi_status_run_id=ms.multi_status_run_id; r.steps.append(AtlasGuardedOperatorLoopStep(step='queue_built',status='ok',run_id=rid,result_id=ms.multi_status_run_id)); self._emit(r,'guarded_operator_loop_queue_built')
                na=self.next_action_orchestrator_service.prepare(AtlasNextActionOrchestratorRequest(pool_id=request.pool_id,run_id=rid,workspace_id=request.workspace_id,project_path=request.project_path,multi_status_run_id=r.multi_status_run_id,build_queue_if_missing=False,refresh_queue=False,dry_run=False,reviewer=request.reviewer,reason=request.reason,metadata={"source":"guarded_operator_loop"}))
                nd=na.model_dump(); r.orchestrator_run_id=na.orchestrator_run_id; r.selected_item_id=na.selected_item_id; r.selected_next_action=na.selected_next_action; r.action_contract=dict(nd.get('action_contract') or {}); r.action_id=r.action_contract.get('action_id',''); r.action_kind=r.action_contract.get('action_kind','');
                r.steps.append(AtlasGuardedOperatorLoopStep(step='action_prepared',status=na.status,run_id=rid,result_id=na.orchestrator_run_id)); self._emit(r,'guarded_operator_loop_action_prepared')
                if r.action_kind=='execution_candidate':
                    r.confirmation_token=f"MANUAL_EXECUTE:{r.orchestrator_run_id}:{r.action_id}:{r.selected_next_action}:{r.selected_item_id}"; r.steps.append(AtlasGuardedOperatorLoopStep(step='token_previewed',status='ok')); self._emit(r,'guarded_operator_loop_token_previewed'); md['confirmation_token_returned']=True
                    if p.allow_auto_dry_run:
                        ex=self.manual_executor_service.execute(AtlasManualNextActionExecutorRequest(pool_id=request.pool_id,run_id=rid,workspace_id=request.workspace_id,orchestrator_run_id=r.orchestrator_run_id,action_id=r.action_id,expected_next_action=r.selected_next_action,confirmation_token=r.confirmation_token,confirmation_text='EXECUTE ONE ACTION',dry_run=True,require_dry_run_first=request.require_dry_run_first,reviewer=request.reviewer,reason=request.reason,metadata={"source":"guarded_operator_loop"}))
                        r.dry_run_result=ex.model_dump(); r.executor_run_id=ex.executor_run_id; md['manual_executor_dry_run_calls']=1; r.steps.append(AtlasGuardedOperatorLoopStep(step='dry_run_completed',status=ex.status,result_id=ex.executor_run_id)); self._emit(r,'guarded_operator_loop_dry_run_completed')
                        r.status='dry_run_ready' if ex.status=='dry_run' else 'confirmation_required'
                    else: r.status='confirmation_required'
                elif na.status=='manual_display': r.status='manual_display'
                elif na.status=='no_action': r.status='no_action'
                else: r.status='blocked'
            elif request.mode in {'execute_confirmed_action','execute_and_refresh'}:
                ex=self.manual_executor_service.execute(AtlasManualNextActionExecutorRequest(pool_id=request.pool_id,run_id=rid,workspace_id=request.workspace_id,orchestrator_run_id=request.orchestrator_run_id,action_id=request.action_id,expected_next_action=request.expected_next_action,confirmation_token=request.confirmation_token,confirmation_text=request.confirmation_text,explicit_decision=request.explicit_decision,dry_run=False,require_dry_run_first=request.require_dry_run_first,reviewer=request.reviewer,reason=request.reason,metadata={"source":"guarded_operator_loop"}))
                r.execute_result=ex.model_dump(); r.executor_run_id=ex.executor_run_id; md['manual_executor_execute_calls']=1; md['confirmed_action_executed']=ex.status=='executed'; r.status='confirmation_required' if ex.status=='executed' else 'blocked'; self._emit(r,'guarded_operator_loop_execute_completed')
                if request.mode=='execute_and_refresh' and ex.status=='executed':
                    rf=self.post_refresh_service.refresh(AtlasPostManualExecutionRefreshRequest(pool_id=request.pool_id,run_id=rid,workspace_id=request.workspace_id,project_path=request.project_path,executor_run_id=ex.executor_run_id,dry_run=False,reviewer=request.reviewer,reason=request.reason,metadata={"source":"guarded_operator_loop"}))
                    r.refresh_result=rf.model_dump(); r.post_refresh_run_id=rf.refresh_run_id; md['post_refresh_calls']=1; r.status='executed_and_refreshed'; self._emit(r,'guarded_operator_loop_post_refresh_completed')
            elif request.mode=='refresh_after_execution':
                rf=self.post_refresh_service.refresh(AtlasPostManualExecutionRefreshRequest(pool_id=request.pool_id,run_id=rid,workspace_id=request.workspace_id,project_path=request.project_path,executor_run_id=request.executor_run_id,dry_run=False,reviewer=request.reviewer,reason=request.reason,metadata={"source":"guarded_operator_loop"}))
                r.refresh_result=rf.model_dump(); r.post_refresh_run_id=rf.refresh_run_id; md['post_refresh_calls']=1; r.status='refreshed'
            else:
                r.errors.append('invalid_mode'); r.status='blocked'
        except Exception as exc:
            r.status='failed_internal'; r.errors.append(f'unexpected_guarded_loop_exception:{exc.__class__.__name__}')
        r.metadata.update(md)
        self._save_result(r)
        self._emit(r,'guarded_operator_loop_result_saved')
        return r
    def _emit(self,r,e): self.journal.append_event(r.pool_id, r.run_id, {"event_type":e,"loop_run_id":r.loop_run_id,"pool_id":r.pool_id,"run_id":r.run_id,"mode":r.mode,"created_at":datetime.now(timezone.utc).isoformat()})
    def _save_result(self,r):
        root=self.data_root/'atlas'/'guarded_operator_loop'/validate_relative_path(r.pool_id); root.mkdir(parents=True,exist_ok=True)
        d=r.model_dump(); d['confirmation_token']='';
        jp=root/f'{r.loop_run_id}.json'; mp=root/f'{r.loop_run_id}.md'
        d['metadata'].update({"data_root":str(self.data_root),"result_path":str(jp),"result_path_relative":f"atlas/guarded_operator_loop/{r.pool_id}/{r.loop_run_id}.json"})
        jp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
        mp.write_text(f"# Guarded Operator Loop\n\n## Summary\n- loop_run_id: {r.loop_run_id}\n- pool_id: {r.pool_id}\n- mode: {r.mode}\n- status: {r.status}\n- selected_item_id: {r.selected_item_id}\n- selected_next_action: {r.selected_next_action}\n- action_id: {r.action_id}\n",encoding='utf-8')
