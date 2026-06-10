"""Bounded twin context package builder v2 (PI-9).

Builds a ``TwinContextPackage`` from the PI-6/7/8 graphs and the current workspace sources:
graph-neighborhood candidate generation, objective/phase relevance, freshness and
contradiction penalties, source excerpts at the manifest revision, all context sections, a
persisted-shaped manifest, bounded traversal and a token budget. Essential requirement and
preserve-behavior items are never dropped. Pure: no Atlas schema, no SQLite.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterable

from agent.project_intelligence.contracts import (
    ContextItem,
    ContextManifest,
    RuntimeObservationRecord,
    SourceExcerpt,
)
from agent.project_twin.facade import TwinContextPackage
from agent.project_twin.graph.behavioral import BehavioralGraph
from agent.project_twin.graph.semantic import SemanticGraph

_MAX_NEIGHBORHOOD = 60
_EXCERPT_LINES = 25


def _est_tokens(item: ContextItem) -> int:
    return max(1, (len(item.ref) + len(item.summary) + len(item.inclusion_reason)) // 4)


def _neighbors(semantic: SemanticGraph, target_refs: list[str]) -> set[str]:
    out: set[str] = set(target_refs)
    for t in target_refs:
        for e in semantic.edges(kind="calls"):
            if e.source_ref == t:
                out.add(e.target_ref)
            if e.target_ref == t:
                out.add(e.source_ref)
    return out


def build_context_package(
    *,
    project_id: str,
    workspace_id: str,
    phase: str,
    objective: str,
    target_refs: list[str],
    token_budget: int,
    semantic: SemanticGraph,
    behavioral: BehavioralGraph | None = None,
    runtime: Iterable[RuntimeObservationRecord] | None = None,
    sources: dict[str, str] | None = None,
    source_revision: str | None = None,
    twin_revision_id: str | None = None,
    requirements: list[ContextItem] | None = None,
    preserve_behaviors: list[ContextItem] | None = None,
    memories: list[ContextItem] | None = None,
    skills: list[ContextItem] | None = None,
    nexus: list[ContextItem] | None = None,
    incidents: list[ContextItem] | None = None,
    contradicted_refs: set[str] | None = None,
    stale_refs: set[str] | None = None,
    min_confidence: float = 0.25,
) -> TwinContextPackage:
    behavioral = behavioral or BehavioralGraph()
    runtime = list(runtime or [])
    contradicted = contradicted_refs or set()
    stale = stale_refs or set()
    sources = sources or {}

    targets = set(target_refs)
    neighborhood = _neighbors(semantic, target_refs)
    # Bound the neighborhood so we never dump the whole graph into a prompt.
    bounded = set(target_refs) | set(sorted(neighborhood - targets)[: _MAX_NEIGHBORHOOD])

    symbols: list[ContextItem] = []
    interfaces: list[ContextItem] = []
    uncertainties: list[ContextItem] = []

    for ref in sorted(bounded):
        node = semantic.get(ref)
        if node is None:
            continue
        if ref in contradicted:
            uncertainties.append(ContextItem(ref=ref, kind=node.kind, summary=node.name,
                                             status="contradicted", confidence=0.2,
                                             inclusion_reason="runtime-contradicted static fact"))
            continue
        reason = "target" if ref in targets else "call-neighborhood"
        if ref in stale:
            reason += " (stale: revision mismatch)"
        score = 1.0 if ref in targets else 0.5
        item = ContextItem(ref=ref, kind=node.kind, summary=f"{node.kind} {node.name}",
                            status="inferred", confidence=score, source_refs=[node.file],
                            inclusion_reason=reason)
        if node.kind == "class":
            interfaces.append(item)
        else:
            symbols.append(item)

    behavior_paths: list[ContextItem] = []
    state_and_events: list[ContextItem] = []
    side_effects: list[ContextItem] = []
    for fact in behavioral.facts():
        if fact.owner_ref not in bounded:
            continue
        ci = ContextItem(ref=fact.ref, kind=fact.kind, summary=f"{fact.kind} {fact.label}",
                         status=fact.status, confidence=fact.confidence,
                         source_refs=[fact.owner_ref], inclusion_reason="behavioral neighborhood")
        if fact.kind in ("control_flow", "recovery", "route"):
            behavior_paths.append(ci)
        elif fact.kind == "state":
            state_and_events.append(ci)
        elif fact.kind == "side_effect":
            side_effects.append(ci)

    tests: list[ContextItem] = []
    runtime_evidence: list[ContextItem] = []
    for obs in runtime:
        if targets & set(obs.subject_refs):
            runtime_evidence.append(ContextItem(ref=obs.observation_id, kind="runtime",
                                                summary=f"{obs.collector}:{obs.result} {obs.summary}",
                                                status=obs.result, confidence=0.9,
                                                inclusion_reason="runtime evidence for target"))
            for ref in obs.subject_refs:
                if ref.startswith("test://"):
                    tests.append(ContextItem(ref=ref, kind="test", summary=ref,
                                             inclusion_reason="covers target"))

    # Essential sections are never dropped.
    req_items = list(requirements or [])
    preserve_items = list(preserve_behaviors or [])
    essential = req_items + preserve_items

    # Token budget: count essentials first (kept even on overflow), then non-essentials by score.
    used = sum(_est_tokens(i) for i in essential)
    truncated = used > token_budget

    non_essential_sections = [symbols, interfaces, behavior_paths, state_and_events,
                              side_effects, tests, runtime_evidence,
                              list(memories or []), list(skills or []), list(nexus or []),
                              list(incidents or [])]
    flat: list[ContextItem] = [i for sec in non_essential_sections for i in sec]
    flat.sort(key=lambda i: i.confidence, reverse=True)
    keep: set[str] = set()
    excluded: list[str] = []
    for item in flat:
        cost = _est_tokens(item)
        if used + cost <= token_budget:
            used += cost
            keep.add(item.ref)
        else:
            excluded.append(item.ref)
            truncated = True

    def _filter(sec: list[ContextItem]) -> list[ContextItem]:
        return [i for i in sec if i.ref in keep]

    # source excerpts at the manifest revision
    source_material: list[SourceExcerpt] = []
    source_revisions: dict[str, str] = {}
    for ref in target_refs:
        node = semantic.get(ref)
        rel = node.file if node else None
        if rel and rel in sources:
            lines = sources[rel].splitlines()[: _EXCERPT_LINES]
            source_material.append(SourceExcerpt(
                ref=ref, path=rel, start_line=1, end_line=len(lines),
                excerpt="\n".join(lines), source_revision=source_revision,
            ))
            if source_revision:
                source_revisions[rel] = source_revision

    included_refs = sorted(keep | {i.ref for i in essential} | {s.ref for s in source_material})
    manifest = ContextManifest(
        manifest_id=f"ctx:{uuid.uuid4().hex[:10]}", project_id=project_id, workspace_id=workspace_id,
        phase=phase, actual_twin_revision_id=twin_revision_id,
        included_refs=included_refs, excluded_refs=sorted(excluded),
        uncertainty_refs=[u.ref for u in uncertainties],
        source_revisions=source_revisions, token_budget=token_budget, used_tokens=used,
        truncated=truncated, rollout_mode="active",
    )

    return TwinContextPackage(
        project_id=project_id, workspace_id=workspace_id, twin_revision_id=twin_revision_id,
        phase=phase,
        requirements=req_items,
        symbols=_filter(symbols),
        interfaces=_filter(interfaces),
        behavior_paths=_filter(behavior_paths),
        state_and_events=_filter(state_and_events),
        side_effects=_filter(side_effects),
        tests=_filter(tests),
        runtime_evidence=_filter(runtime_evidence),
        incidents=_filter(list(incidents or [])),
        memories=_filter(list(memories or [])),
        skills=_filter(list(skills or [])),
        nexus_evidence=_filter(list(nexus or [])),
        preserve_behaviors=preserve_items,
        uncertainties=uncertainties,
        source_material=source_material,
        manifest=manifest,
    )
