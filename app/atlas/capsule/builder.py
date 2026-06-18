from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.atlas.capsule.contracts import (
    CAPSULE_SCHEMA_VERSION,
    CapsuleBuildRequest,
    CapsuleManifest,
    CapsulePackageRecord,
)
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.file_service import sha256_file
from app.atlas.play.sessions import PlaySessionRepository
from app.atlas.play.workspace_policy import WorkspacePermission, decide_workspace_access
from app.portal.paths import PortalPathLayout


CAPSULE_BUILDER_SCHEMA_VERSION = "atlas.capsule.builder.v1"
_SAFE_PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_DEFAULT_EXCLUDES = {
    ".git/**",
    ".hg/**",
    ".svn/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    ".venv/**",
    "venv/**",
    "node_modules/**",
    "dist/**",
    "build/**",
    "ca_data/**",
    ".atlas/**",
    ".portal/**",
    "data/**",
}
_PRIVATE_PATTERNS = {
    "env_file": re.compile(r"(^|/)\.env($|[./-])", re.IGNORECASE),
    "api_key": re.compile(r"(api[_-]?key|secret|token)\s*[:=]", re.IGNORECASE),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


class CapsuleBuildError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BuildFile:
    relative_path: str
    source_path: Path
    sha256: str
    size_bytes: int


def _safe_package_id(value: str) -> str:
    text = str(value or "").strip()
    if not _SAFE_PACKAGE_ID_RE.fullmatch(text):
        raise CapsuleBuildError("invalid_package_id")
    return text


class CapsuleBuilder:
    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.sessions = PlaySessionRepository(self.data_root)
        self.portal_paths = PortalPathLayout(self.data_root)

    def build(self, request: CapsuleBuildRequest) -> dict:
        session = self.sessions.load(request.play_session_id)
        if session.project_id != request.project_id:
            raise CapsuleBuildError("session_project_mismatch")
        # A Play session is "successful" when it reached the terminal "stopped" state with
        # an exit code of 0 (clean self-exit) or None (a long-lived server/static preview
        # the user explicitly stopped). A crashed session is "failed" and is rejected.
        # Force build skips this gate but keeps every path-safety and exclusion guard.
        if not request.force and not self._is_successful_play_session(session):
            raise CapsuleBuildError("play_session_not_successful")
        project_root = Path(session.project_root).resolve()
        profiles = self._selected_profiles(request, session)
        default_profile_id = request.default_profile_id or profiles[0].profile_id
        if default_profile_id not in {profile.profile_id for profile in profiles}:
            raise CapsuleBuildError("default_profile_not_selected")
        files = self._collect_files(project_root, request)
        if not request.force:
            self._check_expected_hashes(files, request)
        package_id = _safe_package_id(request.package_id or request.project_id)
        manifest = CapsuleManifest(
            package_id=package_id,
            name=request.name or package_id,
            version=request.version,
            launch_profiles=profiles,
            default_profile_id=default_profile_id,
            data_policy=request.data_policy,
        )
        checksums = {item.relative_path: item.sha256 for item in files}
        findings = self._scan_findings(files)
        zip_bytes = self._build_zip(files, manifest, checksums, findings)
        content_hash = hashlib.sha256(zip_bytes).hexdigest()
        package_root = self.portal_paths.package_store_root() / package_id / request.version
        package_root.mkdir(parents=True, exist_ok=True)
        storage_path = package_root / f"{content_hash}.zip"
        if not storage_path.exists():
            storage_path.write_bytes(zip_bytes)
        manifest_path = package_root / f"{content_hash}.manifest.json"
        findings_path = package_root / f"{content_hash}.findings.json"
        manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        findings_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
        record = CapsulePackageRecord(
            package_id=package_id,
            version=request.version,
            storage_path=str(storage_path),
            content_hash=content_hash,
            manifest_path=str(manifest_path),
            findings_path=str(findings_path),
        )
        record_path = package_root / f"{content_hash}.record.json"
        record_path.write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "schema_version": CAPSULE_BUILDER_SCHEMA_VERSION,
            "status": "built",
            "forced": bool(request.force),
            "record": record.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
            "checksums": checksums,
            "findings": findings,
            "file_count": len(files),
        }

    def _selected_profiles(self, request: CapsuleBuildRequest, session) -> list[LaunchProfile]:
        source_profiles = request.launch_profiles or [self._profile_from_session(session)]
        selected = [profile for profile in source_profiles if profile.profile_id in set(request.selected_profile_ids)]
        if len(selected) != len(set(request.selected_profile_ids)):
            raise CapsuleBuildError("selected_profile_missing")
        if any(profile.kind == LaunchKind.COMPOSITE for profile in selected):
            deps = {dep for profile in selected for dep in profile.depends_on}
            selected_ids = {profile.profile_id for profile in selected}
            if not deps.issubset(selected_ids):
                raise CapsuleBuildError("composite_dependency_not_selected")
        return selected

    def _is_successful_play_session(self, session) -> bool:
        if session.state != "stopped":
            return False
        if session.exit_code in {0, None}:
            return True
        # Long-lived static/server previews are intentionally terminated by the
        # user. On Windows and POSIX this can leave a non-zero process return
        # code even though the Play session completed by explicit Stop.
        return session.stop_reason == "user_stop"

    def _profile_from_session(self, session) -> LaunchProfile:
        adapter = session.adapter or {}
        kind = LaunchKind(adapter.get("kind") or session.launch_kind)
        argv = [str(value) for value in adapter.get("argv") or []]
        entrypoint = ""
        if kind == LaunchKind.STATIC_WEB and len(argv) > 1:
            entrypoint = argv[1]
        elif kind == LaunchKind.PYTHON_SCRIPT and len(argv) > 1:
            entrypoint = argv[1]
        else:
            entrypoint = str(adapter.get("entrypoint") or "")
        return LaunchProfile(
            profile_id=session.launch_profile_id,
            name=session.launch_profile_id,
            kind=kind,
            entrypoint=entrypoint or None,
            working_directory=session.working_directory or ".",
        )

    def _collect_files(self, project_root: Path, request: CapsuleBuildRequest) -> list[BuildFile]:
        items: list[BuildFile] = []
        excludes = set(request.exclude_globs) | _DEFAULT_EXCLUDES
        for path in sorted(project_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(project_root).as_posix()
            if not self._included(rel, request.include_globs, excludes):
                continue
            decision = decide_workspace_access(project_root=project_root, relative_path=rel, permission=WorkspacePermission.READ)
            if not decision.allowed:
                continue
            items.append(BuildFile(relative_path=rel, source_path=path, sha256=sha256_file(path), size_bytes=path.stat().st_size))
        if not items:
            raise CapsuleBuildError("no_package_files")
        return items

    def _included(self, relative_path: str, includes: list[str], excludes: set[str]) -> bool:
        include_match = any(fnmatch.fnmatch(relative_path, pattern) for pattern in (includes or ["**/*"]))
        exclude_match = any(fnmatch.fnmatch(relative_path, pattern) for pattern in excludes)
        return include_match and not exclude_match

    def _check_expected_hashes(self, files: list[BuildFile], request: CapsuleBuildRequest) -> None:
        if not request.require_current_hashes:
            return
        by_path = {item.relative_path: item.sha256 for item in files}
        for rel, expected in request.expected_file_hashes.items():
            if by_path.get(rel) != expected:
                raise CapsuleBuildError("stale_file_hash")

    def _scan_findings(self, files: list[BuildFile]) -> list[dict]:
        findings: list[dict] = []
        for item in files:
            if _PRIVATE_PATTERNS["env_file"].search(item.relative_path):
                findings.append({"kind": "env_file", "path": item.relative_path, "severity": "warning"})
            if item.size_bytes > 200_000:
                continue
            try:
                text = item.source_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for kind in ("api_key", "private_key"):
                if _PRIVATE_PATTERNS[kind].search(text):
                    findings.append({"kind": kind, "path": item.relative_path, "severity": "warning"})
        return findings

    def _build_zip(self, files: list[BuildFile], manifest: CapsuleManifest, checksums: dict[str, str], findings: list[dict]) -> bytes:
        from io import BytesIO

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            self._write_json(zf, "metadata/manifest.json", manifest.model_dump(mode="json"))
            self._write_json(zf, "metadata/checksums.json", {"schema_version": CAPSULE_SCHEMA_VERSION, "files": checksums})
            self._write_json(zf, "metadata/findings.json", {"schema_version": CAPSULE_BUILDER_SCHEMA_VERSION, "findings": findings})
            for item in sorted(files, key=lambda value: value.relative_path):
                info = zipfile.ZipInfo(f"application/{item.relative_path}", _ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, item.source_path.read_bytes())
        return buffer.getvalue()

    def _write_json(self, zf: zipfile.ZipFile, name: str, payload: dict) -> None:
        info = zipfile.ZipInfo(name, _ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zf.writestr(info, json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
