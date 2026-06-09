from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.atlas.capsule.contracts import CapsuleManifest, CapsulePackageRecord
from app.atlas.play.contracts import TrustState
from app.atlas.play.paths import AtlasPlayPathLayout
from app.portal.paths import PortalPathLayout


PORTAL_CATALOG_SCHEMA_VERSION = "portal.catalog.v1"
MAX_IMPORT_FILES = 2000
MAX_IMPORT_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class PortalCatalogError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PortalCatalogService:
    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.paths = PortalPathLayout(self.data_root)

    def list_packages(self) -> dict:
        records = [record.model_dump(mode="json") for record in self._records()]
        return {"schema_version": PORTAL_CATALOG_SCHEMA_VERSION, "packages": records}

    def preflight_archive(self, archive_path: str | Path) -> dict:
        path = Path(archive_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise PortalCatalogError("archive_missing")
        with zipfile.ZipFile(path) as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            if len(infos) > MAX_IMPORT_FILES:
                raise PortalCatalogError("archive_file_count_exceeded")
            normalized: set[str] = set()
            total_size = 0
            for info in infos:
                safe_name = self._safe_zip_name(info.filename)
                key = safe_name.lower()
                if key in normalized:
                    raise PortalCatalogError("duplicate_archive_entry")
                normalized.add(key)
                total_size += int(info.file_size)
                if info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO and info.file_size > 1024 * 1024:
                    raise PortalCatalogError("archive_compression_ratio_exceeded")
            if total_size > MAX_IMPORT_BYTES:
                raise PortalCatalogError("archive_size_exceeded")
            try:
                manifest = CapsuleManifest.model_validate_json(zf.read("metadata/manifest.json").decode("utf-8"))
                checksums_payload = json.loads(zf.read("metadata/checksums.json").decode("utf-8"))
            except KeyError as exc:
                raise PortalCatalogError("manifest_missing") from exc
            except Exception as exc:
                raise PortalCatalogError("manifest_invalid") from exc
            checksums = dict(checksums_payload.get("files") or {})
            for info in infos:
                safe_name = self._safe_zip_name(info.filename)
                if not safe_name.startswith("application/"):
                    continue
                rel = safe_name.removeprefix("application/")
                expected = checksums.get(rel)
                actual = hashlib.sha256(zf.read(info)).hexdigest()
                if expected != actual:
                    raise PortalCatalogError("checksum_mismatch")
        return {
            "schema_version": PORTAL_CATALOG_SCHEMA_VERSION,
            "status": "ok",
            "manifest": manifest.model_dump(mode="json"),
            "file_count": len(infos),
            "total_uncompressed_bytes": total_size,
        }

    def import_archive(self, archive_path: str | Path) -> dict:
        preflight = self.preflight_archive(archive_path)
        manifest = CapsuleManifest.model_validate(preflight["manifest"])
        content_hash = hashlib.sha256(Path(archive_path).read_bytes()).hexdigest()
        existing = [record for record in self._records() if record.package_id == manifest.package_id and record.version == manifest.version]
        if any(record.content_hash != content_hash for record in existing):
            raise PortalCatalogError("package_version_conflict")
        package_root = self.paths.package_store_root() / manifest.package_id / manifest.version
        package_root.mkdir(parents=True, exist_ok=True)
        storage_path = package_root / f"{content_hash}.zip"
        if not storage_path.exists():
            shutil.copyfile(archive_path, storage_path)
        record = CapsulePackageRecord(
            package_id=manifest.package_id,
            version=manifest.version,
            storage_path=str(storage_path),
            content_hash=content_hash,
            trust_state=TrustState.UNTRUSTED_IMPORTED_PACKAGE,
        )
        self._record_path(record).write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return {"schema_version": PORTAL_CATALOG_SCHEMA_VERSION, "status": "imported", "record": record.model_dump(mode="json")}

    def export_package_path(self, package_id: str, version: str, content_hash: str) -> Path:
        for record in self._records():
            if record.package_id == package_id and record.version == version and record.content_hash == content_hash:
                path = Path(record.storage_path)
                if path.exists():
                    return path
        raise PortalCatalogError("package_not_found")

    def uninstall_package(self, package_id: str, version: str, content_hash: str) -> dict:
        path = self.export_package_path(package_id, version, content_hash)
        record_dir = path.parent
        for item in record_dir.glob(f"{content_hash}.*"):
            if item.is_file():
                item.unlink()
        if path.exists():
            path.unlink()
        return {"schema_version": PORTAL_CATALOG_SCHEMA_VERSION, "status": "uninstalled", "data_deleted": False}

    def fork_to_atlas(self, package_id: str, version: str, content_hash: str, new_project_id: str) -> dict:
        archive = self.export_package_path(package_id, version, content_hash)
        work_root = AtlasPlayPathLayout(self.data_root).atlas_project_work_root(new_project_id)
        if work_root.exists() and any(work_root.iterdir()):
            raise PortalCatalogError("target_project_exists")
        work_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = self._safe_zip_name(info.filename)
                if not name.startswith("application/"):
                    continue
                rel = name.removeprefix("application/")
                target = (work_root / rel).resolve()
                if os.path.commonpath([str(work_root), str(target)]) != str(work_root):
                    raise PortalCatalogError("archive_entry_escape")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
        return {
            "schema_version": PORTAL_CATALOG_SCHEMA_VERSION,
            "status": "forked",
            "project_id": new_project_id,
            "project_work_root": str(work_root),
        }

    def _records(self) -> list[CapsulePackageRecord]:
        root = self.paths.package_store_root()
        if not root.exists():
            return []
        records: list[CapsulePackageRecord] = []
        for path in sorted(root.glob("*/*/*.record.json")):
            try:
                records.append(CapsulePackageRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return records

    def _record_path(self, record: CapsulePackageRecord) -> Path:
        return self.paths.package_store_root() / record.package_id / record.version / f"{record.content_hash}.record.json"

    def _safe_zip_name(self, name: str) -> str:
        text = str(name or "").replace("\\", "/")
        win = PureWindowsPath(text)
        posix = PurePosixPath(text)
        if text.startswith("/") or win.drive or win.root or any(part in {"", ".", ".."} for part in posix.parts):
            raise PortalCatalogError("archive_entry_unsafe")
        return posix.as_posix()
