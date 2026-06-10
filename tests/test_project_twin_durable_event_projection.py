"""PIR-4 durable event projection and delivery trace tests."""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.contracts import (
    ApplyResultRequest,
    ProjectIdentity,
    RuntimeObservationRecord,
    VerificationResultRequest,
)
from agent.project_intelligence.factory import build_project_intelligence
from agent.project_intelligence.rollout import RolloutConfig
from agent.project_intelligence.store import ProjectIntelligenceStore
from agent.project_twin.event_bridge import CanonicalEventBridge, DeliveryTraceProjector
from agent.project_twin.event_projection_store import DurableDeliveryTraceProjector, EventProjectionStore
from agent.project_twin.facade import OpenTwinRequest, ProjectEventEnvelope, TwinQueryRequest
from agent.project_twin.module import DigitalTwinModuleImpl


def _env(
    event_type: str,
    *,
    eid: str,
    payload: dict,
    workspace_id: str = "w1",
    idem: str | None = None,
    plan_item_id: str | None = None,
    plan_pool_id: str | None = None,
    source_ref: str | None = None,
    rev: str | None = "abc123",
) -> ProjectEventEnvelope:
    return ProjectEventEnvelope(
        event_id=eid,
        event_type=event_type,
        project_id="p1",
        workspace_id=workspace_id,
        source="atlas",
        source_ref=source_ref,
        source_revision=rev,
        idempotency_key=idem or eid,
        correlation_id="corr1",
        plan_pool_id=plan_pool_id,
        plan_item_id=plan_item_id,
        payload=payload,
    )


def _full_flow_events(workspace_id: str = "w1") -> list[ProjectEventEnvelope]:
    return [
        _env("conversation.message.completed", eid="e0", workspace_id=workspace_id, payload={"message_ref": "m1"}),
        _env(
            "requirement.confirmed",
            eid="e1",
            workspace_id=workspace_id,
            payload={"requirement_id": "R1", "text": "do x", "source_message_ref": "m1"},
        ),
        _env("plan.created", eid="e2", workspace_id=workspace_id, payload={"plan_id": "PL1"}),
        _env(
            "plan_item.completed",
            eid="e3",
            workspace_id=workspace_id,
            plan_item_id="PI1",
            plan_pool_id="PL1",
            payload={"requirement_ids": ["R1"]},
        ),
        _env(
            "proposal.generated",
            eid="e4",
            workspace_id=workspace_id,
            plan_item_id="PI1",
            payload={"proposal_id": "PR1"},
        ),
        _env(
            "safe_apply.completed",
            eid="e5",
            workspace_id=workspace_id,
            plan_item_id="PI1",
            payload={"proposal_id": "PR1", "applied_refs": ["file://app.py"], "new_source_revision": "def456"},
        ),
        _env(
            "verification.completed",
            eid="e6",
            workspace_id=workspace_id,
            plan_item_id="PI1",
            payload={"verification_id": "V1", "result": "passed", "evidence_refs": ["evidence://log1"]},
        ),
    ]


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_durable_delivery_trace_survives_restart_with_full_payload(tmp_path: Path) -> None:
    db = tmp_path / "events.db"
    projector = DurableDeliveryTraceProjector(EventProjectionStore(db))
    for env in _full_flow_events():
        assert projector.ingest(env).accepted is True
    projector.close()

    reopened_store = EventProjectionStore(db)
    reopened = DurableDeliveryTraceProjector(reopened_store)
    trace = reopened.get_trace("p1", "requirement://R1", workspace_id="w1")
    payload = reopened_store.event_payload("p1", "w1", "e5")
    reopened.close()

    refs = {node.ref for node in trace.nodes}
    assert {"requirement://R1", "planitem://PI1", "proposal://PR1", "file://app.py", "verification://V1"} <= refs
    assert payload is not None
    assert payload["payload"]["applied_refs"] == ["file://app.py"]


def test_durable_duplicate_replay_is_idempotent(tmp_path: Path) -> None:
    projector = DurableDeliveryTraceProjector(EventProjectionStore(tmp_path / "events.db"))
    events = _full_flow_events()
    for env in events:
        assert projector.ingest(env).duplicate is False
    before = projector.get_trace("p1", "requirement://R1", workspace_id="w1")

    results = [projector.ingest(env) for env in events]
    after = projector.get_trace("p1", "requirement://R1", workspace_id="w1")
    projector.close()

    assert all(result.duplicate for result in results)
    assert len(after.nodes) == len(before.nodes)
    assert len(after.edges) == len(before.edges)


