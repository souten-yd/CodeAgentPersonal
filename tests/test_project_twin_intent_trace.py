"""PDT-4 tests for the intent and delivery trace projector."""

from __future__ import annotations

import pytest

from agent.project_twin.contracts import IntentDeliveryEvent
from agent.project_twin.intent_trace import IntentDeliveryProjector
from agent.project_twin.static_graph import nid
from agent.project_twin.store import SqliteProjectTwinStore


def _event(event_type, payload, idem):
    return IntentDeliveryEvent(
        project_id="p1",
        event_type=event_type,
        source_ref=f"src/{idem}",
        idempotency_key=idem,
        payload=payload,
    )


@pytest.fixture()
def proj():
    return IntentDeliveryProjector()


def test_message_projection(proj):
    delta = proj.project(_event("conversation.message.completed",
                                {"conversation_id": "c1", "message_id": "m1", "role": "user", "summary": "add login"}, "e1"))
    refs = {n.canonical_ref for n in delta.nodes}
    assert "conversation://c1" in refs and "message://c1/m1" in refs
    assert any(e.edge_type == "contains_message" for e in delta.edges)
    assert all(n.derivation == "canonical_projection" for n in delta.nodes)


def test_requirement_with_and_without_source(proj):
    ok = proj.project(_event("requirement.confirmed",
                             {"requirement_id": "r1", "text": "login", "source_conversation_id": "c1",
                              "source_message_id": "m1", "constraints": [{"id": "k1", "text": "use OAuth"}]}, "e2"))
    assert any(e.edge_type == "derives_requirement" for e in ok.edges)
    assert any(n.canonical_ref == "constraint://r1/k1" for n in ok.nodes)

    missing = proj.project(_event("requirement.confirmed", {"requirement_id": "r2", "text": "x"}, "e3"))
    assert any(d["code"] == "requirement_without_source_message" for d in missing.diagnostics)


def test_plan_item_links(proj):
    delta = proj.project(_event("plan_item.completed",
                                {"plan_pool_id": "pool1", "plan_item_id": "i1", "requirement_id": "r1",
                                 "changed_files": ["app/login.py"], "changed_symbols": ["py://app/login.py#login"]}, "e4"))
    et = {(e.edge_type, e.target_node_id) for e in delta.edges}
    assert ("planned_as", nid("planitem://pool1/i1")) in et
    assert ("changed_file", nid("file://app/login.py")) in et
    assert ("changed_symbol", nid("py://app/login.py#login")) in et


def test_unsupported_event_diagnostic(proj):
    delta = proj.project(_event("something.else", {}, "e5"))
    assert any(d["code"] == "unsupported_event_type" for d in delta.diagnostics)


def test_full_chain_is_queryable(proj):
    store = SqliteProjectTwinStore(":memory:")
    events = [
        _event("conversation.message.completed",
               {"conversation_id": "c1", "message_id": "m1", "role": "user", "summary": "add login"}, "e1"),
        _event("requirement.confirmed",
               {"requirement_id": "r1", "text": "login", "source_conversation_id": "c1", "source_message_id": "m1"}, "e2"),
        _event("plan_item.completed",
               {"plan_pool_id": "pool1", "plan_item_id": "i1", "requirement_id": "r1",
                "changed_files": ["app/login.py"], "changed_symbols": ["py://app/login.py#login"]}, "e3"),
        _event("safe_apply.completed",
               {"proposal_id": "pr1", "plan_pool_id": "pool1", "plan_item_id": "i1",
                "applied_files": ["app/login.py"], "apply_status": "applied"}, "e4"),
        _event("verification.completed",
               {"verification_id": "v1", "plan_pool_id": "pool1", "plan_item_id": "i1", "result": "passed",
                "tests": [{"ref": "test://tests/test_login.py::test_login", "result": "passed"}],
                "evidence": [{"id": "ev1", "summary": "1 passed", "result": "passed",
                              "test_ref": "test://tests/test_login.py::test_login"}]}, "e5"),
    ]
    for ev in events:
        store.apply_delta(proj.project(ev))

    snap = store.get_snapshot("p1")
    # undirected adjacency over current edges
    adj: dict[str, set[str]] = {}
    for e in snap.edges:
        adj.setdefault(e.source_node_id, set()).add(e.target_node_id)
        adj.setdefault(e.target_node_id, set()).add(e.source_node_id)

    def reachable(start_ref: str, goal_ref: str) -> bool:
        start, goal = nid(start_ref), nid(goal_ref)
        seen, stack = {start}, [start]
        while stack:
            cur = stack.pop()
            if cur == goal:
                return True
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return False

    # Message -> Requirement -> PlanItem -> Symbol  and  PlanItem -> Test -> Evidence
    assert reachable("message://c1/m1", "evidence://ev1")
    assert reachable("message://c1/m1", "py://app/login.py#login")
    assert reachable("requirement://r1", "test://tests/test_login.py::test_login")

    # source IDs are preserved on the projected nodes
    refs = {n.canonical_ref for n in snap.nodes}
    for expected in (
        "message://c1/m1", "requirement://r1", "planitem://pool1/i1",
        "proposal://pr1", "verification://v1", "evidence://ev1",
    ):
        assert expected in refs
    store.close()
