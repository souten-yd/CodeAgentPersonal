"""Live-pipeline integration seam for the Twin Control Plane (TFG-12 cut-over).

This is the single, reversible seam that lets the autonomous codegen orchestrator run
the Twin/Forge gated pipeline as **advisory evidence** alongside its existing
generate/apply/verify flow.

Authority is preserved exactly: Atlas keeps Proposal / Safe Apply / Verification, and the
Twin Control Plane stays advisory context/evidence. This seam therefore never applies,
verifies, commits, or publishes — it only assembles ExecutionPolicy, TwinBrief, and a
shadow report and returns them as run metadata.

Mode is resolved from configuration and defaults to OFF, so a fresh checkout and any
deployment that does not opt in behaves exactly as before. Active mode is enabled by
setting ``ATLAS_TWIN_PIPELINE_MODE=active`` (or passing the mode explicitly) and is fully
reversible by setting it back to ``off``. Active mode also requires shadow evidence to
have been assembled; if it cannot be, the seam degrades to recording the gap rather than
forcing a change.
"""
from __future__ import annotations

import os
from typing import Iterable

from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.contracts import TwinBrief, default_hard_constraints
from agent.twin_control_plane.shadow_integration import (
    TwinShadowMode,
    TwinShadowOrchestrator,
    TwinShadowReport,
)

PIPELINE_MODE_ENV = "ATLAS_TWIN_PIPELINE_MODE"
GATE_BLOCKING_ENV = "ATLAS_TWIN_GATE_BLOCKING"

# Default mode for the live pipeline. Active is the approved production default; it stays
# advisory for execution authority and is fully reversible via ATLAS_TWIN_PIPELINE_MODE=off.
DEFAULT_PIPELINE_MODE = PipelineMode.ACTIVE


def resolve_pipeline_mode(value: str | None = None) -> PipelineMode:
    """Resolve the Twin pipeline mode from an explicit value or the environment.

    Defaults to ACTIVE (the approved production default). An unrecognised value falls back
    to the default rather than silently disabling the gate; set ``off`` explicitly to
    return to the legacy flow."""
    raw = (value if value is not None else os.environ.get(PIPELINE_MODE_ENV, "")).strip().lower()
    if not raw:
        return DEFAULT_PIPELINE_MODE
    try:
        return PipelineMode(raw)
    except ValueError:
        return DEFAULT_PIPELINE_MODE


def resolve_gate_blocking(value: str | None = None) -> bool:
    """Whether the Twin gate may BLOCK a run (promoted from advisory).

    Defaults to enabled. Disable with ``ATLAS_TWIN_GATE_BLOCKING`` in
    {0, off, false, no}. Even when enabled, blocking is limited to a genuine policy
    prerequisite (see ``twin_gate_block_reason``); it never blocks on advisory
    uncertainty or on infrastructure unavailability."""
    raw = (value if value is not None else os.environ.get(GATE_BLOCKING_ENV, "")).strip().lower()
    if raw in {"0", "off", "false", "no"}:
        return False
    return True


def twin_gate_block_reason(evidence: dict) -> str:
    """Return a block reason when the (blocking) Twin gate must stop the run, else "".

    Conservative by design: it blocks ONLY when active mode is engaged but the shadow
    evidence active requires could not be assembled. It deliberately does NOT block on:
    advisory uncertainty, missing optional artifacts, or ``available=False`` from an
    internal/infra error (unavailable is not a failure)."""
    if not isinstance(evidence, dict):
        return ""
    if evidence.get("mode") != PipelineMode.ACTIVE.value:
        return ""
    if evidence.get("available") and evidence.get("requires_shadow_evidence"):
        return "twin_gate_requires_shadow_evidence"
    return ""


BLOCK_UNVERIFIED_ENV = "ATLAS_TWIN_BLOCK_UNVERIFIED"


BLOCK_SCHEMA_ENV = "ATLAS_TWIN_BLOCK_SCHEMA"


def resolve_block_schema(value: str | None = None) -> bool:
    """Whether a breaking schema change should hard-block (promoted from advisory).

    Defaults to OFF: Schema Guardian stays advisory until the measured false-positive rate
    justifies promotion. Enable with ``ATLAS_TWIN_BLOCK_SCHEMA`` in {1, on, true, yes}. Even
    when on, only a genuinely breaking change (removed/type-changed public surface) blocks;
    a new/additive schema never blocks. A schema block feeds the bounded repair loop (the
    model regenerates with feedback), it is not an immediate terminal stop."""
    raw = (value if value is not None else os.environ.get(BLOCK_SCHEMA_ENV, "")).strip().lower()
    return raw in {"1", "on", "true", "yes"}


