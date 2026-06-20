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
    _project_twin_db_path,
    build_twin_pipeline_evidence,
    expand_changed_refs_to_symbols,
    load_project_twin_store,
    refresh_project_twin,
    resolve_build_project_twin,
    resolve_pipeline_mode,
    resolve_twin_autobuild,
    try_project_twin_impact,
)

# Source extensions whose mtime indicates the project changed since the Twin was last built. The
# Twin's static projection indexes these; a change to any means the cached Twin is stale.
_TWIN_SOURCE_EXTS = (".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".vue", ".json", ".go", ".rs", ".java")
# Skip heavy/irrelevant trees so the staleness scan stays cheap on a real repo.
_TWIN_SKIP_DIRS = {".git", "node_modules", "venv", "venv_sys", "__pycache__", ".pytest_cache", "dist", "build", ".venv"}


def _newest_source_mtime(project_path: str) -> float:
    """Newest mtime among the project's source files (bounded walk). 0.0 when none/unreadable.
    Used to decide whether a cached Project Twin is stale and must be refreshed."""
    import os

    newest = 0.0
    scanned = 0
    try:
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in _TWIN_SKIP_DIRS]
            for name in files:
                if not name.endswith(_TWIN_SOURCE_EXTS):
                    continue
                try:
                    m = os.path.getmtime(os.path.join(root, name))
                    if m > newest:
                        newest = m
                except OSError:
                    continue
                scanned += 1
                if scanned >= 5000:  # bound the scan on a very large tree
                    return newest
    except Exception:  # noqa: BLE001
        return newest
    return newest


def fresh_project_twin(*, data_root, project_id: str, project_path: str):
    """Return a Project Twin that reflects the CURRENT project state.

    Builds when no Twin exists yet (first encounter of an existing project), and REFRESHES when the
    project changed since the cached Twin was built (e.g. a greenfield project after earlier items
    created files, an existing project being revised, or a plan reloaded from history after edits).
    Otherwise reuses the cached Twin (cheap). This fixes the staleness in ``ensure_project_twin``,
    which returns the cached Twin unconditionally when its DB exists. Never raises -> None."""
    try:
        from pathlib import Path

        if not project_path or not Path(project_path).is_dir():
            return None
        db_path = Path(_project_twin_db_path(str(data_root), project_id))
        if not db_path.exists():
            return refresh_project_twin(data_root=str(data_root), project_id=project_id, project_path=project_path)
        newest_src = _newest_source_mtime(project_path)
        try:
            twin_mtime = db_path.stat().st_mtime
        except OSError:
            twin_mtime = 0.0
        if newest_src > twin_mtime:
            return refresh_project_twin(data_root=str(data_root), project_id=project_id, project_path=project_path)
        return load_project_twin_store(data_root=str(data_root), project_id=project_id)
    except Exception:  # noqa: BLE001 - advisory; degrade to no twin
        return None


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

        # Build/refresh the Project Twin so impact / Safe-Edit Briefing reflect the CURRENT code
        # (the dependency-awareness that lifts a weak model). Active mode autobuilds by default; the
        # explicit build flag forces it in any mode. fresh_project_twin refreshes when the project
        # changed since the last build, so every condition stays correct — first read of an existing
        # project, a greenfield project after earlier items created files, a plan reloaded from
        # history, or an existing project being revised.
        store = None
        if project_path and (resolve_build_project_twin() or (mode == PipelineMode.ACTIVE and resolve_twin_autobuild())):
            store = fresh_project_twin(data_root=str(data_root), project_id=project_id, project_path=project_path)
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
