from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from agent.atlas_change_snapshot_schema import AtlasChangeSnapshot, AtlasChangeSnapshotFile, AtlasChangeSnapshotResult
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_item_file_changes import normalize_plan_item_file_changes, validate_protected_relative_path
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


class AtlasChangeSnapshotService:
    MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024

    def __init__(self, *, journal: AtlasJournal, storage: AtlasPlanPoolStorage, workspace_root: Path | str | None = None):
        self.journal = journal
        self.storage = storage
        self.workspace_root = Path(workspace_root) if workspace_root else None

    def resolve_workspace_root(self, workspace_id: str) -> Path:
        if self.workspace_root is not None:
            return self.workspace_root
        return Path(self.journal.root_dir) / 'atlas' / 'workspaces' / workspace_id

    def validate_target_path(self, path: str) -> tuple[bool, str]:
        ok, reason, _ = validate_protected_relative_path(path)
        return ok, reason

    def copy_file_to_snapshot(self, src: Path, dst: Path):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())

    def compute_sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

    def write_manifest(self, snapshot: AtlasChangeSnapshot):
        manifest = Path(snapshot.manifest_path)
        manifest.write_text(json.dumps(snapshot.model_dump(), ensure_ascii=False, indent=2), encoding='utf-8')
        md = manifest.with_suffix('.md')
        md.write_text(f"# Atlas Change Snapshot\n\n- Snapshot ID: {snapshot.snapshot_id}\n- Pool ID: {snapshot.pool_id}\n- Item ID: {snapshot.item_id}\n- Run ID: {snapshot.run_id}\n- Created at: {snapshot.created_at}\n- File count: {len(snapshot.target_files)}\n- Warnings: {', '.join(snapshot.warnings)}\n", encoding='utf-8')

    def mark_item_from_snapshot(self, pool, item, result: AtlasChangeSnapshotResult):
        item.metadata.setdefault('change_snapshot', {})
        snap = result.snapshot
        item.metadata['change_snapshot'].update({
            'snapshot_id': (snap.snapshot_id if snap else ''),
            'status': result.status,
            'manifest_path': (snap.manifest_path if snap else ''),
            'snapshot_dir': (snap.snapshot_dir if snap else ''),
            'created_at': (snap.created_at if snap else datetime.now(timezone.utc).isoformat()),
            'file_count': len((snap.target_files if snap else [])),
            'skipped_count': len([f for f in (snap.target_files if snap else []) if f.skipped]),
            'restore_allowed': bool(snap.restore_allowed) if snap else False,
        })

    def create_snapshot(self, pool_id, item_id, run_id='', workspace_id='default') -> AtlasChangeSnapshotResult:
        pool = self.storage.load_pool(pool_id)
        item = pool.get_item(item_id)
        if item is None:
            return AtlasChangeSnapshotResult(pool_id=pool_id, item_id=item_id, run_id=run_id, status='blocked', warnings=['item_not_found'])
        norm = normalize_plan_item_file_changes(item)
        if norm.get('changed'):
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
        target_files = list(item.target_files or [])
        if not target_files:
            if run_id:
                self.journal.append_event(pool_id, run_id, {'event_type': 'change_snapshot_manual_blocked', 'pool_id': pool_id, 'item_id': item_id, 'status': 'blocked', 'warnings': ['no_target_files'], 'created_at': datetime.now(timezone.utc).isoformat()})
            return AtlasChangeSnapshotResult(pool_id=pool_id, item_id=item_id, run_id=run_id, status='blocked', warnings=['no_target_files'])

        if run_id:
            self.journal.append_event(pool_id, run_id, {'event_type': 'change_snapshot_manual_started', 'pool_id': pool_id, 'item_id': item_id, 'status': 'started', 'created_at': datetime.now(timezone.utc).isoformat()})
        ts = datetime.now(timezone.utc)
        snapshot_id = f'{item_id}_{ts.strftime("%Y%m%dT%H%M%SZ")}'
        root = self.resolve_workspace_root(workspace_id) / 'plan_pools' / pool_id / 'change_snapshots' / snapshot_id
        files_dir = root / 'files'
        root.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        entries: list[AtlasChangeSnapshotFile] = []

        for target in target_files:
            ok, reason = self.validate_target_path(target)
            if not ok:
                warnings.append(reason)
                if run_id:
                    self.journal.append_event(pool_id, run_id, {'event_type': 'change_snapshot_manual_blocked', 'pool_id': pool_id, 'item_id': item_id, 'status': 'blocked', 'warnings': [reason], 'created_at': datetime.now(timezone.utc).isoformat()})
                return AtlasChangeSnapshotResult(pool_id=pool_id, item_id=item_id, run_id=run_id, status='blocked', warnings=[reason])
            src = self.resolve_workspace_root(workspace_id) / target
            if not src.exists():
                entries.append(AtlasChangeSnapshotFile(path=target, existed_before=False))
                continue
            if src.is_dir():
                warnings.append('directory_target_skipped')
                entries.append(AtlasChangeSnapshotFile(path=target, existed_before=True, skipped=True, skip_reason='directory_target_skipped'))
                continue
            size = src.stat().st_size
            if size > self.MAX_FILE_SIZE_BYTES:
                warnings.append('large_file_skipped')
                entries.append(AtlasChangeSnapshotFile(path=target, existed_before=True, size_before=size, skipped=True, skip_reason='large_file_skipped'))
                continue
            encoded = target.replace('/', '__').replace('\\', '__') + '.before'
            dst = files_dir / encoded
            self.copy_file_to_snapshot(src, dst)
            entries.append(AtlasChangeSnapshotFile(path=target, existed_before=True, size_before=size, sha256_before=self.compute_sha256(src), backup_path=str(dst)))

        snapshot = AtlasChangeSnapshot(snapshot_id=snapshot_id, pool_id=pool_id, item_id=item_id, run_id=run_id, workspace_id=workspace_id, created_at=ts.isoformat(), target_files=entries, manifest_path=str(root / 'manifest.json'), snapshot_dir=str(root), warnings=warnings)
        self.write_manifest(snapshot)
        result = AtlasChangeSnapshotResult(pool_id=pool_id, item_id=item_id, run_id=run_id, status='saved', snapshot=snapshot, warnings=warnings)
        self.mark_item_from_snapshot(pool, item, result)
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        if run_id:
            self.journal.append_event(pool_id, run_id, {'event_type': 'change_snapshot_manual_saved', 'pool_id': pool_id, 'item_id': item_id, 'status': 'saved', 'warnings': warnings, 'created_at': datetime.now(timezone.utc).isoformat()})
        return result