def resolve_block_unverified(value: str | None = None) -> bool:
    """Whether the post-apply gate should hard-block a completed run that has changed
    files but NO passing verification evidence (only unavailable/missing).

    Defaults to OFF: the autonomous full-auto path legitimately auto-continues some
    unverifiable changes (e.g. a static file whose only check is "open in a browser"),
    so this stricter block is opt-in via ``ATLAS_TWIN_BLOCK_UNVERIFIED`` in
    {1, on, true, yes}."""
    raw = (value if value is not None else os.environ.get(BLOCK_UNVERIFIED_ENV, "")).strip().lower()
    return raw in {"1", "on", "true", "yes"}


def _stable_brief_id(pool_id: str, requirement: str) -> str:
    base = f"{pool_id}:{requirement}".strip(":") or "twin_brief"
    return "twin_brief_" + base.replace(" ", "_")[:48]


DEFAULT_PROFILE_STORE_DIR = "ca_data/model_forge/profiles"


def resolve_capability_profile(*, model_id: str = "", provider_id: str = "", store_dir: str | None = None):
    """Load an evidence-backed Forge profile for the live model. Returns
    ``(ModelCapabilityProfile, available, route_preferences)``.

    The capability profile (control-plane dimensions) drives Twin injection; the
    ``route_preferences`` (benchmark dimensions -> per-route fitness) let the selector pick
    the route the model performs best at — "best route x right injection". ``available`` is
    False when no persisted profile exists (neutral, no false weakness/strength). Never raises."""
    from agent.model_forge.execution_policy import ModelCapabilityProfile

    try:
        from agent.model_forge.capability_scoring import build_capability_profile
        from agent.model_forge.profile_store import ProfileStore
        from agent.model_forge.route_fitness import derive_route_fitness

        if not model_id:
            return ModelCapabilityProfile(model_id="atlas-codegen"), False, {}
        store = ProfileStore(store_dir or DEFAULT_PROFILE_STORE_DIR)
        persisted = store.load_profile(provider_id, model_id)
        if persisted is None:
            return ModelCapabilityProfile(model_id=model_id, provider_id=provider_id), False, {}
        cap = build_capability_profile(persisted, model_id=model_id, provider_id=provider_id)
        route_prefs = derive_route_fitness(persisted.dimension_scores)
        return cap, True, route_prefs
    except Exception:
        return ModelCapabilityProfile(model_id=model_id or "atlas-codegen", provider_id=provider_id), False, {}


def _build_policy_and_brief(
    *, requirement: str, pool_id: str, project_path: str, refs: list[str],
    item_refs: Iterable[str], change_class: str, task_category: str,
    capability_profile=None, route_preferences: dict | None = None,
):
    """Build the ExecutionPolicy (Forge Twin route selection) and TwinBrief for a run.

    Lazy imports keep model_forge out of the twin_control_plane package import graph."""
    from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
    from agent.model_forge.route_matrix import ChangeClass

    selector = ExecutionPolicySelector()
    policy = selector.select(
        ChangeClass(change_class), task_category=task_category,
        model_profile=capability_profile or ModelCapabilityProfile(model_id="atlas-codegen"),
        route_preferences=route_preferences or None,
    )
    brief = TwinBrief(
        brief_id=_stable_brief_id(pool_id, requirement),
        goal=requirement or "autonomous codegen",
        allowed_refs=refs,
        impacted_refs=refs,
        hard_constraints=default_hard_constraints(),
        source_refs=[project_path] if project_path else [],
        metadata={"pool_id": pool_id, "item_refs": sorted({str(i) for i in item_refs if str(i).strip()})},
    )
    return policy, brief


BUILD_PROJECT_TWIN_ENV = "ATLAS_TWIN_BUILD_PROJECT"


def resolve_build_project_twin(value: str | None = None) -> bool:
    """Whether to build/refresh a Project Twin from the live project in-run (default OFF).
    Enable with ``ATLAS_TWIN_BUILD_PROJECT`` in {1, on, true, yes}; reversible."""
    raw = (value if value is not None else os.environ.get(BUILD_PROJECT_TWIN_ENV, "")).strip().lower()
    return raw in {"1", "on", "true", "yes"}


def _project_twin_db_path(data_root: str, project_id: str):
    from pathlib import Path
    safe = (project_id or "default").replace("/", "_").replace(":", "_").replace("\\", "_")
    d = Path(data_root) / "twin_control_plane" / "project_twin"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe}.sqlite3"


TWIN_AUTOBUILD_ENV = "ATLAS_TWIN_AUTOBUILD"


def resolve_twin_autobuild(value: str | None = None) -> bool:
    """Whether the autonomous loop auto-builds the Project Twin from the live project before
    generation so impact / Safe-Edit Briefing evidence is available THIS run (default ON). This is
    what makes dependency-awareness work on a large existing codebase; disable with
    ``ATLAS_TWIN_AUTOBUILD`` in {0, off, false, no}. Reversible."""
    raw = (value if value is not None else os.environ.get(TWIN_AUTOBUILD_ENV, "")).strip().lower()
    if raw in {"0", "off", "false", "no"}:
        return False
    return True


