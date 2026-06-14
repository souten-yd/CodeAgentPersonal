"""Impact and path analysis (PDT-11).

Provides explainable path and change-impact queries over the current twin graph:
- `trace_path`: directed path search between entities (e.g. UI control to persistence);
- `assess_impact`: structural + transitive (reverse-dependency) impact, affected
  requirements, behavior paths, side effects, recommended tests, historical risk and
  uncertainty, each with source references and explanation paths.

Reads the current snapshot through the store; never mutates. Confidence/status filters are
honoured so stale/low-confidence facts can be excluded. The `SqliteProjectTwinStore`
delegates its `trace_path`/`assess_impact` to this service.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.project_twin.contracts import (
    ImpactItem,
    ImpactRequest,
    ImpactResult,
    PathTraceRequest,
    PathTraceResult,
    TwinPath,
)
from agent.project_twin.static_graph import nid
from agent.project_twin.types import HISTORICAL_STATUSES

_SIDE_EFFECT_TYPES = {"side_effect", "api_call", "api_route"}
_TEST_TYPES = {"test"}
_REQUIREMENT_TYPES = {"requirement"}
_INCIDENT_TYPES = {"incident", "risk"}
# Pure structural containers reached by walking `defines`/`contains` edges in reverse (a function's
# module, its file, parent directories, the repo). They *contain* the changed symbol but are not
# behaviorally impacted by it, so they must not pollute the impact items shown to the planner.
_CONTAINER_NODE_TYPES = {"repository", "directory", "file", "module", "package"}
# Definitional forward edges along which a change propagates to the *implementing* entity, e.g. an
# `api_route` is implemented by its handler function via `handled_by`. Reverse reachability alone
# misses these because the implementer is the edge target, not a dependent; expanding seeds forward
# along them lets a route change surface its backend handler (and through it, callers/tests/effects).
_FORWARD_IMPACT_EDGES = {"handled_by"}
# Below this weakest-link confidence an impact was reached only through heuristic/inferred edges and
# must be reported with uncertainty rather than presented as a verified dependency.
_UNCERTAIN_PATH_CONFIDENCE = 0.7


def _pyname_alias_ref(ref: str | None) -> str | None:
    """The name-only alias for a resolved python symbol ref, or None.

    Name-based call edges (a caller that could not be statically resolved) target a shared
    ``pyname://<short>`` pseudo-node rather than the resolved ``py://path#qual`` node. Bridging the
    two during traversal lets heuristic name-only callers (e.g. a test calling an intermediate
    function) still be discovered, at the cost of name-collision imprecision that is surfaced as
    reduced path confidence.
    """
    if ref and ref.startswith("py://") and "#" in ref:
        short = ref.split("#", 1)[1].split(".")[-1]
        return f"pyname://{short}"
    return None


class GraphAnalysisService:
    def __init__(self, store) -> None:
        self._store = store

    def _load(self, project_id: str):
        snap = self._store.get_snapshot(project_id)
        nodes_by_id = {n.node_id: n for n in snap.nodes}
        id_to_ref = {n.node_id: n.canonical_ref for n in snap.nodes}
        fwd: dict[str, list] = {}
        rev: dict[str, list] = {}
        for e in snap.edges:
            fwd.setdefault(e.source_node_id, []).append(e)
            rev.setdefault(e.target_node_id, []).append(e)
        return nodes_by_id, id_to_ref, fwd, rev, snap.twin_revision_id

    # -- path tracing ---------------------------------------------------------

    def trace_path(self, request: PathTraceRequest) -> PathTraceResult:
        nodes_by_id, id_to_ref, fwd, rev, head = self._load(request.project_id)
        start = nid(request.source_ref)
        goal = nid(request.target_ref) if request.target_ref else None
        allowed = set(request.allowed_edge_types)
        statuses = set(request.statuses)
        results: list[TwinPath] = []

        def ok(edge) -> bool:
            if allowed and edge.edge_type not in allowed:
                return False
            if edge.confidence < request.min_confidence:
                return False
            if statuses and edge.status not in statuses:
                return False
            return True

        def dfs(cur, ref_path, edge_types, confidences, depth, visited):
            if len(results) >= request.max_paths:
                return
            if goal is not None and cur == goal and depth > 0:
                results.append(_make_path(ref_path, edge_types, confidences))
                return
            if depth >= request.max_depth:
                if goal is None and edge_types:
                    results.append(_make_path(ref_path, edge_types, confidences))
                return
            edges = [e for e in fwd.get(cur, []) if ok(e)]
            if not edges and goal is None and edge_types:
                results.append(_make_path(ref_path, edge_types, confidences))
                return
            for e in edges:
                tgt = e.target_node_id
                if tgt in visited:
                    continue
                dfs(tgt, ref_path + [id_to_ref.get(tgt, "?")], edge_types + [e.edge_type],
                    confidences + [e.confidence], depth + 1, visited | {tgt})

        dfs(start, [request.source_ref], [], [], 0, {start})
        return PathTraceResult(
            project_id=request.project_id, twin_revision_id=head, paths=results,
            truncated=len(results) >= request.max_paths,
            diagnostics=[] if results else [{"code": "no_path_found", "source": request.source_ref, "target": request.target_ref}],
            generated_at=datetime.now(timezone.utc),
        )

    # -- impact ---------------------------------------------------------------

    def assess_impact(self, request: ImpactRequest) -> ImpactResult:
        nodes_by_id, id_to_ref, fwd, rev, head = self._load(request.project_id)

        seeds: set[str] = set()
        for ref in request.changed_refs:
            seeds.add(nid(ref))
            if ref.startswith("py://") and "#" in ref:
                short = ref.split("#", 1)[1].split(".")[-1]
                seeds.add(nid(f"pyname://{short}"))

        # Forward-expand seeds along definitional edges (e.g. api_route -> handler via `handled_by`)
        # so changing a route/definition surfaces the implementing symbol; through it we then also
        # reach that symbol's callers, tests, and side effects below.
        impl_ids: set[str] = set()
        ix_stack = list(seeds)
        ix_seen = set(seeds)
        while ix_stack:
            cur = ix_stack.pop()
            for e in fwd.get(cur, []):
                if e.edge_type not in _FORWARD_IMPACT_EDGES or e.confidence < request.min_confidence:
                    continue
                tgt = e.target_node_id
                if tgt not in ix_seen:
                    ix_seen.add(tgt)
                    impl_ids.add(tgt)
                    ix_stack.append(tgt)
        seeds |= impl_ids

        def alias_id(node_id: str) -> str | None:
            alias_ref = _pyname_alias_ref(id_to_ref.get(node_id))
            if alias_ref is None:
                return None
            aid = nid(alias_ref)
            return aid if aid != node_id else None

        # reverse reachability: who depends on the changed entities. `path_conf` tracks the weakest
        # edge confidence along the discovered path so an impact reached only via heuristic/inferred
        # links is reported with honest uncertainty instead of false certainty. A resolved symbol is
        # bridged to its name-only alias (same depth/confidence) so name-based callers are found.
        depth_of: dict[str, int] = {}
        visited = set(seeds)
        path_conf: dict[str, float] = {s: 1.0 for s in seeds}
        frontier: list[tuple[str, int]] = []
        for s in list(seeds):
            frontier.append((s, 0))
            alias = alias_id(s)
            if alias is not None and alias not in visited:
                visited.add(alias)
                path_conf[alias] = 1.0
                frontier.append((alias, 0))
        while frontier:
            cur, depth = frontier.pop()
            if depth >= request.max_depth:
                continue
            for e in rev.get(cur, []):
                if e.confidence < request.min_confidence:
                    continue
                src = e.source_node_id
                conf = min(path_conf.get(cur, 1.0), e.confidence)
                if src not in visited:
                    visited.add(src)
                    depth_of[src] = depth + 1
                    path_conf[src] = conf
                    frontier.append((src, depth + 1))
                    alias = alias_id(src)
                    if alias is not None and alias not in visited:
                        visited.add(alias)
                        depth_of[alias] = depth + 1
                        path_conf[alias] = conf
                        frontier.append((alias, depth + 1))
                elif conf > path_conf.get(src, 0.0):
                    path_conf[src] = conf

        # Resolve a name-only alias node back to the concrete symbol(s) it could refer to, so a
        # name-based call (caller -> pyname://x) can reach the real symbol's side effects downstream.
        alias_to_ids: dict[str, list[str]] = {}
        for node_id, ref in id_to_ref.items():
            alias_ref = _pyname_alias_ref(ref)
            if alias_ref is not None:
                alias_to_ids.setdefault(nid(alias_ref), []).append(node_id)

        # forward reachability: side effects produced by the changed entities
        side_effect_ids: set[str] = set()
        fseen = set(seeds)
        fstack = list(seeds)
        while fstack:
            cur = fstack.pop()
            for real_id in alias_to_ids.get(cur, []):
                if real_id not in fseen:
                    fseen.add(real_id)
                    fstack.append(real_id)
            for e in fwd.get(cur, []):
                if e.confidence < request.min_confidence:
                    continue
                tgt = e.target_node_id
                node = nodes_by_id.get(tgt)
                if node and node.node_type in _SIDE_EFFECT_TYPES:
                    side_effect_ids.add(tgt)
                if tgt not in fseen:
                    fseen.add(tgt)
                    fstack.append(tgt)

        def item(node, reason) -> ImpactItem:
            return ImpactItem(
                canonical_ref=node.canonical_ref, item_type=node.node_type, status=node.status,
                confidence=node.confidence, source_refs=[node.source_ref], evidence_refs=node.evidence_refs,
                reason=reason,
            )

        # Implementing symbols reached by forward-expansion are direct impacts of the change.
        reason_of: dict[str, str] = {i: "implements_changed_entity" for i in impl_ids}
        for nodeid in impl_ids:
            depth_of.setdefault(nodeid, 1)

        direct, transitive, requirements, tests, incidents, uncertainty = [], [], [], [], [], []
        for nodeid, depth in depth_of.items():
            node = nodes_by_id.get(nodeid)
            if node is None:
                continue
            if node.node_type in _CONTAINER_NODE_TYPES:
                # Structural container reached via containment edges — not a behavioral impact.
                continue
            reason = reason_of.get(nodeid, f"reverse_dependency_depth_{depth}")
            (direct if depth <= 1 else transitive).append(item(node, reason))
            if node.node_type in _REQUIREMENT_TYPES:
                requirements.append(item(node, "affected_requirement"))
            if node.node_type in _TEST_TYPES:
                tests.append(item(node, "recommended_test"))
            if node.node_type in _INCIDENT_TYPES:
                incidents.append(item(node, "historical_risk"))
            link_conf = path_conf.get(nodeid, node.confidence)
            if node.status in HISTORICAL_STATUSES or node.confidence < 0.5 or link_conf < _UNCERTAIN_PATH_CONFIDENCE:
                uncertainty.append({
                    "canonical_ref": node.canonical_ref, "status": node.status,
                    "confidence": node.confidence, "path_confidence": round(link_conf, 3),
                })

        side_effects = [item(nodes_by_id[i], "side_effect_of_change") for i in side_effect_ids if i in nodes_by_id]

        # behavior paths and explanation: trace from the first changed ref
        behavior_paths: list[TwinPath] = []
        explanation: list[TwinPath] = []
        if request.changed_refs:
            tr = self.trace_path(PathTraceRequest(
                project_id=request.project_id, source_ref=request.changed_refs[0],
                min_confidence=request.min_confidence, max_depth=request.max_depth, max_paths=5,
            ))
            explanation = tr.paths
            behavior_paths = [p for p in tr.paths if any(t in {"triggers", "invokes", "performs_side_effect", "reaches_route"} for t in p.edge_types)]

        return ImpactResult(
            project_id=request.project_id, twin_revision_id=head,
            direct_impacts=direct, transitive_impacts=transitive, affected_requirements=requirements,
            behavior_paths=behavior_paths, side_effects=side_effects, recommended_tests=tests,
            past_incidents=incidents if request.include_historical_risks else [],
            uncertainty=uncertainty, explanation_paths=explanation,
            diagnostics=[] if (direct or transitive or side_effects) else [{"code": "no_impact_found"}],
            generated_at=datetime.now(timezone.utc),
        )


def _make_path(ref_path: list[str], edge_types: list[str], confidences: list[float]) -> TwinPath:
    inferred = False  # confidence proxy; callers set heuristic edges with lower confidence
    min_conf = min(confidences) if confidences else 1.0
    return TwinPath(
        node_refs=ref_path, edge_types=edge_types, min_confidence=min_conf,
        contains_inferred=min_conf < 0.8,
        explanation=" -> ".join(f"{ref_path[i]} =[{edge_types[i]}]=> {ref_path[i + 1]}" for i in range(len(edge_types))),
    )
