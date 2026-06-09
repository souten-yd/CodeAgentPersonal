"""Static projection service (PDT-3).

Bridges the pure static analyzer to the transactional Twin Store: it runs the analyzer,
computes which prior facts were *deleted* (present before, not re-emitted) so they are
explicitly invalidated rather than silently lost, links the delta to the current head for
stale protection, and applies it in one transaction.

This is the projection path (parser -> store via typed delta). It never mutates workflow
state, PlanPool authority or any Atlas safety boundary.
"""

from __future__ import annotations

from agent.project_twin.contracts import StaticAnalysisRequest, TwinRevision
from agent.project_twin.static_graph import StaticStructuralAnalyzer


class StaticProjectionService:
    def __init__(self, store, analyzer: StaticStructuralAnalyzer | None = None) -> None:
        self._store = store
        self._analyzer = analyzer or StaticStructuralAnalyzer()

    def refresh(
        self,
        *,
        project_id: str,
        project_path: str,
        changed_paths: list[str] | None = None,
        full_rebuild: bool = False,
    ) -> TwinRevision:
        head = self._store.get_health(project_id).twin_revision_id

        result = self._analyzer.analyze(
            StaticAnalysisRequest(
                project_id=project_id,
                project_path=project_path,
                changed_paths=changed_paths or [],
                full_rebuild=full_rebuild,
                base_revision_id=head,
            )
        )
        delta = result.delta

        # Determine the scope of files whose prior facts we are responsible for.
        scope: set[str] | None
        if full_rebuild or not changed_paths:
            scope = None  # everything currently in the twin is in scope
        else:
            scope = set(changed_paths)

        if head is not None:
            snapshot = self._store.get_snapshot(project_id)
            new_node_refs = {n.canonical_ref for n in delta.nodes}
            new_edge_ids = {e.edge_id for e in delta.edges}

            for node in snapshot.nodes:
                if scope is not None and node.source_ref not in scope:
                    continue
                if node.canonical_ref not in new_node_refs:
                    delta.invalidate_node_ids.append(node.node_id)
            for edge in snapshot.edges:
                if scope is not None and edge.source_ref not in scope:
                    continue
                if edge.edge_id not in new_edge_ids:
                    delta.invalidate_edge_ids.append(edge.edge_id)

        delta.base_revision_id = head
        return self._store.apply_delta(delta)
