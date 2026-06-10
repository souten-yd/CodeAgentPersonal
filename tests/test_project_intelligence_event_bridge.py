"""PI-5 canonical event bridge and delivery-trace tests.

Acceptance criteria (implementation plan PI-5):
- a real requirement/plan/proposal/apply/verification flow produces a delivery trace;
- duplicate replay does not duplicate facts;
- missing links create diagnostics, not fabricated edges;
- canonical stores remain unchanged by projection (the bridge has no canonical-write path);
plus projection failure marks degraded and queues retry without rolling back canonical work.
"""

from __future__ import annotations

import pytest

from agent.project_twin.event_bridge import (
    CanonicalEventBridge,
    DeliveryTraceProjector,
)
from agent.project_twin.facade import ProjectEventEnvelope
from agent.project_intelligence.store import ProjectIntelligenceStore


def _env(event_type: str, *, eid: str, payload: dict, idem: str | None = None,
         plan_item_id: str | None = None, plan_pool_id: str | None = None,
         source_ref: str | None = None, rev: str | None = "abc123") -> ProjectEventEnvelope:
    return ProjectEventEnvelope(
        event_id=eid, event_type=event_type, project_id="p1", workspace_id="w1",
        source="atlas", source_ref=source_ref, source_revision=rev,
        idempotency_key=idem or eid, correlation_id="corr1",
        plan_pool_id=plan_pool_id, plan_item_id=plan_item_id, payload=payload,
    )


def _full_flow_events() -> list[ProjectEventEnvelope]:
    return [
        _env("conversation.message.completed", eid="e0", payload={"message_ref": "m1"}),
        _env("requirement.confirmed", eid="e1", payload={"requirement_id": "R1", "text": "do x",
                                                          "source_message_ref": "m1"}),
        _env("plan.created", eid="e2", payload={"plan_id": "PL1"}),
        _env("plan_item.completed", eid="e3", plan_item_id="PI1", plan_pool_id="PL1",
             payload={"requirement_ids": ["R1"]}),
        _env("proposal.generated", eid="e4", plan_item_id="PI1", payload={"proposal_id": "PR1"}),
        _env("safe_apply.completed", eid="e5", plan_item_id="PI1",
             payload={"proposal_id": "PR1", "applied_refs": ["file://app.py"],
                      "new_source_revision": "def456"}),
        _env("verification.completed", eid="e6", plan_item_id="PI1",
             payload={"verification_id": "V1", "result": "passed",
                      "evidence_refs": ["evidence://log1"]}),
    ]


# --- Full delivery flow ------------------------------------------------------

def test_full_flow_produces_delivery_trace() -> None:
    proj = DeliveryTraceProjector()
    for env in _full_flow_events():
        assert proj.ingest(env).accepted is True

    trace = proj.get_trace("p1", "requirement://R1")
    refs = {n.ref for n in trace.nodes}
    # The whole chain is reachable from the requirement.
    assert {"requirement://R1", "planitem://PI1", "proposal://PR1",
            "file://app.py", "verification://V1", "evidence://log1"} <= refs
    edge_types = {(e.source_ref, e.target_ref, e.edge_type) for e in trace.edges}
    assert ("requirement://R1", "planitem://PI1", "implemented_by") in edge_types
    assert ("planitem://PI1", "proposal://PR1", "proposes") in edge_types
    assert ("proposal://PR1", "file://app.py", "applies_to") in edge_types
    assert ("planitem://PI1", "verification://V1", "verified_by") in edge_types
    assert ("verification://V1", "evidence://log1", "produced") in edge_types


def test_revision_ids_preserved_on_applied_refs() -> None:
    proj = DeliveryTraceProjector()
    for env in _full_flow_events():
        proj.ingest(env)
    applied = next(n for n in proj.get_trace("p1", "file://app.py").nodes if n.ref == "file://app.py")
    assert applied.source_revision == "def456"  # apply revision preserved


# --- Idempotent replay -------------------------------------------------------

def test_duplicate_replay_does_not_duplicate_facts() -> None:
    proj = DeliveryTraceProjector()
    events = _full_flow_events()
    for env in events:
        proj.ingest(env)
    trace1 = proj.get_trace("p1", "requirement://R1")

    # Replay the entire flow again (at-least-once delivery).
    results = [proj.ingest(env) for env in events]
    assert all(r.duplicate for r in results)
    assert all(r.added_nodes == 0 and r.added_edges == 0 for r in results)
    trace2 = proj.get_trace("p1", "requirement://R1")
    assert len(trace2.nodes) == len(trace1.nodes)
    assert len(trace2.edges) == len(trace1.edges)


# --- Missing links create diagnostics, not fabricated edges ------------------

def test_missing_link_creates_diagnostic_not_edge() -> None:
    proj = DeliveryTraceProjector()
    # A proposal with no plan item: node is created, but no edge is fabricated.
    res = proj.ingest(_env("proposal.generated", eid="x1", payload={"proposal_id": "PR9"}))
    assert res.accepted and res.added_nodes == 1 and res.added_edges == 0
    assert any("plan item" in d.message for d in res.diagnostics)
    trace = proj.get_trace("p1", "proposal://PR9")
    assert trace.edges == []


def test_unknown_event_type_is_rejected_with_diagnostic() -> None:
    proj = DeliveryTraceProjector()
    res = proj.ingest(_env("not.a.real.event", eid="z1", payload={}))
    assert res.accepted is False
    assert res.diagnostics and "unknown event type" in res.diagnostics[0].message


# --- Project isolation -------------------------------------------------------

def test_projection_is_project_isolated() -> None:
    proj = DeliveryTraceProjector()
    proj.ingest(_env("requirement.confirmed", eid="e1", payload={"requirement_id": "R1"}))
    # A different project's trace must not see p1 facts.
    other = proj.get_trace("p2", "requirement://R1")
    assert other.nodes == [] and other.edges == []


# --- Failure marks degraded and queues retry (no canonical rollback) ---------

def test_projection_failure_marks_degraded_and_queues_retry() -> None:
    class _Boom(DeliveryTraceProjector):
        def ingest(self, env):  # noqa: ANN001
            raise RuntimeError("projection store down")

    store = ProjectIntelligenceStore()
    bridge = CanonicalEventBridge(_Boom(), job_store=store)
    res = bridge.handle(_env("requirement.confirmed", eid="e1", payload={"requirement_id": "R1"}))
    assert res.accepted is False and res.degraded is True
    assert bridge.is_degraded("p1") is True
    # A retry job was queued (idempotent); canonical state is untouched (no store mutation here).
    jobs = store.list_jobs("p1")
    assert len(jobs) == 1 and jobs[0]["job_type"] == "twin_event_reproject"


def test_bridge_holds_no_canonical_store() -> None:
    bridge = CanonicalEventBridge()
    for value in vars(bridge).values():
        name = type(value).__name__.lower()
        assert "planpool" not in name and "conversation" not in name and "sqlite" not in name
