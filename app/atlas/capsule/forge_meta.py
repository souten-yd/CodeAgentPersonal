"""Capsule Forge metadata + replay (PFG-29).

Forge provenance for a Capsule is projected into a sidecar next to the package
(``{content_hash}.forge.json``) — never inside the immutable package ZIP, so the package
bytes and its content_hash stay unchanged. Replay records a Portal run outcome against the
Capsule's model into the profile store and writes a replay-evidence sidecar, asserting the
ZIP is byte-for-byte unchanged (no source mutation).
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent.model_forge.portal_evidence import PortalRunEvidence, ingest_portal_evidence
from agent.model_forge.profile_store import ProfileStore
from app.portal.paths import PortalPathLayout

CAPSULE_FORGE_SCHEMA_VERSION = "forge.capsule.v1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapsuleForgeMeta(_Strict):
    schema_version: str = CAPSULE_FORGE_SCHEMA_VERSION
    package_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    provider_id: str = ""
    model_id: str = ""
    route_id: str = ""
    stage: str = ""
    source_mode: str = ""
    arena_run_id: str = ""
    candidate_id: str = ""
    loadout_id: str = ""
    dimension: str = "greenfield"
    recorded_at: str = ""


class CapsuleReplayEvidence(_Strict):
    schema_version: str = CAPSULE_FORGE_SCHEMA_VERSION
    package_id: str
    version: str
    content_hash: str
    model_id: str
    provider_id: str
    runtime_passed: bool | None = None
    runtime_status: str = "unavailable"
    runtime_detail: str = ""
    runtime_evidence_ref: str = ""
    preview_status: int | None = None
    play_session_id: str = ""
    user_decision: str = ""
    evidence_strength: str = ""
    profile_updated: bool = False
    profile_version: int = 0
    package_immutable_verified: bool = False
    recorded_at: str = ""


def _package_root(data_root: str | Path, package_id: str, version: str) -> Path:
    return PortalPathLayout(Path(data_root)).package_store_root() / package_id / version


def _zip_path(data_root, package_id, version, content_hash) -> Path:
    return _package_root(data_root, package_id, version) / f"{content_hash}.zip"


def _meta_path(data_root, package_id, version, content_hash) -> Path:
    return _package_root(data_root, package_id, version) / f"{content_hash}.forge.json"


def write_capsule_forge_meta(data_root: str | Path, projection: dict) -> CapsuleForgeMeta:
    meta = CapsuleForgeMeta(**projection)
    zip_path = _zip_path(data_root, meta.package_id, meta.version, meta.content_hash)
    if not zip_path.exists():
        raise FileNotFoundError("capsule_package_not_found")
    if not meta.recorded_at:
        meta = meta.model_copy(update={"recorded_at": datetime.now(timezone.utc).isoformat()})
    path = _meta_path(data_root, meta.package_id, meta.version, meta.content_hash)
    path.write_text(json.dumps(meta.model_dump(mode="json"), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return meta


def read_capsule_forge_meta(data_root, package_id, version, content_hash) -> CapsuleForgeMeta | None:
    path = _meta_path(data_root, package_id, version, content_hash)
    if not path.exists():
        return None
    return CapsuleForgeMeta.model_validate_json(path.read_text(encoding="utf-8"))


def record_capsule_replay(
    data_root: str | Path,
    store: ProfileStore,
    *,
    package_id: str,
    version: str,
    content_hash: str,
    runtime_passed: bool | None,
    runtime_status: str = "",
    runtime_detail: str = "",
    runtime_evidence_ref: str = "",
    preview_status: int | None = None,
    play_session_id: str = "",
    user_decision: str = "",
) -> CapsuleReplayEvidence:
    """Replay a Capsule run outcome into the model profile and record replay evidence.
    Never mutates the package ZIP or project source: the ZIP hash is verified unchanged."""
    meta = read_capsule_forge_meta(data_root, package_id, version, content_hash)
    if meta is None or not meta.model_id:
        raise ValueError("capsule_forge_meta_missing")
    zip_path = _zip_path(data_root, package_id, version, content_hash)
    if not zip_path.exists():
        raise FileNotFoundError("capsule_package_not_found")

    # Update the model profile through the same runtime-vs-weak-feedback discipline.
    # A caller-supplied runtime_passed flag is not acceptance-level runtime evidence unless
    # it is backed by a concrete replay evidence reference.
    profile_runtime_passed = runtime_passed if runtime_evidence_ref else None
    result = ingest_portal_evidence(store, PortalRunEvidence(
        installation_id=f"capsule:{content_hash}",
        provider_id=meta.provider_id or "unknown",
        model_id=meta.model_id,
        dimension=meta.dimension or "greenfield",
        runtime_passed=profile_runtime_passed,
        user_decision=user_decision,
        evidence_refs=[ref for ref in [f"capsule:{package_id}:{version}:{content_hash}", runtime_evidence_ref] if ref],
    ))

    # Immutability check: the package ZIP must be byte-for-byte unchanged.
    actual_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    immutable_ok = (actual_hash == content_hash)

    evidence = CapsuleReplayEvidence(
        package_id=package_id, version=version, content_hash=content_hash,
        model_id=meta.model_id, provider_id=meta.provider_id,
        runtime_passed=runtime_passed,
        runtime_status=runtime_status or ("passed" if runtime_passed else "failed" if runtime_passed is False else "unavailable"),
        runtime_detail=runtime_detail,
        runtime_evidence_ref=runtime_evidence_ref,
        preview_status=preview_status,
        play_session_id=play_session_id,
        user_decision=user_decision,
        evidence_strength=result.strength.value,
        profile_updated=result.moved_score,
        profile_version=(result.profile.version if result.profile else 0),
        package_immutable_verified=immutable_ok,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    # Append to a replay-evidence sidecar (never rewrites prior entries; ZIP untouched).
    replay_path = _package_root(data_root, package_id, version) / f"{content_hash}.replay.jsonl"
    with replay_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return evidence


def record_capsule_replay_via_play_runtime(
    data_root: str | Path,
    store: ProfileStore,
    *,
    package_id: str,
    version: str,
    content_hash: str,
    user_decision: str = "",
) -> CapsuleReplayEvidence:
    """Install the Capsule application into a replay workspace and verify it through
    the Play static preview runtime before updating model profile evidence."""
    data_root = Path(data_root)
    zip_path = _zip_path(data_root, package_id, version, content_hash)
    if not zip_path.exists():
        raise FileNotFoundError("capsule_package_not_found")
    replay_root = _package_root(data_root, package_id, version) / "_play_replay" / f"{content_hash}.{uuid4().hex}"
    work_root = replay_root / "work"
    work_root.mkdir(parents=True, exist_ok=True)

    extracted = _extract_capsule_application(zip_path, work_root)
    if "index.html" not in extracted:
        return record_capsule_replay(
            data_root, store,
            package_id=package_id, version=version, content_hash=content_hash,
            runtime_passed=None,
            runtime_status="unavailable",
            runtime_detail="application_index_missing",
            user_decision=user_decision,
        )

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.atlas_play import router as atlas_play_router
    from app.atlas.play.contracts import LaunchKind, LaunchProfile
    from app.atlas.play.environment import build_structured_launch_adapter
    from app.atlas.play.sessions import PlaySessionManager

    app = FastAPI()
    app.state.atlas_ca_data_root = str(data_root)
    app.include_router(atlas_play_router)
    client = TestClient(app)
    manager = PlaySessionManager(data_root)
    adapter = build_structured_launch_adapter(
        work_root,
        LaunchProfile(profile_id="web", name="Capsule Replay", kind=LaunchKind.STATIC_WEB, entrypoint="index.html"),
    )
    session = manager.start_session(project_id=f"capsule-{content_hash[:12]}", project_root=work_root, adapter=adapter)
    preview_status: int | None = None
    detail = ""
    try:
        preview = client.get(f"/api/atlas/play/preview/{session.session_id}/index.html")
        preview_status = preview.status_code
        runtime_passed = preview.status_code == 200 and bool(preview.content)
        if not runtime_passed:
            detail = f"preview_status:{preview.status_code}"
    except Exception as exc:  # noqa: BLE001
        runtime_passed = None
        detail = f"play_runtime_error:{type(exc).__name__}"
    finally:
        try:
            manager.stop_session(session.session_id)
        except Exception:  # noqa: BLE001
            pass
    return record_capsule_replay(
        data_root, store,
        package_id=package_id, version=version, content_hash=content_hash,
        runtime_passed=runtime_passed,
        runtime_status="passed" if runtime_passed else "failed" if runtime_passed is False else "unavailable",
        runtime_detail=detail,
        runtime_evidence_ref=f"play_session:{session.session_id}:preview:index.html" if runtime_passed is not None else "",
        preview_status=preview_status,
        play_session_id=session.session_id,
        user_decision=user_decision,
    )


def _extract_capsule_application(zip_path: Path, work_root: Path) -> set[str]:
    extracted: set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or not name.startswith("application/"):
                continue
            rel = Path(name[len("application/"):])
            if rel.is_absolute() or any(part == ".." for part in rel.parts):
                continue
            target = (work_root / rel).resolve()
            try:
                target.relative_to(work_root.resolve())
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
            extracted.add(rel.as_posix())
    return extracted


__all__ = [
    "CAPSULE_FORGE_SCHEMA_VERSION",
    "CapsuleForgeMeta",
    "CapsuleReplayEvidence",
    "write_capsule_forge_meta",
    "read_capsule_forge_meta",
    "record_capsule_replay",
    "record_capsule_replay_via_play_runtime",
]
