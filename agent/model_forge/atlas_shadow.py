"""Advisory Forge method/evaluation observations for Atlas execution phases."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import Field

from agent.model_forge.capability_scoring import build_capability_profile
from agent.model_forge.execution_policy import ExecutionPolicySelector
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel
from agent.model_forge.stage_taxonomy import ForgeStage, StageMode
from agent.twin_control_plane.proof_ledger import ProofLedgerEntry, ProofLedgerStore


_STAGE_CHANGE_CLASS = {
    ForgeStage.PLANNING: ChangeClass.LARGE,
    ForgeStage.PATCH_GENERATION: ChangeClass.SMALL,
    ForgeStage.VERIFICATION_INTERPRETATION: ChangeClass.TRIVIAL,
    ForgeStage.REPAIR: ChangeClass.SMALL,
}


class AtlasExecutionShadowRecord(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    request_id: str = Field(min_length=1)
    stage: ForgeStage
    task_category: str = ""
    result_status: str = ""
    result_digest: str = ""
    policy_id: str = ""
    provider_id: str = ""
    model_id: str = ""
    method_variant: str = ""
    method_fallbacks: list[str] = Field(default_factory=list)
    evaluation_refs: list[str] = Field(default_factory=list)
    unavailable_reasons: list[str] = Field(default_factory=list)
    decision: str = "shadow_recorded_legacy_primary"
    changes_production_routing: bool = False
    active_auto_enabled: bool = False
    recorded_at: str = ""
    proof_ledger_ref: str = ""


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value) or "unknown"


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + sha256(raw).hexdigest()


def record_atlas_execution_shadow(
    service: Any,
    *,
    stage: ForgeStage | str,
    request_id: str,
    task_category: str,
    result_payload: Any,
    result_status: str = "",
    provider_id: str = "",
    model_id: str = "",
) -> str:
    """Record a method recommendation without changing the supplied Atlas result."""
    stage = ForgeStage(stage)
    if service.stage_matrix.get_entry(stage).mode != StageMode.SHADOW_SELECT:
        return ""

    profiles = service.profiles.list_profiles()
    selected = None
    if provider_id and model_id:
        selected = service.profiles.load_profile(provider_id, model_id)
    if selected is None and profiles:
        selected = sorted(profiles, key=lambda item: (item.provider_id, item.model_id))[0]
    capability = build_capability_profile(
        selected,
        provider_id=provider_id or (selected.provider_id if selected else ""),
        model_id=model_id or (selected.model_id if selected else "default"),
    )
    policy = ExecutionPolicySelector().select(
        _STAGE_CHANGE_CLASS.get(stage, ChangeClass.SMALL),
        task_category=task_category,
        model_profile=capability,
    )
    evaluation_refs = list(selected.evidence_refs) if selected else []
    unavailable = [] if selected else ["model_evaluation_profile:unavailable"]
    record = AtlasExecutionShadowRecord(
        request_id=request_id,
        stage=stage,
        task_category=task_category,
        result_status=result_status,
        result_digest=_digest(result_payload),
        policy_id=policy.policy_id,
        provider_id=capability.provider_id,
        model_id=capability.model_id,
        method_variant=policy.method_variant.value if policy.method_variant else "",
        method_fallbacks=[item.value for item in policy.method_fallbacks],
        evaluation_refs=evaluation_refs,
        unavailable_reasons=unavailable,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    root = Path(service._ca_data_root)  # ForgeService owns this root; artifacts stay Atlas-local.
    artifact = root / "model_forge" / "atlas_shadow" / stage.value / f"{_safe_id(request_id)}.json"
    ledger = ProofLedgerEntry(
        entry_id=f"forge_shadow:{stage.value}:{request_id}",
        plan_item_ref=request_id,
        policy_id=policy.policy_id,
        model_id=capability.model_id,
        provider_id=capability.provider_id,
        runtime_evidence_refs=[str(artifact), *evaluation_refs],
        decision="shadow_recorded_legacy_primary",
        accepted=False,
        proof_requirements=[
            "Forge shadow evidence is advisory and cannot change production routing.",
            "Proposal, Safe Apply, Verification, and existing Atlas authority remain required.",
        ],
        forge_stage=stage.value,
        method_variant=record.method_variant,
        method_fallbacks=list(record.method_fallbacks),
        forge_evaluation_refs=evaluation_refs,
    )
    ProofLedgerStore(root / "twin_control_plane" / "proof_ledger").append(ledger, ledger_id="forge_shadow")
    record.proof_ledger_ref = ledger.entry_id
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(artifact)


__all__ = ["AtlasExecutionShadowRecord", "record_atlas_execution_shadow"]