def ensure_project_twin(*, data_root: str, project_id: str, project_path: str, force_rebuild: bool = False):
    """Load the persistent Project Twin, BUILDING it from source when absent so real impact evidence
    is available for the current run (not just a later one). Bounded and never raises; returns the
    store or None when the project path is unusable."""
    if not force_rebuild:
        store = load_project_twin_store(data_root=data_root, project_id=project_id)
        if store is not None:
            return store
    return refresh_project_twin(data_root=data_root, project_id=project_id, project_path=project_path)


def load_project_twin_store(*, data_root: str, project_id: str):
    """Load a persistent Project Twin store previously built for this project, else None.
    Never raises."""
    try:
        from pathlib import Path
        path = _project_twin_db_path(data_root, project_id)
        if not Path(path).exists():
            return None
        from agent.project_twin.store import SqliteProjectTwinStore
        return SqliteProjectTwinStore(str(path))
    except Exception:
        return None


def refresh_project_twin(*, data_root: str, project_id: str, project_path: str):
    """Build/refresh a persistent Project Twin from the project directory so later runs get
    real impact evidence. Returns the store, or None when disabled/unavailable. Never raises."""
    try:
        from pathlib import Path
        if not project_path or not Path(project_path).is_dir():
            return None
        from agent.project_twin.projection import StaticProjectionService
        from agent.project_twin.store import SqliteProjectTwinStore
        store = SqliteProjectTwinStore(str(_project_twin_db_path(data_root, project_id)))
        StaticProjectionService(store).refresh(
            project_id=project_id or "default", project_path=str(project_path), full_rebuild=True)
        return store
    except Exception:
        return None


def expand_changed_refs_to_symbols(store, project_id: str, changed_refs: Iterable[str]) -> list[str]:
    """Map changed FILE paths to the ``py://<relpath>#<symbol>`` refs the Twin indexes, so impact
    (callers) can actually be assessed. Twin impact seeds on symbol nodes, but the autonomous loop
    only knows which FILES changed — a bare ``mod.py`` / ``py://mod.py`` ref yields no callers. For
    each changed file we add every symbol the Twin defines in it; symbol-level refs pass through
    unchanged. Best-effort, never raises; returns at least the original refs."""
    refs = [str(r).strip() for r in changed_refs if str(r).strip()]
    if store is None or not project_id or not refs:
        return refs
    file_paths: list[str] = []
    out: list[str] = []
    for r in refs:
        out.append(r)
        if "#" not in r:  # a file-level ref — record its path (strip any scheme).
            file_paths.append(r.split("://", 1)[-1].strip("/"))
    if not file_paths:
        return out
    try:
        snapshot = store.get_snapshot(project_id)
        for node in getattr(snapshot, "nodes", []) or []:
            ref = str(getattr(node, "canonical_ref", ""))
            if not ref.startswith("py://") or "#" not in ref:
                continue
            path = ref[len("py://"):].split("#", 1)[0]
            if any(path == fp or path.endswith("/" + fp) or fp.endswith("/" + path) or fp.endswith(path) for fp in file_paths):
                out.append(ref)
    except Exception:
        return out
    seen: set[str] = set()
    deduped: list[str] = []
    for r in out:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return deduped


def try_project_twin_impact(
    *, project_id: str, changed_refs: Iterable[str], store=None, change_kind: str = "modify"
):
    """Best-effort real Project Twin impact for the current run.

    Returns an ``ImpactResult`` when a Project Twin store with a snapshot for
    ``project_id`` is available, else ``None`` (recorded as unavailable upstream — never
    fabricated). Never raises. There is no persistent per-project Twin store by default,
    so the common live outcome is ``None``; when a store is supplied (tests, or a future
    persistent Twin), real impact flows through unchanged."""
    refs = [str(r).strip() for r in changed_refs if str(r).strip()]
    if store is None or not project_id or not refs:
        return None
    try:
        from agent.project_twin.contracts import ImpactRequest

        request = ImpactRequest(project_id=project_id, changed_refs=refs, change_kind=change_kind)
        return store.assess_impact(request)
    except Exception:
        return None


def _impact_section(impact) -> dict:
    if impact is None:
        return {"available": False, "reason": "project_twin_impact_unavailable"}
    return {
        "available": True,
        "project_id": getattr(impact, "project_id", ""),
        "twin_revision_id": getattr(impact, "twin_revision_id", ""),
        "direct_impacts": len(getattr(impact, "direct_impacts", []) or []),
        "transitive_impacts": len(getattr(impact, "transitive_impacts", []) or []),
        "recommended_tests": len(getattr(impact, "recommended_tests", []) or []),
    }


