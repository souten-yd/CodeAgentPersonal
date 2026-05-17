from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from agent.atlas_change_snapshot_restore_schema import (
    AtlasChangeSnapshotRestoreFileResult,
    AtlasChangeSnapshotRestoreRequest,
    AtlasChangeSnapshotRestoreResult,
)
from agent.atlas_journal import AtlasJournal


class AtlasChangeSnapshotRestoreService:
    def __init__(self, *, journal: AtlasJournal, workspace_root: Path | str | None = None):
        self.journal = journal
        self.workspace_root = Path(workspace_root) if workspace_root else None

    def resolve_workspace_root(self, workspace_id: str) -> Path:
        if self.workspace_root is not None:
            return self.workspace_root
        return Path(self.journal.root_dir) / 'atlas' / 'workspaces' / workspace_id

    def validate_target_path(self, path: str) -> tuple[bool, str]:
        pp = Path(str(path or '').strip())
        if not str(pp):
            return False, 'empty_target_path'
        if pp.is_absolute() or '..' in pp.parts:
            return False, 'unsafe_target_path'
        return True, ''

    def sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

    def restore(self, req: AtlasChangeSnapshotRestoreRequest) -> AtlasChangeSnapshotRestoreResult:
        started = datetime.now(timezone.utc).isoformat()
        if req.run_id:
            self.journal.append_event(req.pool_id, req.run_id, {'event_type': 'change_snapshot_restore_manual_started', 'pool_id': req.pool_id, 'item_id': req.item_id, 'created_at': started})
        manifest_path = Path(req.manifest_path)
        if not manifest_path.exists():
            res = AtlasChangeSnapshotRestoreResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status='blocked', warnings=['manifest_not_found'])
            if req.run_id:
                self.journal.append_event(req.pool_id, req.run_id, {'event_type': 'change_snapshot_restore_manual_failed', 'pool_id': req.pool_id, 'item_id': req.item_id, 'warnings': res.warnings, 'created_at': datetime.now(timezone.utc).isoformat()})
            return res

        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        entries = manifest.get('target_files') or []
        workspace_root = self.resolve_workspace_root(req.workspace_id)
        results: list[AtlasChangeSnapshotRestoreFileResult] = []
        warnings: list[str] = []

        for entry in entries:
            rel = str(entry.get('path') or '')
            ok, reason = self.validate_target_path(rel)
            if not ok:
                return AtlasChangeSnapshotRestoreResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status='blocked', warnings=[reason])
            target = workspace_root / rel
            existed_before = bool(entry.get('existed_before'))
            backup_path = Path(str(entry.get('backup_path') or ''))
            row = AtlasChangeSnapshotRestoreFileResult(path=rel, existed_before=existed_before)
            if existed_before:
                if not backup_path.exists():
                    row.skipped = True; row.skip_reason = 'backup_not_found'; warnings.append('backup_not_found')
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(backup_path.read_bytes())
                    row.sha256_before = str(entry.get('sha256_before') or '')
                    row.sha256_after = self.sha256(target)
                    row.restored = True
                    if row.sha256_before and row.sha256_after != row.sha256_before:
                        row.skipped = True
                        row.restored = False
                        row.skip_reason = 'sha256_mismatch'
                        warnings.append('sha256_mismatch')
            else:
                if not req.confirm_delete_missing_before:
                    row.skipped = True
                    row.skip_reason = 'manual_confirm_required_for_delete'
                elif target.exists():
                    target.unlink()
                    row.deleted = True
            results.append(row)

        status = 'restored' if any(x.restored or x.deleted for x in results) else 'blocked'
        report = {
            'pool_id': req.pool_id, 'item_id': req.item_id, 'run_id': req.run_id, 'status': status,
            'created_at': datetime.now(timezone.utc).isoformat(), 'manifest_path': str(manifest_path),
            'confirm_delete_missing_before': req.confirm_delete_missing_before,
            'file_results': [x.model_dump() for x in results], 'warnings': warnings,
            'manual_only': True, 'auto_rollback_enabled': False,
        }
        report_json = manifest_path.parent / 'restore_report.json'
        report_md = manifest_path.parent / 'restore_report.md'
        report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        report_md.write_text(f"# Atlas Change Snapshot Restore Report\n\n- Status: {status}\n- Manual only: true\n- Auto rollback enabled: false\n- Restored: {sum(1 for x in results if x.restored)}\n- Deleted: {sum(1 for x in results if x.deleted)}\n- Skipped: {sum(1 for x in results if x.skipped)}\n", encoding='utf-8')
        out = AtlasChangeSnapshotRestoreResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status=status, restored_count=sum(1 for x in results if x.restored), deleted_count=sum(1 for x in results if x.deleted), skipped_count=sum(1 for x in results if x.skipped), file_results=results, warnings=warnings, report_json_path=str(report_json), report_md_path=str(report_md), metadata={'manual_only': True, 'auto_rollback_enabled': False})
        event = 'change_snapshot_restore_manual_completed' if status == 'restored' else 'change_snapshot_restore_manual_failed'
        if req.run_id:
            self.journal.append_event(req.pool_id, req.run_id, {'event_type': event, 'pool_id': req.pool_id, 'item_id': req.item_id, 'status': status, 'warnings': warnings, 'created_at': datetime.now(timezone.utc).isoformat()})
        return out
