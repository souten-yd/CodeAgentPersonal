"""Bring Twin Control Plane injection to the general / manual patch-generation path.

The autonomous codegen orchestrator consults the Twin Control Plane before generation and passes
``twin_generation_hints`` (the COMPILED instruction: interface contracts + dependency impact +
Safe-Edit Briefing + anti-pattern guardrails + golden examples, all adapted to the active model's
known weaknesses) into patch generation. That dependency-awareness is what lifts a weak local model
on a real codebase — but it only ran inside the autonomous loop.

This module exposes the same consultation as a standalone function so the per-item patch endpoint
(and any manual approve/execute flow) gets the same lift. The patch service already consumes
``request.metadata["twin_generation_hints"]["twin_instruction"]`` and composes it into the generation
system prompt (see ``AtlasPatchProposalService.propose_for_item`` /
``compose_generation_system_prompt``), so callers only need to merge the returned hints into the
request metadata.

Advisory only: this never overrides Atlas's Proposal / Safe Apply / Verification authority, and it
never raises — any failure degrades to ``{}`` (no hints), preserving the legacy behaviour.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.atlas_plan_item_file_changes import normalize_plan_item_file_changes
from agent.twin_control_plane.pipeline_integration import (
    PipelineMode,
    build_twin_pipeline_evidence,
    ensure_project_twin,
    expand_changed_refs_to_symbols,
    load_project_twin_store,
    resolve_build_project_twin,
    resolve_pipeline_mode,
    resolve_twin_autobuild,
    try_project_twin_impact,
)


def _load_anti_pattern_memory(data_root: Any):
    """Durable Anti-Pattern memory so prior-run guardrails advise this run (or None)."""
    try:
        from agent.twin_control_plane.anti_pattern_memory import AntiPatternMemoryStore

        return AntiPatternMemoryStore(Path(data_root) / "twin_control_plane" / "anti_pattern_memory").load()
    except Exception:  # pragma: no cover - advisory; degrade to empty
        return None


def _load_golden_index(data_root: Any):
    """Durable accepted golden patches as an advisory retrieval index (or None)."""
    try:
        from agent.model_forge.golden_patch_retrieval import GoldenPatchStore

        return GoldenPatchStore(Path(data_root) / "twin_control_plane" / "golden_patches").load_index()
    except Exception:  # pragma: no cover - advisory; degrade to empty
        return None


def hints_from_evidence(evidence: dict) -> dict:
    """Map a Twin pipeline evidence dict to ``{"twin_generation_hints": {...}}`` for patch generation.
    Empty when the seam is off/unavailable or no compiled instruction was produced."""
    if not isinstance(evidence, dict) or not evidence.get("available") or evidence.get("mode") == "off":
        return {}
    seb = evidence.get("safe_edit_briefing") or {}
    dependent_files = list(seb.get("dependent_files") or []) if isinstance(seb, dict) else []
    hints = {
        "twin_route": evidence.get("route"),
        "twin_instruction_style": evidence.get("instruction_style"),
        "twin_injection_level": evidence.get("twin_injection_level"),
        "twin_policy_id": evidence.get("policy_id"),
        # The compiled Twin instruction — the bounded control section injected into the system prompt.
        "twin_instruction": evidence.get("compiled_instruction"),
        "twin_instruction_id": evidence.get("instruction_id"),
        # Files the Twin found depend on this change — generation ranks/loads their symbols so the
        # model edits with the dependents' real API in view (impact-driven context selection).
        "impacted_dependent_files": dependent_files or None,
    }
    hints = {k: v for k, v in hints.items() if v is not None}
    if not hints.get("twin_instruction"):
        return {}
    return {"twin_generation_hints": hints}


def build_twin_generation_hints(*, data_root: Any, pool: Any, item: Any, request_metadata: dict | None = None) -> dict:
    """Consult the Twin Control Plane for one plan item and return ``{"twin_generation_hints": {...}}``
    suitable to merge into a patch-proposal request's metadata. Mirrors the autonomous orchestrator's
    pre-generation Twin consultation. Never raises -> ``{}`` on any error or when the seam is off."""
    try:
        mode = resolve_pipeline_mode()
        if mode == PipelineMode.OFF:
            return {}
        req_md = request_metadata or {}
        project_id = str(getattr(pool, "pool_id", "") or getattr(pool, "project_id", "") or "")
        project_path = str(getattr(pool, "project_path", "") or "")
        changed_refs: list[str] = []
        for tf in (getattr(item, "target_files", []) or []):
            if tf:
                changed_refs.append(str(tf))
        try:
            for ch in (normalize_plan_item_file_changes(item) or []):
                p = ch.get("path") if isinstance(ch, dict) else None
                if p:
                    changed_refs.append(str(p))
        except Exception:  # noqa: BLE001 - file_changes optional pre-generation
            pass

        # Build/refresh the Project Twin from the live project so impact / Safe-Edit Briefing reflect
        # the current code (the dependency-awareness that lifts a weak model). Active mode autobuilds
        # by default; the explicit build flag forces it in any mode.
        store = None
        if project_path and (resolve_build_project_twin() or (mode == PipelineMode.ACTIVE and resolve_twin_autobuild())):
            store = ensure_project_twin(data_root=str(data_root), project_id=project_id, project_path=project_path)
        elif resolve_build_project_twin():
            store = load_project_twin_store(data_root=str(data_root), project_id=project_id)

        impact_refs = expand_changed_refs_to_symbols(store, project_id, changed_refs)
        impact = try_project_twin_impact(project_id=project_id, changed_refs=impact_refs, store=store)

        evidence = build_twin_pipeline_evidence(
            mode=mode,
            requirement=str(getattr(pool, "root_goal", "") or ""),
            pool_id=project_id,
            project_path=project_path,
            changed_refs=changed_refs,
            item_refs=[str(getattr(item, "item_id", "") or "")],
            impact=impact,
            model_id=str(req_md.get("model_id") or req_md.get("forge_model_id") or ""),
            provider_id=str(req_md.get("provider_id") or req_md.get("forge_provider_id") or ""),
            profile_store_dir=str(Path(data_root) / "model_forge" / "profiles"),
            anti_pattern_memory=_load_anti_pattern_memory(data_root),
            golden_index=_load_golden_index(data_root),
        )
        return hints_from_evidence(evidence)
    except Exception:  # noqa: BLE001 - advisory; never break patch generation
        return {}
