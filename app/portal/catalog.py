from __future__ import annotations

import hashlib
import json
import os
import re
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
        packages: list[dict] = []
        for record in self._records():
            payload = record.model_dump(mode="json")
            payload["manifest"] = self._manifest_summary(record)
            payload["display"] = self._display_metadata(record)
            packages.append(payload)
        return {"schema_version": PORTAL_CATALOG_SCHEMA_VERSION, "packages": packages}

    def _manifest_summary(self, record: CapsulePackageRecord) -> dict | None:
        """Attach a read-only manifest projection so the catalog UI can offer launch
        profile selection. Reads only the already-stored manifest; never mutates the package."""
        manifest_path = Path(record.manifest_path) if record.manifest_path else None
        if manifest_path is None or not manifest_path.exists():
            return None
        try:
            manifest = CapsuleManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return {
            "name": manifest.name,
            "version": manifest.version,
            "default_profile_id": manifest.default_profile_id,
            "persistent_data_supported": manifest.data_policy.persistent_data_supported,
            "requested_permissions": list(manifest.requested_permissions),
            "launch_profiles": [
                {"profile_id": profile.profile_id, "name": profile.name, "kind": profile.kind.value}
                for profile in manifest.launch_profiles
            ],
        }

    def _display_metadata(self, record: CapsulePackageRecord) -> dict:
        manifest = self._manifest_summary(record) or {}
        default_name = manifest.get("name") or record.package_id
        path = self._display_path(record)
        if not path.exists():
            return {"name": default_name, "icon": "📦"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"name": default_name, "icon": "📦"}
        name = str(payload.get("name") or default_name).strip() or default_name
        icon = str(payload.get("icon") or "📦").strip() or "📦"
        return {"name": name[:80], "icon": icon[:16]}

    def update_display_metadata(self, package_id: str, version: str, content_hash: str, *, name: str, icon: str = "") -> dict:
        record = self._find_record(package_id, version, content_hash)
        display_name = str(name or "").strip()
        display_icon = str(icon or "").strip() or "📦"
        if not display_name:
            raise PortalCatalogError("display_name_required")
        if len(display_name) > 80:
            raise PortalCatalogError("display_name_too_long")
        if len(display_icon) > 16:
            raise PortalCatalogError("display_icon_too_long")
        payload = {
            "schema_version": PORTAL_CATALOG_SCHEMA_VERSION,
            "package_id": record.package_id,
            "version": record.version,
            "content_hash": record.content_hash,
            "name": display_name,
            "icon": display_icon,
        }
        self._display_path(record).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "schema_version": PORTAL_CATALOG_SCHEMA_VERSION,
            "status": "updated",
            "record": record.model_dump(mode="json"),
            "display": self._display_metadata(record),
        }

    @staticmethod
    def safe_upload_filename(filename: str) -> str:
        """Sanitize a browser-supplied upload name to a safe, extension-checked file
        name. Strips any directory component and rejects non-archive extensions so an
        upload can never be staged outside the quarantine dir or under a tricky name."""
        base = Path(str(filename or "")).name
        low = base.lower()
        if not (low.endswith(".portal.zip") or low.endswith(".zip")):
            raise PortalCatalogError("unsupported_archive_extension")
        cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".") or "upload"
        if not cleaned.lower().endswith(".zip"):
            cleaned = f"{cleaned}.zip"
        return cleaned

    def begin_quarantine_import(self, import_id: str, filename: str) -> Path:
        """Return a quarantined staging path for an uploaded archive. The archive is
        untrusted until preflight + manifest checks pass in import_archive."""
        staged_name = self.safe_upload_filename(filename)
        quarantine_dir = self.paths.quarantine_root(import_id)
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        return quarantine_dir / staged_name

    def discard_quarantine_import(self, import_id: str) -> None:
        quarantine_dir = self.paths.quarantine_root(import_id)
        if quarantine_dir.exists():
            shutil.rmtree(quarantine_dir, ignore_errors=True)

    def preflight_archive(self, archive_path: str | Path) -> dict:
        path = Path(archive_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise PortalCatalogError("archive_missing")
        try:
            archive = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            raise PortalCatalogError("archive_not_a_zip") from exc
        with archive as zf:
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
        manifest_path = package_root / f"{content_hash}.manifest.json"
        manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        record = CapsulePackageRecord(
            package_id=manifest.package_id,
            version=manifest.version,
            storage_path=str(storage_path),
            content_hash=content_hash,
            trust_state=TrustState.UNTRUSTED_IMPORTED_PACKAGE,
            manifest_path=str(manifest_path),
        )
        self._record_path(record).write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return {"schema_version": PORTAL_CATALOG_SCHEMA_VERSION, "status": "imported", "record": record.model_dump(mode="json")}

    def repair_manifest_sidecar(self, package_id: str, version: str, content_hash: str) -> dict:
        """Repair a legacy package whose manifest sidecar is missing/stale by
        re-projecting the manifest from the immutable package archive. Launch
        profiles are inferred only from the package's own metadata/manifest.json;
        the package ZIP is never mutated. Unrecoverable packages are reported with
        a clear status instead of being silently dropped."""
        record = next(
            (
                item
                for item in self._records()
                if item.package_id == package_id and item.version == version and item.content_hash == content_hash
            ),
            None,
        )
        if record is None:
            raise PortalCatalogError("package_not_found")
        zip_path = Path(record.storage_path)
        if not zip_path.exists():
            return {
                "schema_version": PORTAL_CATALOG_SCHEMA_VERSION,
                "status": "unrecoverable",
                "reason": "package_archive_missing",
                "record": record.model_dump(mode="json"),
            }
        try:
            with zipfile.ZipFile(zip_path) as zf:
                manifest = CapsuleManifest.model_validate_json(zf.read("metadata/manifest.json").decode("utf-8"))
        except (KeyError, zipfile.BadZipFile, ValueError, OSError):
            return {
                "schema_version": PORTAL_CATALOG_SCHEMA_VERSION,
                "status": "unrecoverable",
                "reason": "manifest_unrecoverable",
                "record": record.model_dump(mode="json"),
            }
        sidecar = zip_path.parent / f"{content_hash}.manifest.json"
        sidecar.write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        if record.manifest_path != str(sidecar):
            record = record.model_copy(update={"manifest_path": str(sidecar)})
            self._record_path(record).write_text(
                json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return {
            "schema_version": PORTAL_CATALOG_SCHEMA_VERSION,
            "status": "repaired",
            "record": record.model_dump(mode="json"),
            "manifest": self._manifest_summary(record),
        }

    def export_package_path(self, package_id: str, version: str, content_hash: str) -> Path:
        record = self._find_record(package_id, version, content_hash)
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

    def _display_path(self, record: CapsulePackageRecord) -> Path:
        return self.paths.package_store_root() / record.package_id / record.version / f"{record.content_hash}.display.json"

    def _find_record(self, package_id: str, version: str, content_hash: str) -> CapsulePackageRecord:
        for record in self._records():
            if record.package_id == package_id and record.version == version and record.content_hash == content_hash:
                return record
        raise PortalCatalogError("package_not_found")

    def _safe_zip_name(self, name: str) -> str:
        text = str(name or "").replace("\\", "/")
        win = PureWindowsPath(text)
        posix = PurePosixPath(text)
        if text.startswith("/") or win.drive or win.root or any(part in {"", ".", ".."} for part in posix.parts):
            raise PortalCatalogError("archive_entry_unsafe")
        return posix.as_posix()
