"""HTTP API for Atlas Automation Profile selection.

This router wraps the existing ``app.atlas.automation_safety_profile`` module
and the new ``app.atlas.pre_authorized_bounded_dev_envelope`` module. It
exposes:

* ``GET  /api/atlas/automation-safety-profile/policies`` — UI-facing preset
  catalogue (6 Automation Profile presets, 4 capability tiers, envelope list).
* ``GET  /api/atlas/automation-safety-profile/latest`` — last persisted
  manifest for the resolved workspace (read-only).
* ``POST /api/atlas/automation-safety-profile/preview`` — validation-only call
  to ``create_automation_safety_profile``; never writes to disk.
* ``POST /api/atlas/automation-safety-profile/select`` — explicit selection.
  Requires the confirmation text. Writes the safety profile manifest AND, if
  an envelope is requested, a side-by-side envelope manifest carrying the
  derived activation flags.
* ``GET  /api/atlas/automation-safety-profile/pre-authorized-envelopes`` —
  envelope recipe catalogue.

All routes are read-only with respect to executable runtime state. Selecting a
profile writes a manifest; it does not start a loop. The autonomous loop runner
reads the envelope manifest separately when the user issues a chat command.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.atlas.automation_safety_profile import (
    PROFILE_AUTONOMOUS_DEV_AGENT,
    PROFILE_GUARDED_SINGLE_ACTION,
    PROFILE_ORDER,
    PROFILE_REVIEW_ONLY,
    PROFILE_SUPERVISED_BOUNDED_AUTO,
    SCHEMA_VERSION as SAFETY_PROFILE_SCHEMA_VERSION,
    SELF_IMPROVEMENT_SCOPES,
    SELF_SCOPE_ATLAS_RUNTIME_STRICT,
    SELF_SCOPE_NONE,
    create_automation_safety_profile,
    load_automation_safety_profile,
    write_automation_safety_profile,
    _PROFILE_CAPABILITIES,
)
from app.atlas.autonomous_loop_envelope_runner import (
    REQUEST_KIND_DEV,
    REQUEST_KIND_SELF_IMPROVEMENT,
    prepare_autonomous_loop_session,
)
from app.atlas.pre_authorized_bounded_dev_envelope import (
    ALLOWED_ENVELOPES,
    ENVELOPE_BOUNDED_DEV,
    ENVELOPE_NONE,
    ENVELOPE_SELF_IMPROVEMENT,
    SCHEMA_VERSION as ENVELOPE_SCHEMA_VERSION,
    TRACK_PR as ENVELOPE_TRACK_PR,
    build_envelope_manifest,
    list_envelopes,
)

router = APIRouter(
    prefix="/api/atlas/automation-safety-profile",
    tags=["atlas-automation-safety-profile"],
)

EXPECTED_CONFIRMATION_TEXT = "SELECT AUTOMATION PROFILE"
LEGACY_CONFIRMATION_TEXT = "SELECT AUTOMATION SAFETY PROFILE"

# UI-facing 6-preset catalogue. Each preset maps to a (safety_profile,
# envelope) tuple. ``self_improvement_*`` fields are the values the UI should
# auto-fill when this preset is picked.
AUTOMATION_PROFILE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "review_only",
        "rank": 0,
        "label": "Review Only",
        "description": "Atlas only proposes; nothing is mutated.",
        "safety_profile": PROFILE_REVIEW_ONLY,
        "envelope_id": ENVELOPE_NONE,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
        "strict_gate_approved": False,
        "level4_checkpoint_required": False,
        "enables_full_automation": False,
    },
    {
        "id": "single_action",
        "rank": 1,
        "label": "Single Action (manual approve)",
        "description": "One bounded mutation per explicit human approval.",
        "safety_profile": PROFILE_GUARDED_SINGLE_ACTION,
        "envelope_id": ENVELOPE_NONE,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
        "strict_gate_approved": False,
        "level4_checkpoint_required": False,
        "enables_full_automation": False,
    },
    {
        "id": "supervised_auto",
        "rank": 2,
        "label": "Supervised Auto",
        "description": "Atlas applies mutations only after each approval; loop is not autonomous.",
        "safety_profile": PROFILE_SUPERVISED_BOUNDED_AUTO,
        "envelope_id": ENVELOPE_NONE,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
        "strict_gate_approved": False,
        "level4_checkpoint_required": False,
        "enables_full_automation": False,
    },
    {
        "id": "autonomous_custom",
        "rank": 3,
        "label": "Autonomous (custom bounds)",
        "description": "Full autonomous capability; bounds must be supplied per request.",
        "safety_profile": PROFILE_AUTONOMOUS_DEV_AGENT,
        "envelope_id": ENVELOPE_NONE,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
        "strict_gate_approved": False,
        "level4_checkpoint_required": False,
        "enables_full_automation": False,
    },
    {
        "id": "autonomous_bounded_dev",
        "rank": 4,
        "label": "Autonomous",
        "description": "Full automatic code generation within a pre-authorised envelope. Envelope is selected by Work target: Dev/repair uses pre_authorized_bounded_dev_envelope; Self-improvement uses pre_authorized_self_improvement_envelope (requires strict gate + Level-4 checkpoint).",
        "safety_profile": PROFILE_AUTONOMOUS_DEV_AGENT,
        "envelope_id": ENVELOPE_BOUNDED_DEV,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
        "strict_gate_approved": False,
        "level4_checkpoint_required": False,
        "enables_full_automation": True,
        "work_target_envelope_map": {
            "software_development_or_repair": ENVELOPE_BOUNDED_DEV,
            "platform_self_improvement": ENVELOPE_SELF_IMPROVEMENT,
        },
    },
]


class PreviewRequest(BaseModel):
    profile: str = Field(default=PROFILE_REVIEW_ONLY)
    self_improvement_enabled: bool = Field(default=False)
    self_improvement_scope: str = Field(default=SELF_SCOPE_NONE)
    strict_gate_approved: bool = Field(default=False)
    explicit_profile_selection: bool = Field(default=True)
    envelope_id: str = Field(default=ENVELOPE_NONE)
    level4_checkpoint_path: str | None = Field(default=None)


class SelectRequest(PreviewRequest):
    confirmation_text: str
    level4_checkpoint_path: str | None = Field(default=None)


class StartAutonomousLoopRequest(BaseModel):
    request_kind: str = Field(default=REQUEST_KIND_DEV)
    loop_goal: str = Field(default="")
    requested_actions: int = Field(default=1)
    requested_files: int = Field(default=1)
    requested_runtime_seconds: int = Field(default=60)
    requested_risk_level: str = Field(default="low")
    requested_paths: list[str] = Field(default_factory=list)
    requested_commands: list[str] = Field(default_factory=list)


@router.get("/policies")
def get_policies() -> dict[str, Any]:
    """Return the UI preset catalogue and underlying capability matrix."""

    return {
        "schema_version": SAFETY_PROFILE_SCHEMA_VERSION,
        "envelope_schema_version": ENVELOPE_SCHEMA_VERSION,
        "envelope_track_pr": ENVELOPE_TRACK_PR,
        "expected_confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        "legacy_confirmation_text_accepted": LEGACY_CONFIRMATION_TEXT,
        "explicit_profile_selection_required": True,
        "automation_profile_presets": AUTOMATION_PROFILE_PRESETS,
        "safety_profiles": [
            {
                "id": name,
                "rank": rank,
                "capabilities": dict(_PROFILE_CAPABILITIES[name]),
            }
            for name, rank in PROFILE_ORDER.items()
        ],
        "self_improvement_scopes": sorted(SELF_IMPROVEMENT_SCOPES),
        "envelopes": sorted(ALLOWED_ENVELOPES),
    }


@router.get("/pre-authorized-envelopes")
def get_pre_authorized_envelopes() -> dict[str, Any]:
    """Return all envelope recipes (bound values, allowlists, blocked paths)."""

    return {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "track_pr": ENVELOPE_TRACK_PR,
        "envelopes": list_envelopes(),
    }


@router.get("/latest")
def get_latest(request: Request) -> dict[str, Any]:
    """Return the most recently persisted safety + envelope manifests."""

    data_root = resolve_atlas_ca_data_root(request)
    safety_manifest = _load_latest_safety_manifest(data_root)
    envelope_manifest = _load_latest_envelope_manifest(data_root)
    return {
        "available": safety_manifest is not None,
        "safety_profile": safety_manifest,
        "envelope": envelope_manifest,
    }


@router.post("/preview")
def preview_profile(payload: PreviewRequest) -> dict[str, Any]:
    """Run ``create_automation_safety_profile`` without writing to disk."""

    profile = _safe_create_profile(payload, data_root=None, write=False)
    envelope_preview: dict[str, Any] | None = None
    if payload.envelope_id and payload.envelope_id != ENVELOPE_NONE:
        envelope_preview = build_envelope_manifest(
            envelope_id=payload.envelope_id,
            safety_profile=profile,
            confirmation_text=EXPECTED_CONFIRMATION_TEXT,
            created_at=profile.get("created_at") or _utc_now(),
        )
    return {
        "safety_profile": profile,
        "envelope": envelope_preview,
        "enables_full_automation": _envelope_enables_full_automation(envelope_preview),
    }


@router.post("/select")
def select_profile(request: Request, payload: SelectRequest) -> dict[str, Any]:
    """Persist a safety profile and (optionally) an envelope manifest."""

    if payload.confirmation_text not in (
        EXPECTED_CONFIRMATION_TEXT,
        LEGACY_CONFIRMATION_TEXT,
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "confirmation_text_required",
                "expected": EXPECTED_CONFIRMATION_TEXT,
            },
        )

    data_root = resolve_atlas_ca_data_root(request)
    profile = _safe_create_profile(payload, data_root=data_root, write=True)
    if profile.get("status") != "active":
        return {
            "status": "blocked",
            "safety_profile": profile,
            "envelope": None,
            "manifest_paths": {},
        }

    safety_path = write_automation_safety_profile(data_root=data_root, profile=profile)

    envelope_manifest: dict[str, Any] | None = None
    envelope_path: Path | None = None
    if payload.envelope_id and payload.envelope_id != ENVELOPE_NONE:
        envelope_manifest = build_envelope_manifest(
            envelope_id=payload.envelope_id,
            safety_profile=profile,
            confirmation_text=payload.confirmation_text,
            created_at=profile.get("created_at") or _utc_now(),
        )
        envelope_path = _write_envelope_manifest(data_root, envelope_manifest)

    return {
        "status": "active",
        "safety_profile": profile,
        "envelope": envelope_manifest,
        "enables_full_automation": _envelope_enables_full_automation(envelope_manifest),
        "manifest_paths": {
            "safety_profile": str(safety_path),
            "envelope": str(envelope_path) if envelope_path else "",
        },
    }


@router.post("/start-autonomous-loop")
def start_autonomous_loop(
    request: Request, payload: StartAutonomousLoopRequest
) -> dict[str, Any]:
    """Prepare an autonomous loop session bounded by the persisted envelope.

    This endpoint does not execute commands. It produces a session record that
    downstream autopilot routes can consume. Bound violations are reported as
    blocking reasons in the response.
    """

    if payload.request_kind not in (REQUEST_KIND_DEV, REQUEST_KIND_SELF_IMPROVEMENT):
        raise HTTPException(
            status_code=400,
            detail={"error": "request_kind_not_allowed", "value": payload.request_kind},
        )

    data_root = resolve_atlas_ca_data_root(request)
    session = prepare_autonomous_loop_session(
        data_root=data_root,
        request_kind=payload.request_kind,
        loop_goal=payload.loop_goal,
        requested_actions=payload.requested_actions,
        requested_files=payload.requested_files,
        requested_runtime_seconds=payload.requested_runtime_seconds,
        requested_risk_level=payload.requested_risk_level,
        requested_paths=payload.requested_paths,
        requested_commands=payload.requested_commands,
    )
    return session


def _safe_create_profile(
    payload: PreviewRequest, *, data_root: Path | None, write: bool
) -> dict[str, Any]:
    checkpoint_path: Path | None = None
    if payload.level4_checkpoint_path:
        checkpoint_path = Path(payload.level4_checkpoint_path)
    try:
        return create_automation_safety_profile(
            profile=payload.profile,
            data_root=data_root,
            level4_checkpoint_path=checkpoint_path,
            self_improvement_enabled=payload.self_improvement_enabled,
            self_improvement_scope=payload.self_improvement_scope,
            explicit_profile_selection=payload.explicit_profile_selection,
            strict_gate_approved=payload.strict_gate_approved,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "automation_safety_profile_validation_error", "reason": str(exc)},
        ) from exc


def _envelope_enables_full_automation(envelope: dict[str, Any] | None) -> bool:
    if not envelope:
        return False
    return bool(
        envelope.get("status") == "active"
        and envelope.get("autonomous_loop_execution_enabled")
    )


def _envelope_dir(data_root: Path) -> Path:
    return data_root / "atlas" / "pre_authorized_envelopes"


def _write_envelope_manifest(data_root: Path, manifest: dict[str, Any]) -> Path:
    envelope_dir = _envelope_dir(data_root)
    envelope_dir.mkdir(parents=True, exist_ok=True)
    safety_profile_id = manifest.get("safety_profile_id") or "unknown"
    envelope_id = manifest.get("envelope_id") or "unknown"
    file_name = f"{envelope_id}__{safety_profile_id}.json"
    path = envelope_dir / file_name
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _load_latest_safety_manifest(data_root: Path) -> dict[str, Any] | None:
    root = data_root / "atlas" / "automation_safety_profiles"
    if not root.is_dir():
        return None
    manifests: list[tuple[float, Path]] = []
    for child in root.iterdir():
        manifest_path = child / "manifest.json"
        if manifest_path.is_file():
            manifests.append((manifest_path.stat().st_mtime, manifest_path))
    if not manifests:
        return None
    manifests.sort()
    latest_path = manifests[-1][1]
    try:
        return load_automation_safety_profile(
            manifest_path=latest_path, data_root=data_root
        )
    except (ValueError, FileNotFoundError, json.JSONDecodeError):
        return None


def _load_latest_envelope_manifest(data_root: Path) -> dict[str, Any] | None:
    envelope_dir = _envelope_dir(data_root)
    if not envelope_dir.is_dir():
        return None
    files = [p for p in envelope_dir.iterdir() if p.is_file() and p.suffix == ".json"]
    if not files:
        return None
    files.sort(key=lambda path: path.stat().st_mtime)
    latest = files[-1]
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except (ValueError, FileNotFoundError, json.JSONDecodeError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
