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
from datetime import datetime, timezone
from pathlib import Path

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
    result = ingest_portal_evidence(store, PortalRunEvidence(
        installation_id=f"capsule:{content_hash}",
        provider_id=meta.provider_id or "unknown",
        model_id=meta.model_id,
        dimension=meta.dimension or "greenfield",
        runtime_passed=runtime_passed,
        user_decision=user_decision,
        evidence_refs=[f"capsule:{package_id}:{version}:{content_hash}"],
    ))

    # Immutability check: the package ZIP must be byte-for-byte unchanged.
    actual_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    immutable_ok = (actual_hash == content_hash)

    evidence = CapsuleReplayEvidence(
        package_id=package_id, version=version, content_hash=content_hash,
        model_id=meta.model_id, provider_id=meta.provider_id,
        runtime_passed=runtime_passed, user_decision=user_decision,
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


__all__ = [
    "CAPSULE_FORGE_SCHEMA_VERSION",
    "CapsuleForgeMeta",
    "CapsuleReplayEvidence",
    "write_capsule_forge_meta",
    "read_capsule_forge_meta",
    "record_capsule_replay",
]