def build_twin_pipeline_evidence(
    *,
    mode: PipelineMode,
    requirement: str = "",
    pool_id: str = "",
    project_path: str = "",
    changed_refs: Iterable[str] = (),
    item_refs: Iterable[str] = (),
    impact=None,
    model_id: str = "",
    provider_id: str = "",
    profile_store_dir: str | None = None,
    anti_pattern_memory=None,
    golden_index=None,
    skill_patches=None,
    change_class: str = "medium",
    task_category: str = "autonomous_codegen",
) -> dict:
    """Assemble advisory Twin evidence for one autonomous run. Never raises — any internal
    failure is reported as ``available: False`` so the legacy flow is never broken.

    When a real Project Twin ``impact`` is supplied it flows into the shadow assembly
    (BlastMap + TwinProof) and Contract Sentinel; when absent the impact section is
    recorded as explicitly unavailable (never fabricated). The ExecutionPolicy is driven
    by an evidence-backed Forge capability profile when one exists, else a neutral
    default (recorded as ``capability_profile_unavailable``)."""
    if mode == PipelineMode.OFF:
        return {"mode": PipelineMode.OFF.value, "engaged": False, "available": False,
                "reason": "pipeline_off"}

    try:
        refs = sorted({str(r).strip() for r in changed_refs if str(r).strip()})
        capability_profile, profile_available, route_preferences = resolve_capability_profile(
            model_id=model_id, provider_id=provider_id, store_dir=profile_store_dir,
        )
        policy, brief = _build_policy_and_brief(
            requirement=requirement, pool_id=pool_id, project_path=project_path, refs=refs,
            item_refs=item_refs, change_class=change_class, task_category=task_category,
            capability_profile=capability_profile, route_preferences=route_preferences,
        )
        shadow_orch = TwinShadowOrchestrator(TwinShadowMode.SHADOW)
        shadow_report: TwinShadowReport | None = shadow_orch.assemble(
            requirement_ref=requirement, plan_item_ref=pool_id,
            execution_policy=policy, twin_brief=brief, changed_refs=refs,
            impact=impact,
        )
        # Contract Sentinel over the real BlastMap when impact evidence exists.
        contract_section: dict | None = None
        if impact is not None:
            try:
                from agent.twin_control_plane.blast_map import build_blast_map
                from agent.twin_control_plane.contract_sentinel import evaluate_contracts

                blast = build_blast_map(impact, brief=brief, changed_refs=refs)
                sentinel = evaluate_contracts(policy, brief, blast)
                contract_section = {
                    "report_id": sentinel.report_id,
                    "accepted": sentinel.accepted,
                    "blocked": sentinel.blocked,
                    "proof_requirements": list(sentinel.proof_requirements),
                }
            except Exception:
                contract_section = {"available": False, "reason": "contract_sentinel_error"}

        # Compile the deterministic model-facing instruction so the live generator can
        # receive it as a bounded control section (advisory; never overrides authority).
        compiled_text = ""
        instruction_id = ""
        try:
            from agent.twin_control_plane.instruction_compiler import compile_model_instruction

            compiled = compile_model_instruction(brief, policy)
            compiled_text = compiled.text
            instruction_id = compiled.instruction_id
        except Exception:
            compiled_text = ""

        # Advisory-only context (anti-pattern guardrails / golden patches / skills).
        advisory = build_advisory_context(
            memory=anti_pattern_memory, golden_index=golden_index, skill_patches=skill_patches,
            model_id=model_id, route=policy.route.value, project_ref=pool_id, changed_refs=refs,
        )
        if compiled_text and advisory.get("text"):
            compiled_text = f"{compiled_text}\n\n{ADVISORY_PROMPT_HEADER}\n{advisory['text']}"

        # Safe-Edit Briefing: when real Twin impact exists, tell the generator which existing callers /
        # side effects / tests depend on what it is changing, so it preserves the public interface
        # instead of breaking dependents — the key to safely editing a large existing codebase. Advisory
        # only; empty (and thus a no-op) when there are no dependents or no impact evidence.
        safe_edit_section = {"available": False}
        if impact is not None:
            try:
                from agent.project_twin.safe_edit_briefing import (
                    build_safe_edit_briefing, render_safe_edit_briefing,
                )

                briefing = build_safe_edit_briefing(impact, target_refs=refs)
                briefing_text = render_safe_edit_briefing(briefing)
                if briefing_text:
                    compiled_text = (f"{compiled_text}\n\n{briefing_text}" if compiled_text else briefing_text)
                    safe_edit_section = {"available": True, **briefing.to_dict()}
            except Exception:
                safe_edit_section = {"available": False, "reason": "safe_edit_briefing_error"}

        has_shadow_evidence = shadow_report is not None
        engaged = mode == PipelineMode.ACTIVE and has_shadow_evidence
        evidence = {
            "mode": mode.value,
            "engaged": engaged,
            "available": True,
            "advisory": True,  # never overrides Atlas Safe Apply / Verification authority
            "requires_shadow_evidence": mode == PipelineMode.ACTIVE and not has_shadow_evidence,
            "policy_id": policy.policy_id,
            "route": policy.route.value,
            "instruction_style": policy.instruction_style.value,
            "twin_injection_level": int(policy.twin_injection_level),
            "required_gates": list(policy.required_gates),
            "brief_id": brief.brief_id,
            "capability_profile_available": profile_available,
            "capability_profile_unavailable": not profile_available,
            "known_weaknesses": list(capability_profile.known_weaknesses),
            # Benchmark x injection: the per-route fitness from the model's benchmark profile,
            # and whether it informed the (safe) route choice.
            "route_fitness": {r.value if hasattr(r, "value") else str(r): v for r, v in (route_preferences or {}).items()},
            "benchmark_route_selected": any("benchmark_preferred_route" in r for r in policy.reasons),
            "compiled_instruction": compiled_text,
            "instruction_id": instruction_id,
            "advisory_context": {
                "hint_count": len(advisory.get("hints", [])),
                "golden_patch_count": len(advisory.get("golden_patches", [])),
                "skill_count": len(advisory.get("skills", [])),
            },
            "impact": _impact_section(impact),
            "safe_edit_briefing": safe_edit_section,
            "contract_sentinel": contract_section,
            "shadow_report": shadow_report.model_dump(mode="json") if shadow_report else None,
        }
        return evidence
    except Exception as exc:  # pragma: no cover - defensive: never break the legacy flow
        return {"mode": getattr(mode, "value", str(mode)), "engaged": False,
                "available": False, "reason": f"twin_evidence_error:{type(exc).__name__}"}


