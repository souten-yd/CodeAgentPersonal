from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
import zipfile
from pathlib import Path

from app.atlas.capsule.contracts import CapsuleManifest
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlaySessionManager
from app.portal.catalog import PortalCatalogError, PortalCatalogService
from app.portal.contracts import PortalInstallation, PortalRunRequest, evaluate_portal_run_policy
from app.portal.paths import PortalPathLayout


PORTAL_RUNTIME_SCHEMA_VERSION = "portal.runtime.v1"


class PortalRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PortalRuntimeService:
    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.paths = PortalPathLayout(self.data_root)
        self.catalog = PortalCatalogService(self.data_root)
        self.play = PlaySessionManager(self.data_root)

    def install_package(self, package_id: str, version: str, content_hash: str, installation_id: str | None = None) -> dict:
        package_path = self.catalog.export_package_path(package_id, version, content_hash)
        record = next(
            (item for item in self.catalog._records() if item.package_id == package_id and item.version == version and item.content_hash == content_hash),
            None,
        )
        if record is None:
            raise PortalRuntimeError("package_not_found")
        target_id = installation_id or f"portal-{uuid.uuid4().hex}"
        installation = PortalInstallation(
            installation_id=target_id,
            package_id=package_id,
            version=version,
            package_path=str(package_path),
            content_hash=content_hash,
            trust_state=record.trust_state,
        )
        root = self.paths.installation_root(target_id)
        root.mkdir(parents=True, exist_ok=True)
        (root / "installation.json").write_text(json.dumps(installation.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return {"schema_version": PORTAL_RUNTIME_SCHEMA_VERSION, "status": "installed", "installation": installation.model_dump(mode="json")}

    def run(self, request: PortalRunRequest) -> dict:
        installation = self._load_installation(request.installation_id)
        run_request = request.model_copy(update={"trust_state": installation.trust_state})
        decision = evaluate_portal_run_policy(run_request)
        if not decision.allowed:
            raise PortalRuntimeError(decision.reason)
        package_path = Path(installation.package_path)
        if not package_path.exists() or self._sha256(package_path) != installation.content_hash:
            raise PortalRuntimeError("package_hash_mismatch")
        session_id = f"portal-{uuid.uuid4().hex}"
        app_root = self.paths.session_application_root(session_id)
        app_root.mkdir(parents=True, exist_ok=True)
        manifest = self._extract_application(package_path, app_root)
        profile = next((item for item in manifest.launch_profiles if item.profile_id == request.launch_profile_id), None)
        if profile is None:
            raise PortalRuntimeError("launch_profile_not_found")
        if profile.kind == "composite":
            play_record = self.play.start_composite_session(
                project_id=installation.installation_id,
                project_root=app_root,
                launch_profiles=manifest.launch_profiles,
                composite_profile_id=profile.profile_id,
            )
        else:
            adapter = build_structured_launch_adapter(app_root, profile)
            play_record = self.play.start_session(
                project_id=installation.installation_id,
                project_root=app_root,
                adapter=adapter,
            )
        runtime = {
            "schema_version": PORTAL_RUNTIME_SCHEMA_VERSION,
            "status": "running",
            "installation_id": installation.installation_id,
            "portal_session_id": session_id,
            "play_session_id": play_record.session_id,
            "application_root": str(app_root),
            "launch_profile_id": profile.profile_id,
            "trust_state": installation.trust_state,
            "run_mode": request.run_mode,
        }
        recovery = self.paths.recovery_root(play_record.session_id)
        recovery.mkdir(parents=True, exist_ok=True)
        (recovery / "portal_run.json").write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"schema_version": PORTAL_RUNTIME_SCHEMA_VERSION, "status": "running", "runtime": runtime, "play_session": play_record.model_dump(mode="json")}

    def stop(self, play_session_id: str) -> dict:
        record = self.play.stop_session(play_session_id)
        return {"schema_version": PORTAL_RUNTIME_SCHEMA_VERSION, "status": "stopped", "play_session": record.model_dump(mode="json")}

    def purge(self, play_session_id: str) -> dict:
        runtime = self._load_runtime(play_session_id)
        self.play.stop_session(play_session_id)
        self._rmtree(runtime["application_root"])
        self._rmtree(self.paths.session_cache_root(runtime["portal_session_id"]))
        self._rmtree(self.paths.session_temp_root(runtime["portal_session_id"]))
        return {"schema_version": PORTAL_RUNTIME_SCHEMA_VERSION, "status": "purged", "portal_session_id": runtime["portal_session_id"]}

    def _load_installation(self, installation_id: str) -> PortalInstallation:
        path = self.paths.installation_root(installation_id) / "installation.json"
        if not path.exists():
            raise PortalRuntimeError("installation_not_found")
        return PortalInstallation.model_validate_json(path.read_text(encoding="utf-8"))

    def _load_runtime(self, play_session_id: str) -> dict:
        path = self.paths.recovery_root(play_session_id) / "portal_run.json"
        if not path.exists():
            raise PortalRuntimeError("portal_runtime_not_found")
        return json.loads(path.read_text(encoding="utf-8"))

    def _extract_application(self, package_path: Path, app_root: Path) -> CapsuleManifest:
        try:
            preflight = self.catalog.preflight_archive(package_path)
        except PortalCatalogError as exc:
            raise PortalRuntimeError(exc.code) from exc
        manifest = CapsuleManifest.model_validate(preflight["manifest"])
        with zipfile.ZipFile(package_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = self.catalog._safe_zip_name(info.filename)
                if not name.startswith("application/"):
                    continue
                rel = name.removeprefix("application/")
                target = (app_root / rel).resolve()
                if os.path.commonpath([str(app_root), str(target)]) != str(app_root):
                    raise PortalRuntimeError("archive_entry_escape")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
                target.chmod(stat.S_IREAD)
        return manifest

    def _sha256(self, path: Path) -> str:
        h = __import__("hashlib").sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

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