def test_durable_projection_is_workspace_isolated(tmp_path: Path) -> None:
    projector = DurableDeliveryTraceProjector(EventProjectionStore(tmp_path / "events.db"))
    for env in _full_flow_events("w1"):
        projector.ingest(env)
    projector.ingest(_env("requirement.confirmed", eid="w2-e1", workspace_id="w2", payload={"requirement_id": "R2"}))

    w1 = projector.get_trace("p1", "requirement://R1", workspace_id="w1")
    w2 = projector.get_trace("p1", "requirement://R1", workspace_id="w2")
    projector.close()

    assert any(node.ref == "requirement://R1" for node in w1.nodes)
    assert w2.nodes == []
    assert w2.edges == []


def test_poison_event_is_diagnosable_without_blocking_later_events(tmp_path: Path) -> None:
    store = EventProjectionStore(tmp_path / "events.db")
    projector = DurableDeliveryTraceProjector(store)

    poison = projector.ingest(_env("not.a.real.event", eid="bad", payload={}))
    ok = projector.ingest(_env("requirement.confirmed", eid="good", payload={"requirement_id": "R1"}))
    trace = projector.get_trace("p1", "requirement://R1", workspace_id="w1")
    state = store.event_state("p1", "w1", "bad")
    projector.close()

    assert poison.accepted is False
    assert state == "poison"
    assert ok.accepted is True
    assert [node.ref for node in trace.nodes] == ["requirement://R1"]
    assert any("unknown event type" in diagnostic.message for diagnostic in trace.diagnostics)


def test_projection_failure_queues_retry_with_full_event_payload() -> None:
    class _Boom(DeliveryTraceProjector):
        def ingest(self, env):  # noqa: ANN001
            raise RuntimeError("projection store down")

    store = ProjectIntelligenceStore()
    bridge = CanonicalEventBridge(_Boom(), job_store=store)
    event = _env("requirement.confirmed", eid="e1", payload={"requirement_id": "R1"})

    result = bridge.handle(event)
    jobs = store.list_jobs("p1")
    store.close()

    assert result.accepted is False and result.degraded is True
    assert len(jobs) == 1
    assert jobs[0]["payload"]["event_payload"]["payload"]["requirement_id"] == "R1"


def test_safe_apply_event_projects_trace_and_triggers_twin_refresh(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "app.py", "def f():\n    return 1\n")
    projector = DurableDeliveryTraceProjector(EventProjectionStore(tmp_path / "events.db"))
    twin = DigitalTwinModuleImpl(
        tmp_path / "twin.db",
        event_bridge=CanonicalEventBridge(projector),
    )
    project = ProjectIdentity(project_id="p1", workspace_id="w1", project_path=str(root))
    twin.open_project(OpenTwinRequest(project=project))

    _write(root, "app.py", "def f():\n    return 1\n\ndef g():\n    return 2\n")
    event = _env(
        "safe_apply.completed",
        eid="apply-1",
        payload={
            "proposal_id": "PR1",
            "applied_refs": ["file://app.py"],
            "changed_paths": ["app.py"],
            "project_path": str(root),
        },
        plan_item_id="PI1",
    )
    result = twin.ingest_event(event)
    query = twin.query(TwinQueryRequest(project_id="p1", workspace_id="w1", refs=["py://app.py#g"]))
    trace = projector.get_trace("p1", "file://app.py", workspace_id="w1")
    twin.close()

    assert result.accepted is True
    assert [item.ref for item in query.items] == ["py://app.py#g"]
    assert any(edge.target_ref == "file://app.py" and edge.edge_type == "applies_to" for edge in trace.edges)


def test_project_intelligence_apply_and_verification_records_create_delivery_path(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "app.py", "def f():\n    return 1\n")
    projector = DurableDeliveryTraceProjector(EventProjectionStore(tmp_path / "events.db"))
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db", event_bridge=CanonicalEventBridge(projector))
    coord = build_project_intelligence(rollout=RolloutConfig(enabled=True), digital_twin=twin)
    project = ProjectIdentity(project_id="p1", workspace_id="w1", project_path=str(root))
    twin.open_project(OpenTwinRequest(project=project))

    apply = coord.record_apply_result(
        ApplyResultRequest(
            project=project,
            plan_pool_id="PL1",
            plan_item_id="PI1",
            applied_refs=["file://app.py"],
            success=True,
            correlation_id="apply-1",
        )
    )
    verify = coord.record_verification_result(
        VerificationResultRequest(
            project=project,
            plan_pool_id="PL1",
            plan_item_id="PI1",
            observations=[
                RuntimeObservationRecord(
                    observation_id="obs1",
                    project_id="p1",
                    workspace_id="w1",
                    result="passed",
                    evidence_refs=["evidence://log1"],
                )
            ],
            correlation_id="ver-1",
        )
    )
    trace = projector.get_trace("p1", "file://app.py", workspace_id="w1")
    twin.close()

    assert apply.accepted is True
    assert verify.accepted is True
    assert {"file://app.py", "verification://ver-1", "evidence://log1"} <= {node.ref for node in trace.nodes}
    assert any(edge.edge_type == "produced" and edge.target_ref == "evidence://log1" for edge in trace.edges)
