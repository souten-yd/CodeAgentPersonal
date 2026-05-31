from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent.atlas_change_snapshot_service import AtlasChangeSnapshotService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_item_file_changes import normalize_plan_item_file_changes
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_safe_apply_adapter import AtlasSafeApplyAdapter
from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyRequest
from agent.atlas_safe_apply_execution_schema import AtlasSafeApplyExecutionRequest, AtlasSafeApplyExecutionResult


class AtlasSafeApplyExecutionService:
    def __init__(self, *, journal: AtlasJournal, storage: AtlasPlanPoolStorage, safe_apply_adapter: AtlasSafeApplyAdapter | None = None, workspace_root: Path | str | None = None):
        self.journal = journal
        self.storage = storage
        self.safe_apply_adapter = safe_apply_adapter
        self.change_snapshot_service = AtlasChangeSnapshotService(journal=journal, storage=storage, workspace_root=workspace_root)

    def execute_item(self, request: AtlasSafeApplyExecutionRequest) -> AtlasSafeApplyExecutionResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        self._append_event(pool.pool_id, request.run_id, 'safe_apply_manual_started', item, status='started')
        if item is None:
            self._append_event(pool.pool_id, request.run_id, 'safe_apply_manual_blocked', None, status='blocked', warnings=['item_not_found'])
            return AtlasSafeApplyExecutionResult(pool_id=pool.pool_id, item_id=request.item_id, run_id=request.run_id, status='blocked', warnings=['item_not_found'], plan_pool=pool.model_dump(), safe_apply_result={'decision': 'block', 'status': 'blocked', 'reasons': ['item_not_found']})
        norm = normalize_plan_item_file_changes(item)
        if norm.get('changed'):
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
        ok, warnings = self.validate_item_for_safe_apply(pool, item, request=request)
        if not ok:
            self.persist_safe_apply_metadata(item, {'status': 'blocked', 'reasons': warnings, 'actual_file_changed': False, 'changed_files': [], 'file_results': []}, change_snapshot={})
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
            self._append_event(pool.pool_id, request.run_id, 'safe_apply_manual_blocked', item, status='blocked', warnings=warnings)
            return AtlasSafeApplyExecutionResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status='blocked', warnings=warnings, plan_pool=pool.model_dump(), safe_apply_result={'decision': 'block', 'status': 'blocked', 'reasons': warnings})


        snapshot_result = self.change_snapshot_service.create_snapshot(pool.pool_id, item.item_id, run_id=request.run_id, workspace_id=request.workspace_id)
        snapshot_meta = {}
        if snapshot_result.snapshot is not None:
            snapshot_meta = {
                'snapshot_id': snapshot_result.snapshot.snapshot_id,
                'manifest_path': snapshot_result.snapshot.manifest_path,
                'snapshot_dir': snapshot_result.snapshot.snapshot_dir,
                'file_count': len(snapshot_result.snapshot.target_files),
                'skipped_count': len([f for f in snapshot_result.snapshot.target_files if f.skipped]),
                'warnings': list(snapshot_result.warnings or []),
                'workspace_root': str(self.change_snapshot_service.resolve_workspace_root(request.workspace_id)),
            }
        if snapshot_result.status in {'blocked', 'failed'}:
            snapshot_reasons = list(snapshot_result.warnings or ['change_snapshot_failed'])
            self.persist_safe_apply_metadata(item, {'status': 'blocked', 'reasons': snapshot_reasons, 'actual_file_changed': False, 'changed_files': [], 'file_results': []}, change_snapshot=snapshot_meta)
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
            self._append_event(pool.pool_id, request.run_id, 'safe_apply_manual_blocked', item, status='blocked', warnings=list(snapshot_result.warnings or ['change_snapshot_failed']))
            return AtlasSafeApplyExecutionResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status='blocked', warnings=list(snapshot_result.warnings or ['change_snapshot_failed']), plan_pool=pool.model_dump(), safe_apply_result={'decision': 'block', 'status': 'blocked', 'reasons': list(snapshot_result.warnings or ['change_snapshot_failed']), 'change_snapshot': snapshot_meta}, metadata={'change_snapshot': snapshot_meta})

        apply_metadata = dict(request.metadata or {})
        apply_result = self.safe_apply_adapter.apply_low_risk_item(item, pool, request=AtlasSafeApplyRequest(pool_id=pool.pool_id, item_id=item.item_id, dry_run=request.dry_run, require_approval=False, allow_simulation_without_executor=True, metadata=apply_metadata))
        result_payload = apply_result.model_dump() if hasattr(apply_result, 'model_dump') else dict(apply_result)
        executor_result = dict(result_payload.get('executor_result') or {})
        for key in ('actual_file_changed', 'changed_files', 'file_results', 'partial_write_possible'):
            if key in executor_result and key not in result_payload:
                result_payload[key] = executor_result.get(key)
        executor_connected = self.safe_apply_adapter is not None and self.safe_apply_adapter.implementation_executor is not None
        result_payload.setdefault('executor_connected', executor_connected)
        result_payload.setdefault('actual_file_changed', bool(result_payload.get('status') == 'applied'))
        result_payload.setdefault('changed_files', list(item.target_files if result_payload.get('status') == 'applied' else []))
        self.mark_item_from_result(pool, item, result_payload)
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        result_status = str(result_payload.get('status') or '').lower()
        if result_status == 'applied':
            status = 'applied'
        elif result_status == 'simulated':
            status = 'simulated'
        elif result_status in {'blocked', 'skipped'}:
            status = result_status
        else:
            status = 'failed'
        reasons = list(result_payload.get('reasons') or [])
        execution_record = {'request': request.model_dump(), 'result': result_payload, 'pool': pool.model_dump(), 'status': status, 'change_snapshot': snapshot_meta}
        json_path, md_path = self.save_execution_record(pool.pool_id, item.item_id, request=request, item=item, status=status, result=result_payload, warnings=reasons, change_snapshot=snapshot_meta)
        if status == 'applied':
            event_type = 'safe_apply_manual_completed'
        elif status == 'simulated':
            event_type = 'safe_apply_manual_simulated'
        elif status == 'blocked':
            event_type = 'safe_apply_manual_blocked'
        else:
            event_type = 'safe_apply_manual_failed'
        self._append_event(pool.pool_id, request.run_id, event_type, item, status=status, warnings=reasons, execution_record_json=json_path, execution_record_md=md_path)
        self.persist_safe_apply_metadata(item, {**result_payload, 'status': status, 'reasons': reasons}, change_snapshot=snapshot_meta)
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        executor_meta = {'actual_file_changed': bool(result_payload.get('actual_file_changed')), 'changed_files': list(result_payload.get('changed_files') or []), 'file_results': list(result_payload.get('file_results') or [])}
        return AtlasSafeApplyExecutionResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status=status, safe_apply_result={**result_payload, 'decision': 'allow' if status == 'applied' else 'block', 'status': status, 'reasons': reasons, 'change_snapshot': snapshot_meta}, plan_pool=pool.model_dump(), warnings=reasons, metadata={'execution_record_json': json_path, 'execution_record_md': md_path, 'workspace_root': str(getattr(getattr(self.safe_apply_adapter, 'implementation_executor', None), 'workspace_root', '')), 'change_snapshot': snapshot_meta, 'executor_result': executor_meta})

    def validate_item_for_safe_apply(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasSafeApplyExecutionRequest | None = None):
        warnings: list[str] = []
        if self.safe_apply_adapter is None:
            return False, ['safe_apply_adapter_unavailable']
        dry_run = bool(request.dry_run) if request is not None else False
        if self.safe_apply_adapter.implementation_executor is None and not dry_run:
            return False, ['safe_apply_executor_unavailable']
        preset_id = str(((request.metadata or {}) if request is not None else {}).get('preset_id') or '').lower()
        if preset_id != 'full_auto' and str(((item.metadata or {}).get('approval') or {}).get('decision') or '').lower() != 'approved':
            warnings.append('approval_not_approved')
        risk = str(item.risk_level or '').lower()
        if risk == 'critical':
            warnings.append('critical_risk_not_allowed')
        elif preset_id == 'full_auto':
            if risk not in {'low', 'medium', 'high'}:
                warnings.append('risk_not_allowed')
        elif risk != 'low':
            warnings.append('risk_not_low')
        action_type = str((item.metadata or {}).get('action_type') or '').lower()
        if action_type in {'delete', 'run_command'}:
            warnings.append('forbidden_action_type')
        if item.item_type not in {'implementation', 'documentation'}:
            warnings.append('unsupported_item_type')
        try:
            evaluation = self.safe_apply_adapter.evaluate_safe_apply(item, pool, preset_id=preset_id)
        except TypeError:
            evaluation = self.safe_apply_adapter.evaluate_safe_apply(item, pool)
        if evaluation.decision != 'allow':
            warnings.append('safe_apply_blocked')
        return len(warnings) == 0, warnings

    def mark_item_from_result(self, pool, item, result):
        st = str(result.get('status') or '')
        if st == 'applied':
            item.status = 'completed'
            pool.completed_item_ids = list(dict.fromkeys(pool.completed_item_ids + [item.item_id]))
        elif st == 'simulated':
            # keep item status unchanged for simulated execution
            pass
        elif st == 'blocked':
            item.status = 'blocked'
            pool.blocked_item_ids = list(dict.fromkeys(pool.blocked_item_ids + [item.item_id]))
        elif st == 'skipped':
            item.status = 'blocked'
            pool.blocked_item_ids = list(dict.fromkeys(pool.blocked_item_ids + [item.item_id]))
        else:
            item.status = 'failed'
            pool.failed_item_ids = list(dict.fromkeys(pool.failed_item_ids + [item.item_id]))
        item.metadata.setdefault('safe_apply', {})
        safe_apply_meta = {'status': st, 'applied_at': datetime.now(timezone.utc).isoformat()}
        source = str((item.metadata or {}).get('source') or '').lower()
        if source == 'patch_proposal':
            safe_apply_meta.update({
                'source': 'patch_proposal_planitem_draft',
                'source_item_id': str((item.metadata or {}).get('source_item_id') or ''),
                'source_proposal_id': str((item.metadata or {}).get('source_proposal_id') or ''),
                'manual_only': True,
                'auto_verification': False,
            })
        item.metadata['safe_apply'].update(safe_apply_meta)

    def persist_safe_apply_metadata(self, item: AtlasPlanItem, result: dict, *, change_snapshot: dict | None = None) -> None:
        item.metadata.setdefault('safe_apply', {})
        status = str(result.get('status') or 'failed')
        partial_write_possible = bool(result.get('partial_write_possible'))
        actual = bool(result.get('actual_file_changed'))
        changed_files = list(result.get('changed_files') or []) if (actual or partial_write_possible) else []
        safe_apply_meta = {
            'status': status,
            'applied_at': datetime.now(timezone.utc).isoformat(),
            'reasons': list(result.get('reasons') or []),
            'changed_files': changed_files,
            'file_results': list(result.get('file_results') or []),
            'actual_file_changed': actual,
            'change_set_id': str(((item.metadata or {}).get('change_set') or {}).get('change_set_id') or ''),
            'change_snapshot_id': (change_snapshot or {}).get('snapshot_id', ''),
            'change_snapshot_manifest_path': (change_snapshot or {}).get('manifest_path', ''),
        }
        if partial_write_possible:
            safe_apply_meta['partial_write_possible'] = True
        item.metadata['safe_apply'].update(safe_apply_meta)

    def save_execution_record(self, pool_id, item_id, *, request: AtlasSafeApplyExecutionRequest, item: AtlasPlanItem, status: str, result: dict, warnings: list[str], change_snapshot: dict | None = None):
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        out_dir = Path(self.journal.paths(pool_id=pool_id).plan_pool_json).parent / 'safe_apply'
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f'{item_id}_{ts}.json'
        md_path = out_dir / f'{item_id}_{ts}.md'
        payload = {'request': request.model_dump(), 'result': result, 'status': status, 'warnings': warnings, 'item_id': item_id, 'pool_id': pool_id, 'change_snapshot': dict(change_snapshot or {})}
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        md_path.write_text(
            f"""# Atlas Safe Apply Execution

- Pool ID: {pool_id}
- Item ID: {item_id}
- Run ID: {request.run_id}
- Requested by: {request.requested_by}
- Status: {status}
- Approval decision: {((item.metadata or {}).get('approval') or {}).get('decision','')}
- Approval ID: {((item.metadata or {}).get('approval') or {}).get('approval_id','')}
- Risk level: {item.risk_level}
- Target files: {', '.join(item.target_files or [])}
- Safe apply result summary: {result.get('summary','')}
- Safe apply reasons: {', '.join(result.get('reasons') or [])}
- Changed files: {', '.join(result.get('changed_files') or [])}
- File results: {json.dumps(result.get('file_results') or [], ensure_ascii=False)}
- Warnings: {', '.join(warnings)}
- Change Snapshot ID: {(change_snapshot or {}).get('snapshot_id','')}
- Change Snapshot manifest: {(change_snapshot or {}).get('manifest_path','')}
- Errors: {', '.join(result.get('errors') or [])}
""",
            encoding='utf-8',
        )
        return str(json_path), str(md_path)

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item: AtlasPlanItem | None, *, status: str, warnings: list[str] | None = None, errors: list[str] | None = None, execution_record_json: str = '', execution_record_md: str = '') -> None:
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {'event_type': event_type, 'pool_id': pool_id, 'run_id': run_id, 'item_id': item.item_id if item else '', 'status': status, 'warnings': list(warnings or []), 'errors': list(errors or []), 'execution_record_json': execution_record_json, 'execution_record_md': execution_record_md, 'created_at': datetime.now(timezone.utc).isoformat()})
