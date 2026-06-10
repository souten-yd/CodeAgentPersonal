"""Impact, path, and test-selection analysis v2 (PI-9).

Operates over the PI-6 semantic graph, the PI-7 behavioral graph, and PI-8 runtime
observations. Distinguishes resolved from candidate callers, recommends tests from real
coverage, and reports truthful "no path" results. Pure: no Atlas schema, no SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from agent.project_intelligence.contracts import RuntimeObservationRecord
from agent.project_twin.graph.behavioral import BehavioralGraph
from agent.project_twin.graph.semantic import SemanticGraph


@dataclass
class ImpactReport:
    target_ref: str
    direct_callers: list[str] = field(default_factory=list)
    transitive_callers: list[str] = field(default_factory=list)
    candidate_callers: list[str] = field(default_factory=list)
    affected_behaviors: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    recommended_tests: list[str] = field(default_factory=list)
    confidence: float = 0.0
    explanation: list[str] = field(default_factory=list)


def _reverse_call_index(semantic: SemanticGraph) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    resolved: dict[str, set[str]] = {}
    candidate: dict[str, set[str]] = {}
    for e in semantic.edges(kind="calls"):
        bucket = resolved if e.resolved else candidate
        bucket.setdefault(e.target_ref, set()).add(e.source_ref)
    return resolved, candidate


def assess_impact(
    semantic: SemanticGraph,
    behavioral: BehavioralGraph,
    target_ref: str,
    *,
    runtime: Iterable[RuntimeObservationRecord] | None = None,
    max_depth: int = 5,
) -> ImpactReport:
    """Reverse-dependency impact of changing ``target_ref``."""
    resolved_idx, candidate_idx = _reverse_call_index(semantic)
    report = ImpactReport(target_ref=target_ref)

    direct = sorted(resolved_idx.get(target_ref, set()))
    report.direct_callers = direct
    report.candidate_callers = sorted(candidate_idx.get(target_ref, set()))

    # transitive resolved callers (BFS)
    seen: set[str] = set(direct)
    frontier = list(direct)
    depth = 0
    while frontier and depth < max_depth:
        nxt: list[str] = []
        for ref in frontier:
            for caller in sorted(resolved_idx.get(ref, set())):
                if caller not in seen:
                    seen.add(caller)
                    nxt.append(caller)
        frontier = nxt
        depth += 1
    report.transitive_callers = sorted(seen - set(direct))

    # affected behaviors + side effects owned by the target and its callers
    owners = {target_ref, *direct, *report.transitive_callers}
    for rel in behavioral.relations(kind="performs_side_effect"):
        if rel.source_ref in owners:
            report.side_effects.append(rel.target_ref)
    for fact in behavioral.facts():
        if fact.owner_ref in owners and fact.kind in ("control_flow", "recovery", "state"):
            report.affected_behaviors.append(fact.ref)
    report.side_effects = sorted(set(report.side_effects))
    report.affected_behaviors = sorted(set(report.affected_behaviors))

    report.recommended_tests = select_tests(semantic, runtime or [], [target_ref])
    # confidence: high when callers resolved, lower when only candidates exist
    if direct or not report.candidate_callers:
        report.confidence = 0.9 if direct else 0.5
    else:
        report.confidence = 0.4
    report.explanation = [
        f"{len(direct)} direct + {len(report.transitive_callers)} transitive resolved callers",
        f"{len(report.candidate_callers)} candidate (may-call) callers",
        f"{len(report.recommended_tests)} recommended tests from coverage",
    ]
    return report


@dataclass
class PathResult:
    source_ref: str
    target_ref: str
    found: bool
    path: list[str] = field(default_factory=list)
    inferred: bool = False
    diagnostics: list[str] = field(default_factory=list)


def trace_path(
    semantic: SemanticGraph,
    source_ref: str,
    target_ref: str,
    *,
    max_depth: int = 8,
    kinds: tuple[str, ...] = ("calls", "imports", "inherits", "defines", "contains"),
) -> PathResult:
    """Directed reachability from source to target over selected edge kinds."""
    adjacency: dict[str, list[tuple[str, bool]]] = {}
    for kind in kinds:
        for e in semantic.edges(kind=kind):
            adjacency.setdefault(e.source_ref, []).append((e.target_ref, e.resolved))
    # BFS keeping the first path found.
    queue: list[tuple[str, list[str], bool]] = [(source_ref, [source_ref], False)]
    visited = {source_ref}
    while queue:
        ref, path, inferred = queue.pop(0)
        if ref == target_ref:
            return PathResult(source_ref, target_ref, True, path, inferred)
        if len(path) > max_depth:
            continue
        for nxt, resolved in adjacency.get(ref, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, path + [nxt], inferred or not resolved))
    return PathResult(source_ref, target_ref, False, [], False,
                      diagnostics=["no path found"])


def select_tests(
    semantic: SemanticGraph,
    runtime: Iterable[RuntimeObservationRecord],
    target_refs: list[str],
) -> list[str]:
    """Recommend tests that cover the targets (from real runtime coverage subjects)."""
    targets = set(target_refs)
    recommended: list[str] = []
    for obs in runtime:
        if obs.observation_type != "test_execution":
            continue
        subjects = set(obs.subject_refs)
        if subjects & targets:
            for ref in obs.subject_refs:
                if ref.startswith("test://") and ref not in recommended:
                    recommended.append(ref)
    return sorted(recommended)