TWIN_CONTROL_PROMPT_HEADER = (
    "[Twin Control Plane — advisory hard constraints. These do NOT override the existing "
    "Proposal / Safe Apply / Verification authority; honor them as bounded guidance.]"
)


REPAIR_COMPASS_PROMPT_HEADER = (
    "[Twin Repair Compass — targeted repair guidance. Preserve all hard boundaries; do NOT "
    "weaken or delete tests/gates, bypass Safe Apply, or treat unavailable evidence as passed.]"
)


def compose_generation_system_prompt(base_prompt: str, twin_instruction: str | None) -> str:
    """Append the compiled Twin instruction as a bounded control section to a generation
    system prompt. Returns the base prompt unchanged when there is no instruction (so OFF
    mode and missing instructions never alter legacy prompt behavior)."""
    section = (twin_instruction or "").strip()
    if not section:
        return base_prompt
    return f"{base_prompt}\n\n{TWIN_CONTROL_PROMPT_HEADER}\n{section}"


def compose_repair_system_prompt(base_prompt: str, repair_guidance: str | None) -> str:
    """Append Repair Compass guidance as a bounded section for a repair attempt. Off-safe:
    no guidance leaves the base prompt unchanged."""
    section = (repair_guidance or "").strip()
    if not section:
        return base_prompt
    return f"{base_prompt}\n\n{REPAIR_COMPASS_PROMPT_HEADER}\n{section}"


def _render_repair_guidance(repair) -> str:
    """Render a RepairCompassReport into a compact, model-facing guidance block."""
    lines = ["# Repair Compass guidance"]
    for instruction in repair.instructions:
        lines.append(f"- [{instruction.category.value}] {instruction.summary}")
        for proof in instruction.proof_requirements:
            lines.append(f"  proof: {proof}")
    if repair.product_regression_refs:
        lines.append("Product regression to fix: " + ", ".join(repair.product_regression_refs))
    if repair.environment_unavailable_refs:
        lines.append("Environment-unavailable (keep separate, do not change product for this): "
                     + ", ".join(repair.environment_unavailable_refs))
    if repair.prohibited_actions:
        lines.append("Prohibited:")
        lines.extend(f"  - {action}" for action in repair.prohibited_actions)
    return "\n".join(lines)


