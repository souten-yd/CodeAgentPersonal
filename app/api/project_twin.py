"""Project Digital Twin inspection API (PDT-13).

Read-only inspection over the twin store: health/revision, node + neighbors (lazy
expansion), bounded/paginated query, path trace, change impact and a bounded context
slice. The router exposes NO mutation or execution endpoint — it cannot authorize
execution, apply deltas, or change workflow/PlanPool/approval state. It is purely a
projection viewer.

Storage is resolved per data root; tests inject an in-memory store via
`app.state.project_twin_store`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from agent.project_twin.context_broker import TwinContextBroker
from agent.project_twin.contracts import (
    ImpactRequest,
    PathTraceRequest,
    TwinContextRequest,
    TwinQuery,
)
from agent.project_twin.store import SqliteProjectTwinStore, TwinStoreError
from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/project-twin", tags=["project-twin"])

# Bound the initial graph regardless of what a client requests.
_DEFAULT_QUERY_LIMIT = 100
_MAX_QUERY_LIMIT = 1000

_store_cache: dict[str, SqliteProjectTwinStore] = {}


def _get_store(request: Request) -> SqliteProjectTwinStore:
    injected = getattr(request.app.state, "project_twin_store", None)
    if injected is not None:
        return injected
    root = resolve_atlas_ca_data_root(request)
    db_path = str((root / "project_twin" / "twin.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    store = _store_cache.get(db_path)
    if store is None:
        store = SqliteProjectTwinStore(db_path)
        _store_cache[db_path] = store
    return store


@router.get("/health")
def health(project_id: str, request: Request):
    return _get_store(request).get_health(project_id).model_dump()


@router.get("/node")
def node(project_id: str, canonical_ref: str, request: Request, limit: int = 50):
    """A node plus its bounded 1-hop neighbours, for lazy UI expansion."""

    store = _get_store(request)
    snap = store.get_snapshot(project_id)
    by_id = {n.node_id: n for n in snap.nodes}
    target = next((n for n in snap.nodes if n.canonical_ref == canonical_ref), None)
    if target is None:
        raise HTTPException(status_code=404, detail={"error": "node_not_found", "canonical_ref": canonical_ref})
    neighbours = []
    bound = max(1, min(limit, _MAX_QUERY_LIMIT))
    for e in snap.edges:
        if len(neighbours) >= bound:
            break
        if e.source_node_id == target.node_id and e.target_node_id in by_id:
            neighbours.append({"direction": "out", "edge_type": e.edge_type, "node": by_id[e.target_node_id].model_dump()})
        elif e.target_node_id == target.node_id and e.source_node_id in by_id:
            neighbours.append({"direction": "in", "edge_type": e.edge_type, "node": by_id[e.source_node_id].model_dump()})
    return {"node": target.model_dump(), "neighbours": neighbours, "truncated": len(neighbours) >= bound}


@router.post("/query")
def query(payload: TwinQuery, request: Request):
    # Enforce a bounded initial graph even if a client over-requests.
    if payload.limit > _MAX_QUERY_LIMIT:
        payload = payload.model_copy(update={"limit": _MAX_QUERY_LIMIT})
    return _get_store(request).query(payload).model_dump()


@router.post("/path")
def path(payload: PathTraceRequest, request: Request):
    return _get_store(request).trace_path(payload).model_dump()


@router.post("/impact")
def impact(payload: ImpactRequest, request: Request):
    return _get_store(request).assess_impact(payload).model_dump()


@router.post("/context")
def context(payload: TwinContextRequest, request: Request):
    try:
        broker = TwinContextBroker(_get_store(request))
        return broker.build_slice(payload).model_dump()
    except TwinStoreError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.code}) from exc
