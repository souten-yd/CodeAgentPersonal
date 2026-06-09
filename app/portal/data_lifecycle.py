from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.portal.contracts import PortalRunMode, PortalSnapshot
from app.portal.paths import PortalPathLayout


PORTAL_DATA_SCHEMA_VERSION = "portal.data.v1"


class PortalDataError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PortalDataLifecycleService:
    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.paths = PortalPathLayout(self.data_root)

    def prepare_session_data(
        self,
        *,
        installation_id: str,
        portal_session_id: str,
        run_mode: PortalRunMode,
        snapshot_id: str | None = None,
    ) -> dict:
        data_root = self.paths.session_data_root(portal_session_id)
        cache_root = self.paths.session_cache_root(portal_session_id)
        temp_root = self.paths.session_temp_root(portal_session_id)
        for root in (data_root, cache_root, temp_root):
            root.mkdir(parents=True, exist_ok=True)
        if run_mode == PortalRunMode.CONTINUE_CURRENT_DATA:
            self._copy_contents(self.paths.current_data_root(installation_id), data_root)
        elif run_mode == PortalRunMode.START_FROM_SNAPSHOT:
            if not snapshot_id:
                raise PortalDataError("snapshot_id_required")
            snapshot_data = self._snapshot_data_root(installation_id, snapshot_id)
            if not snapshot_data.exists():
                raise PortalDataError("snapshot_not_found")
            self._copy_contents(snapshot_data, data_root)
        return {
            "data_root": str(data_root),
            "cache_root": str(cache_root),
            "temp_root": str(temp_root),
            "source": run_mode.value,
            "snapshot_id": snapshot_id,
        }

    def commit_current_data(self, installation_id: str, portal_session_id: str) -> dict:
        session_data = self.paths.session_data_root(portal_session_id)
        if not session_data.exists():
            raise PortalDataError("session_data_not_found")
        current = self.paths.current_data_root(installation_id)
        staging = current.parent / f".commit-{uuid.uuid4().hex}"
        backup = current.parent / f".previous-{uuid.uuid4().hex}"
        current.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._copy_contents(session_data, staging)
            if current.exists():
                current.rename(backup)
            staging.rename(current)
        except Exception as exc:
            self._rmtree(staging)
            if backup.exists() and not current.exists():
                backup.rename(current)
            raise PortalDataError("current_data_commit_failed") from exc
        finally:
            self._rmtree(backup)
        summary = self.data_summary(installation_id)
        return {"schema_version": PORTAL_DATA_SCHEMA_VERSION, "status": "saved", "current_data": summary["current_data"]}

    def save_snapshot(self, installation_id: str, portal_session_id: str, snapshot_id: str | None = None) -> dict:
        session_data = self.paths.session_data_root(portal_session_id)
        if not session_data.exists():
            raise PortalDataError("session_data_not_found")
        target_id = snapshot_id or f"snapshot-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        snapshot_root = self.paths.snapshot_root(installation_id, target_id)
        if snapshot_root.exists():
            raise PortalDataError("snapshot_already_exists")
        data_root = self._snapshot_data_root(installation_id, target_id)
        data_root.mkdir(parents=True, exist_ok=True)
        self._copy_contents(session_data, data_root)
        snapshot = PortalSnapshot(
            snapshot_id=target_id,
            installation_id=installation_id,
            source=portal_session_id,
            data_hash=self._hash_tree(data_root),
        )
        (snapshot_root / "snapshot.json").write_text(json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return {"schema_version": PORTAL_DATA_SCHEMA_VERSION, "status": "snapshot_saved", "snapshot": snapshot.model_dump(mode="json")}

    def discard_session_data(self, portal_session_id: str) -> dict:
        self._rmtree(self.paths.session_data_root(portal_session_id))
        self._rmtree(self.paths.session_cache_root(portal_session_id))
        self._rmtree(self.paths.session_temp_root(portal_session_id))
        return {"schema_version": PORTAL_DATA_SCHEMA_VERSION, "status": "discarded", "portal_session_id": portal_session_id}

    def data_summary(self, installation_id: str) -> dict:
        current = self.paths.current_data_root(installation_id)
        snapshots_root = self.paths.snapshot_root(installation_id, "placeholder").parent
        snapshots = []
        if snapshots_root.exists():
            for root in sorted(path for path in snapshots_root.iterdir() if path.is_dir()):
                metadata = root / "snapshot.json"
                if metadata.exists():
                    item = json.loads(metadata.read_text(encoding="utf-8"))
                    item["data"] = self._tree_metadata(root / "data")
                    snapshots.append(item)
        return {
            "schema_version": PORTAL_DATA_SCHEMA_VERSION,
            "installation_id": installation_id,
            "current_data": self._tree_metadata(current),
            "snapshots": snapshots,
            "package_export_includes_data": False,
        }

    def delete_installation_data(self, installation_id: str, *, confirm_delete_data: bool) -> dict:
        if not confirm_delete_data:
            raise PortalDataError("data_delete_confirmation_required")
        root = self.paths.current_data_root(installation_id).parent
        self._rmtree(root)
        return {"schema_version": PORTAL_DATA_SCHEMA_VERSION, "status": "data_deleted", "installation_id": installation_id}

    def export_backup_path(self, installation_id: str) -> Path:
        backup_root = self.data_root / "portal" / "data_backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        path = backup_root / f"{installation_id}-data-backup.zip"
        summary = self.data_summary(installation_id)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("metadata/portal_data_backup.json", json.dumps(summary, ensure_ascii=False, indent=2))
            self._write_tree_to_zip(zf, self.paths.current_data_root(installation_id), "current")
            snapshots_root = self.paths.snapshot_root(installation_id, "placeholder").parent
            if snapshots_root.exists():
                self._write_tree_to_zip(zf, snapshots_root, "snapshots")
        return path

    def _snapshot_data_root(self, installation_id: str, snapshot_id: str) -> Path:
        return self.paths.snapshot_root(installation_id, snapshot_id) / "data"

    def _copy_contents(self, source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            return
        for item in source.iterdir():
            destination = target / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)

    def _tree_metadata(self, root: Path) -> dict:
        total = 0
        latest = 0.0
        exists = root.exists()
        if exists:
            for path in root.rglob("*"):
                if path.is_file():
                    stat_result = path.stat()
                    total += stat_result.st_size
                    latest = max(latest, stat_result.st_mtime)
        return {
            "path": str(root),
            "exists": exists,
            "bytes": total,
            "last_modified": datetime.fromtimestamp(latest, timezone.utc).isoformat() if latest else "",
        }

    def _hash_tree(self, root: Path) -> str:
        h = __import__("hashlib").sha256()
        if root.exists():
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                h.update(path.relative_to(root).as_posix().encode("utf-8"))
                h.update(path.read_bytes())
        return h.hexdigest()

    def _write_tree_to_zip(self, zf: zipfile.ZipFile, root: Path, prefix: str) -> None:
        if not root.exists():
            return
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            zf.write(path, f"{prefix}/{path.relative_to(root).as_posix()}")

    def _rmtree(self, path: str | Path) -> None:
        target = Path(path)
        if not target.exists():
            return

        def onerror(_func, failed_path, _exc_info):
            try:
                Path(failed_path).chmod(stat.S_IWRITE)
                Path(failed_path).unlink()
            except OSError:
                pass

        shutil.rmtree(target, ignore_errors=False, onerror=onerror)