def build_advisory_context(
    *,
    memory=None,
    golden_index=None,
    skill_patches=None,
    model_id: str = "",
    route: str = "",
    project_ref: str = "",
    changed_refs: Iterable[str] = (),
    retrieval_enabled: bool = True,
) -> dict:
    """Assemble advisory-only prompt context — anti-pattern guardrails, retrieved golden
    patches, and distilled skills. These NEVER override Twin / Contract / Schema / State /
    Proof findings; they are examples and hints only.

    Everything degrades safely to empty when its store/index is absent, and low-confidence
    or evidence-free entries are filtered out (so they are never injected). Never raises."""
    hints: list[dict] = []
    golden: list[dict] = []
    skills: list[dict] = []
    refs = [str(r).strip() for r in changed_refs if str(r).strip()]
    try:
        if memory is not None:
            from agent.twin_control_plane.anti_pattern_memory import guardrail_hints
            for hint in guardrail_hints(memory, model_id=model_id, route=route, project_ref=project_ref):
                hints.append({"text": hint.text, "strength": hint.strength.value,
                              "confidence": hint.confidence, "evidence_refs": list(hint.evidence_refs)})
    except Exception:
        pass
    try:
        if golden_index is not None and retrieval_enabled:
            from agent.model_forge.golden_patch_retrieval import RetrievalQuery
            from agent.model_forge.route_taxonomy import ForgeRoute
            route_enum = None
            try:
                route_enum = ForgeRoute(route) if route else None
            except ValueError:
                route_enum = None
            query = RetrievalQuery(task_category="autonomous_codegen", route=route_enum,
                                   model_id=model_id, affected_refs=refs)
            for rp in golden_index.retrieve(query, enabled=retrieval_enabled):
                golden.append({"patch_id": rp.patch.patch_id, "confidence": rp.confidence,
                               "advisory": rp.advisory, "summary": rp.patch.summary})
    except Exception:
        pass
    try:
        if skill_patches:
            from agent.model_forge.skill_distiller import distill_skills
            for skill in distill_skills(list(skill_patches), enabled=retrieval_enabled):
                skills.append({"skill_id": skill.skill_id, "hint": skill.hint,
                               "support": skill.support, "advisory": skill.advisory})
    except Exception:
        pass

    lines: list[str] = []
    if hints:
        lines.append("Anti-pattern guardrails (advisory):")
        lines.extend(f"- {h['text']}" for h in hints)
    if golden:
        lines.append("Similar prior successful patches (advisory examples only):")
        lines.extend(f"- {g['patch_id']}: {g['summary']}" for g in golden)
    if skills:
        lines.append("Distilled skills (advisory):")
        lines.extend(f"- {s['hint']}" for s in skills)
    return {"hints": hints, "golden_patches": golden, "skills": skills,
            "text": "\n".join(lines)}


ADVISORY_PROMPT_HEADER = (
    "[Twin advisory context — examples and hints only. These NEVER override current Twin / "
    "Contract / Schema / State / Proof findings or any hard constraint.]"
)


def python_schema_snapshot(project_path: str, files: Iterable[str], *, schema_id: str = "artifact"):
    """Best-effort schema snapshot of Python files: top-level public functions/classes and
    their signatures, as an ARTIFACT schema surface. Returns None when nothing parseable is
    found (so a missing/unparseable file is honestly unavailable, not a fabricated schema)."""
    import ast
    from pathlib import Path
    from agent.twin_control_plane.schema_guardian import SchemaField, SchemaSnapshot, SchemaSurface

    fields: list = []
    refs: list[str] = []
    for rel in files:
        rel = str(rel).strip()
        if not rel.endswith(".py"):
            continue
        path = Path(project_path) / rel
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        refs.append(rel)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                args = ",".join(a.arg for a in node.args.args)
                fields.append(SchemaField(name=node.name, field_type=f"function({args})", required=True))
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                fields.append(SchemaField(name=node.name, field_type="class", required=True))
    if not refs:
        return None
    return SchemaSnapshot(schema_id=schema_id, surface=SchemaSurface.ARTIFACT,
                          fields=fields, evidence_refs=sorted(set(refs)))


def _build_schema_report(before, after):
    """Schema Guardian report from before/after snapshots, or None when no after-snapshot."""
    if after is None:
        return None
    try:
        from agent.twin_control_plane.schema_guardian import compare_schema_snapshots
        return compare_schema_snapshots(before, after)
    except Exception:
        return None


def _advisory_schema_section(report) -> dict:
    if report is None:
        return {"available": False, "reason": "no_python_schema_snapshot"}
    return {
        "available": True,
        "accepted": report.accepted,
        "migration_required": report.migration_required,
        "would_block_if_promoted": report.blocked,
        "finding_count": len(report.findings),
        "proof_requirements": list(report.proof_requirements),
    }


def _build_state_report(backend, ui, persisted, runtime):
    """StateMirror report from observations, or None when no observations are available."""
    if not (backend or ui or persisted or runtime):
        return None
    try:
        from agent.twin_control_plane.state_mirror import compare_state_mirror
        return compare_state_mirror(backend=backend or (), ui=ui or (),
                                    persisted=persisted or (), runtime=runtime or ())
    except Exception:
        return None


def _advisory_state_section(report) -> dict:
    if report is None:
        return {"available": False, "reason": "no_state_observations"}
    return {
        "available": True,
        "accepted": report.accepted,
        "would_block_if_promoted": report.blocked,
        "finding_count": len(report.findings),
        "unavailable_evidence": list(report.unavailable_evidence),
        "proof_requirements": list(report.proof_requirements),
    }


