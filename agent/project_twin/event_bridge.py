"""Canonical event bridge and delivery-trace expansion (PI-5).

Connects already-committed Atlas canonical operations to Twin projection using
journal/outbox semantics (ADR-PI-011):

- canonical operations commit first, then emit a ``ProjectEventEnvelope`` to this bridge;
- the bridge projects events into a delivery-trace model at least once and idempotently;
- a projection failure marks the twin degraded and queues a retry — it never rolls back a
  successful Safe Apply (the bridge has no canonical-write capability at all);
- correlation/run/pool/item ids are preserved; missing links produce diagnostics, never
  fabricated edges; failure and revision history remain queryable.

Core v1 ``intent_trace.py`` (PDT-4) is kept unchanged; this module is the v2 expansion that
consumes the full event catalog. It depends only on the contract kernel, the twin facade
event types, and an injected job store (jobs.JobStore) — never on a canonical Atlas store.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from agent.project_intelligence.contracts import (
    IntelligenceDiagnostic,
    IntelligenceErrorCode,
    _Frozen,
)
from agent.project_twin.facade import PROJECT_EVENT_TYPES, ProjectEventEnvelope
from agent.project_twin.jobs import JobStore


# --- Delivery-trace fact model -----------------------------------------------


class DeliveryNode(_Frozen):
    ref: str
    kind: str
    label: str = ""
    source_refs: list[str] = Field(default_factory=list)
    source_revision: str | None = None


class DeliveryEdge(_Frozen):
    source_ref: str
    target_ref: str
    edge_type: str
    inferred: bool = False
    source_refs: list[str] = Field(default_factory=list)


class DeliveryIngestResult(_Frozen):
    project_id: str
    event_id: str
    accepted: bool
    duplicate: bool = False
    added_nodes: int = 0
    added_edges: int = 0
    degraded: bool = False
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


class DeliveryTrace(_Frozen):
    project_id: str
    root_ref: str
    nodes: list[DeliveryNode] = Field(default_factory=list)
    edges: list[DeliveryEdge] = Field(default_factory=list)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


def _diag(code: IntelligenceErrorCode, message: str, refs: list[str] | None = None) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, refs=refs or [], severity="info")


# --- Event -> delivery facts mapping -----------------------------------------


def _first(*values: Any) -> Any:
    for v in values:
        if v:
            return v
    return None


def _facts_for_event(
    env: ProjectEventEnvelope,
) -> tuple[list[DeliveryNode], list[tuple[str, str, str, bool]], list[IntelligenceDiagnostic]]:
    """Return (nodes, edges-as-tuples, diagnostics) for one event. No fabricated links."""
    p = env.payload
    rev = env.source_revision
    nodes: list[DeliveryNode] = []
    edges: list[tuple[str, str, str, bool]] = []  # (source, target, type, inferred)
    diags: list[IntelligenceDiagnostic] = []

    et = env.event_type
    if et == "conversation.message.completed":
        mref = _first(p.get("message_ref"), env.source_ref)
        if mref:
            nodes.append(DeliveryNode(ref=f"message://{mref}", kind="message", source_revision=rev))
    elif et in ("requirement.confirmed", "requirement.revised"):
        rid = p.get("requirement_id")
        if not rid:
            diags.append(_diag(IntelligenceErrorCode.REVISION_NOT_FOUND, "requirement event without requirement_id"))
        else:
            nodes.append(DeliveryNode(ref=f"requirement://{rid}", kind="requirement",
                                      label=str(p.get("text", "")), source_revision=rev))
            msg = _first(p.get("source_message_ref"), env.source_ref)
            if msg:
                edges.append((f"message://{msg}", f"requirement://{rid}", "originates", False))
    elif et in ("plan.created", "plan.revised"):
        plan_id = _first(p.get("plan_id"), env.plan_pool_id)
        if plan_id:
            nodes.append(DeliveryNode(ref=f"plan://{plan_id}", kind="plan", source_revision=rev))
    elif et in ("plan_item.started", "plan_item.completed", "plan_item.failed"):
        item = _first(env.plan_item_id, p.get("plan_item_id"))
        if not item:
            diags.append(_diag(IntelligenceErrorCode.REVISION_NOT_FOUND, "plan_item event without plan_item_id"))
        else:
            nodes.append(DeliveryNode(ref=f"planitem://{item}", kind="plan_item",
                                      label=et.split(".")[-1], source_revision=rev))
            plan_id = _first(p.get("plan_id"), env.plan_pool_id)
            if plan_id:
                edges.append((f"plan://{plan_id}", f"planitem://{item}", "contains", False))
            for rid in p.get("requirement_ids", []) or []:
                edges.append((f"requirement://{rid}", f"planitem://{item}", "implemented_by", False))
    elif et in ("proposal.generated", "proposal.approved", "proposal.rejected"):
        pid = p.get("proposal_id")
        if not pid:
            diags.append(_diag(IntelligenceErrorCode.REVISION_NOT_FOUND, "proposal event without proposal_id"))
        else:
            nodes.append(DeliveryNode(ref=f"proposal://{pid}", kind="proposal",
                                      label=et.split(".")[-1], source_revision=rev))
            item = _first(env.plan_item_id, p.get("plan_item_id"))
            if item:
                edges.append((f"planitem://{item}", f"proposal://{pid}", "proposes", False))
            else:
                diags.append(_diag(IntelligenceErrorCode.REVISION_NOT_FOUND,
                                   "proposal not linked to a plan item", [f"proposal://{pid}"]))
    elif et == "safe_apply.completed":
        item = _first(env.plan_item_id, p.get("plan_item_id"))
        pid = p.get("proposal_id")
        applied = p.get("applied_refs", []) or []
        if not applied:
            diags.append(_diag(IntelligenceErrorCode.REVISION_NOT_FOUND, "safe_apply with no applied refs"))
        for ref in applied:
            nodes.append(DeliveryNode(ref=ref, kind="applied_ref", source_revision=p.get("new_source_revision") or rev))
            if pid:
                edges.append((f"proposal://{pid}", ref, "applies_to", False))
            elif item:
                edges.append((f"planitem://{item}", ref, "applies_to", False))
    elif et in ("verification.started", "verification.completed"):
        vid = p.get("verification_id")
        if not vid:
            diags.append(_diag(IntelligenceErrorCode.REVISION_NOT_FOUND, "verification event without verification_id"))
        else:
            nodes.append(DeliveryNode(ref=f"verification://{vid}", kind="verification",
                                      label=str(p.get("result", "")), source_revision=rev))
            item = _first(env.plan_item_id, p.get("plan_item_id"))
            if item:
                edges.append((f"planitem://{item}", f"verification://{vid}", "verified_by", False))
            for ev in p.get("evidence_refs", []) or []:
                nodes.append(DeliveryNode(ref=ev, kind="evidence", source_revision=rev))
                edges.append((f"verification://{vid}", ev, "produced", False))
    elif et == "runtime_observation.recorded":
        oid = p.get("observation_id")
        if oid:
            nodes.append(DeliveryNode(ref=f"observation://{oid}", kind="runtime_observation",
                                      label=str(p.get("result", "")), source_revision=rev))
    # memory/skill/nexus events are projected by their own adapters (Core v1); ignored here.
    return nodes, edges, diags


# --- Projector + bridge ------------------------------------------------------


class DeliveryTraceProjector:
    """Idempotent, project-isolated in-memory delivery-trace projection.

    Holds no canonical store. Re-ingesting an event with the same idempotency key adds no
    new facts (at-least-once delivery is safe). Facts are keyed by ref so duplicate replay
    does not duplicate nodes or edges.
    """

    def __init__(self) -> None:
        # project_id -> {"nodes": {ref: DeliveryNode}, "edges": {key: DeliveryEdge},
        #                "seen": set(idempotency_key), "diags": [..]}
        self._p: dict[str, dict[str, Any]] = {}

    def _proj(self, project_id: str) -> dict[str, Any]:
        return self._p.setdefault(
            project_id, {"nodes": {}, "edges": {}, "seen": set(), "diags": []}
        )

    def ingest(self, env: ProjectEventEnvelope) -> DeliveryIngestResult:
        proj = self._proj(env.project_id)
        if env.event_type not in PROJECT_EVENT_TYPES:
            return DeliveryIngestResult(
                project_id=env.project_id, event_id=env.event_id, accepted=False,
                diagnostics=[_diag(IntelligenceErrorCode.INVALID_CONTRACT_VERSION,
                                   f"unknown event type {env.event_type!r}")],
            )
        key = env.idempotency_key or env.event_id
        if key in proj["seen"]:
            return DeliveryIngestResult(project_id=env.project_id, event_id=env.event_id,
                                        accepted=True, duplicate=True)

        nodes, edge_tuples, diags = _facts_for_event(env)
        added_nodes = 0
        added_edges = 0
        for node in nodes:
            if node.ref not in proj["nodes"]:
                proj["nodes"][node.ref] = node
                added_nodes += 1
        for src, tgt, etype, inferred in edge_tuples:
            ekey = (src, tgt, etype)
            if ekey not in proj["edges"]:
                proj["edges"][ekey] = DeliveryEdge(
                    source_ref=src, target_ref=tgt, edge_type=etype, inferred=inferred,
                    source_refs=[env.source_ref] if env.source_ref else [],
                )
                added_edges += 1
        proj["seen"].add(key)
        proj["diags"].extend(diags)
        return DeliveryIngestResult(
            project_id=env.project_id, event_id=env.event_id, accepted=True,
            added_nodes=added_nodes, added_edges=added_edges, diagnostics=diags,
        )

    def get_trace(self, project_id: str, root_ref: str, *, max_depth: int = 6) -> DeliveryTrace:
        proj = self._p.get(project_id)
        if not proj:
            return DeliveryTrace(project_id=project_id, root_ref=root_ref)
        edges_by_src: dict[str, list[DeliveryEdge]] = {}
        edges_by_tgt: dict[str, list[DeliveryEdge]] = {}
        for e in proj["edges"].values():
            edges_by_src.setdefault(e.source_ref, []).append(e)
            edges_by_tgt.setdefault(e.target_ref, []).append(e)
        visited: set[str] = set()
        order: list[str] = []
        edges_out: list[DeliveryEdge] = []
        frontier = [(root_ref, 0)]
        while frontier:
            ref, depth = frontier.pop(0)
            if ref in visited or depth > max_depth:
                continue
            visited.add(ref)
            order.append(ref)
            for e in edges_by_src.get(ref, []) + edges_by_tgt.get(ref, []):
                edges_out.append(e)
                nxt = e.target_ref if e.source_ref == ref else e.source_ref
                frontier.append((nxt, depth + 1))
        nodes = [proj["nodes"][r] for r in order if r in proj["nodes"]]
        # de-duplicate edges preserving order
        seen_e: set[tuple[str, str, str]] = set()
        uniq_edges: list[DeliveryEdge] = []
        for e in edges_out:
            k = (e.source_ref, e.target_ref, e.edge_type)
            if k not in seen_e:
                seen_e.add(k)
                uniq_edges.append(e)
        return DeliveryTrace(project_id=project_id, root_ref=root_ref, nodes=nodes,
                             edges=uniq_edges, diagnostics=list(proj["diags"]))

    def diagnostics(self, project_id: str) -> list[IntelligenceDiagnostic]:
        proj = self._p.get(project_id)
        return list(proj["diags"]) if proj else []


class CanonicalEventBridge:
    """Outbox-style bridge: receive committed canonical events, project idempotently.

    On projection failure it marks the project degraded and (when a JobStore is injected)
    enqueues a retry job — it never undoes a successful canonical operation.
    """

    def __init__(self, projector: DeliveryTraceProjector | None = None, *, job_store: JobStore | None = None) -> None:
        self._projector = projector or DeliveryTraceProjector()
        self._jobs = job_store
        self._degraded: set[str] = set()

    @property
    def projector(self) -> DeliveryTraceProjector:
        return self._projector

    def is_degraded(self, project_id: str) -> bool:
        return project_id in self._degraded

    def handle(self, env: ProjectEventEnvelope) -> DeliveryIngestResult:
        try:
            return self._projector.ingest(env)
        except Exception as exc:  # projection failure must not roll back canonical work
            self._degraded.add(env.project_id)
            if self._jobs is not None:
                self._jobs.enqueue_job(
                    project_id=env.project_id, workspace_id=env.workspace_id,
                    job_id=f"reproject:{env.event_id}", job_type="twin_event_reproject",
                    payload={"event_id": env.event_id, "event_type": env.event_type},
                    idempotency_key=f"reproject:{env.idempotency_key or env.event_id}",
                )
            return DeliveryIngestResult(
                project_id=env.project_id, event_id=env.event_id, accepted=False, degraded=True,
                diagnostics=[_diag(IntelligenceErrorCode.STORE_UNAVAILABLE,
                                   f"projection failed, retry queued: {exc}")],
            )