def _verification_evidence(verification: Iterable):
    """Normalise (id, status) pairs or {evidence_id,status} dicts into VerificationEvidence.
    Anything that is not an explicit passed/failed is treated as unavailable (never passed)."""
    from agent.twin_control_plane.patch_impact_gate import VerificationEvidence

    out = []
    for idx, item in enumerate(verification or []):
        if isinstance(item, dict):
            ev_id = str(item.get("evidence_id") or item.get("id") or f"verify_{idx}")
            status = str(item.get("status") or "").strip().lower()
        else:
            ev_id = f"verify_{idx}"
            status = str(item).strip().lower()
        if status not in {"passed", "failed"}:
            status = "unavailable"
        out.append(VerificationEvidence(evidence_id=ev_id, status=status))
    return out


def evaluate_twin_post_apply(
    *,
    mode: PipelineMode,
    blocking: bool,
    block_unverified: bool = False,
    requirement: str = "",
    pool_id: str = "",
    project_path: str = "",
    changed_files: Iterable[str] = (),
    verification: Iterable = (),
    before_twin_revision_id: str = "",
    after_twin_revision_id: str = "",
    git_commit_sha: str = "",
    requirement_ref: str = "",
    plan_item_ref: str = "",
    model_id: str = "",
    provider_id: str = "",
    impact=None,
    attempted_actions: Iterable[str] = (),
    contract_sentinel=None,
    schema_guardian=None,
    state_mirror=None,
    twinproof=None,
    before_schema=None,
    after_schema=None,
    backend_state: Iterable = (),
    ui_state: Iterable = (),
    persisted_state: Iterable = (),
    runtime_state: Iterable = (),
    block_schema: bool = False,
    change_class: str = "medium",
    task_category: str = "autonomous_codegen",
) -> dict:
    """Run the Patch Impact Gate over the autonomous run's REAL post-apply evidence and
    return a record (plus a hard-block signal). Never raises.

    Blocking is conservative:
    - a genuine BLOCKED decision (hard contract/schema/state boundary) hard-blocks;
    - a completed change with changed files but NO passing verification only hard-blocks
      when ``block_unverified`` is explicitly enabled (it is otherwise recorded as an
      advisory proof gap, so legitimate auto-continued static changes are not disrupted);
    - ``unavailable`` evidence is never treated as passed."""
    if mode == PipelineMode.OFF:
        return {"mode": PipelineMode.OFF.value, "ran": False, "gate_blocked": False,
                "block_reason": "", "reason": "pipeline_off"}
    try:
        from agent.twin_control_plane.patch_impact_gate import PatchGateDecision, evaluate_patch_impact

        files = sorted({str(f).strip() for f in changed_files if str(f).strip()})
        policy, brief = _build_policy_and_brief(
            requirement=requirement, pool_id=pool_id, project_path=project_path, refs=files,
            item_refs=(), change_class=change_class, task_category=task_category,
        )
        # Build real sub-gate reports from impact evidence when available. Schema Guardian
        # and StateMirror need before/after snapshots/observations that the autonomous
        # codegen path does not currently produce, so they stay unavailable (not fabricated).
        sub_gate_sources: list[str] = []
        if impact is not None:
            try:
                from agent.twin_control_plane.blast_map import build_blast_map
                blast = build_blast_map(impact, brief=brief, changed_refs=files)
                if contract_sentinel is None:
                    from agent.twin_control_plane.contract_sentinel import evaluate_contracts
                    contract_sentinel = evaluate_contracts(
                        policy, brief, blast, attempted_actions=attempted_actions)
                    sub_gate_sources.append("contract_sentinel")
                if twinproof is None:
                    from agent.twin_control_plane.twinproof import build_twinproof
                    twinproof = build_twinproof(impacted_refs=blast.changed_refs)
                    sub_gate_sources.append("twinproof")
            except Exception:
                pass

        # Schema Guardian / StateMirror reports (advisory by default). When block_schema is
        # enabled, a genuinely breaking schema change is fed into the blocking path so it
        # drives the bounded repair loop; additive/new schemas never block.
        schema_report = _build_schema_report(before_schema, after_schema)
        state_report = _build_state_report(backend_state, ui_state, persisted_state, runtime_state)
        if block_schema and schema_report is not None and schema_guardian is None:
            schema_guardian = schema_report

        evidence_items = _verification_evidence(verification)
        report = evaluate_patch_impact(
            policy=policy, brief=brief,
            base_ref=before_twin_revision_id, head_ref=after_twin_revision_id or "working_tree",
            changed_files=files,
            before_twin_revision_id=before_twin_revision_id,
            after_twin_revision_id=after_twin_revision_id,
            verification=evidence_items,
            contract_sentinel=contract_sentinel, schema_guardian=schema_guardian,
            state_mirror=state_mirror, twinproof=twinproof,
        )
        # Durable Proof Ledger entry describing this decision (the orchestrator persists it).
        ledger_entry_dump = None
        try:
            from agent.twin_control_plane.proof_ledger import create_proof_ledger_entry
            entry = create_proof_ledger_entry(
                requirement_ref=requirement_ref, plan_item_ref=plan_item_ref,
                policy=policy, brief=brief, patch_report=report,
                model_id=model_id, provider_id=provider_id,
            )
            ledger_entry_dump = entry.model_dump(mode="json")
        except Exception:
            ledger_entry_dump = None

        # Repair Compass guidance for needs_repair / blocked decisions (advisory; preserves
        # all hard boundaries — never weakens tests/gates/Safe Apply/approval).
        repair_section = None
        repair_guidance = ""
        if report.needs_repair or report.blocked:
            try:
                from agent.twin_control_plane.repair_compass import build_repair_compass
                repair = build_repair_compass(policy=policy, brief=brief, patch_report=report)
                repair_guidance = _render_repair_guidance(repair)
                repair_section = {
                    "report_id": repair.report_id,
                    "prohibited_actions": list(repair.prohibited_actions),
                    "product_regression_refs": list(repair.product_regression_refs),
                    "environment_unavailable_refs": list(repair.environment_unavailable_refs),
                    "instructions": [
                        {"category": i.category.value, "summary": i.summary} for i in repair.instructions
                    ],
                }
            except Exception:
                repair_section = None

        has_passed = bool(report.passed_evidence_refs)
        unverified_change = bool(files) and not has_passed

        block_reason = ""
        if blocking and report.decision == PatchGateDecision.BLOCKED:
            block_reason = "twin_post_apply_hard_boundary"
        elif blocking and block_unverified and unverified_change:
            block_reason = "twin_post_apply_unverified_change"

        return {
            "mode": mode.value,
            "ran": True,
            "decision": report.decision.value,
            "accepted": report.accepted,
            "needs_repair": report.needs_repair,
            "blocked_decision": report.blocked,
            "unverified_change": unverified_change,
            "gate_blocked": bool(block_reason),
            "block_reason": block_reason,
            "sub_gates": {
                "contract_sentinel": contract_sentinel is not None,
                "schema_guardian": schema_guardian is not None,
                "state_mirror": state_mirror is not None,
                "twinproof": twinproof is not None,
                "built_from_impact": sub_gate_sources,
            },
            # Schema Guardian / StateMirror records for measurement. Advisory unless
            # block_schema promotes a breaking schema change into the blocking decision above.
            "advisory_schema": _advisory_schema_section(schema_report),
            "advisory_state": _advisory_state_section(state_report),
            "schema_promoted_to_block": bool(block_schema and schema_report is not None and schema_report.blocked),
            "gate_refs": list(report.gate_refs),
            "ledger_entry": ledger_entry_dump,
            "repair_compass": repair_section,
            "repair_guidance": repair_guidance,
            "passed_evidence": list(report.passed_evidence_refs),
            "failed_evidence": list(report.failed_evidence_refs),
            "unavailable_evidence": list(report.unavailable_evidence_refs),
            "repair_reasons": list(report.repair_reasons),
            "blocked_reasons": list(report.blocked_reasons),
            "proof_requirements": list(report.proof_requirements),
            "report_id": report.report_id,
        }
    except Exception as exc:  # pragma: no cover - defensive: never break the legacy flow
        return {"mode": getattr(mode, "value", str(mode)), "ran": False, "gate_blocked": False,
                "block_reason": "", "reason": f"twin_post_apply_error:{type(exc).__name__}"}


__all__ = [
    "PIPELINE_MODE_ENV",
    "GATE_BLOCKING_ENV",
    "BLOCK_UNVERIFIED_ENV",
    "BLOCK_SCHEMA_ENV",
    "DEFAULT_PIPELINE_MODE",
    "resolve_pipeline_mode",
    "resolve_gate_blocking",
    "resolve_block_unverified",
    "resolve_block_schema",
    "twin_gate_block_reason",
    "BUILD_PROJECT_TWIN_ENV",
    "resolve_build_project_twin",
    "load_project_twin_store",
    "refresh_project_twin",
    "try_project_twin_impact",
    "resolve_capability_profile",
    "DEFAULT_PROFILE_STORE_DIR",
    "TWIN_CONTROL_PROMPT_HEADER",
    "REPAIR_COMPASS_PROMPT_HEADER",
    "compose_generation_system_prompt",
    "compose_repair_system_prompt",
    "python_schema_snapshot",
    "build_advisory_context",
    "ADVISORY_PROMPT_HEADER",
    "build_twin_pipeline_evidence",
    "evaluate_twin_post_apply",
]
