"""PDT-5 tests for the Context Broker and pilot adapters."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.project_twin.context_adapters import PatchContextAdapter, PlannerContextAdapter
from agent.project_twin.context_broker import TwinContextBroker
from agent.project_twin.contracts import TwinContextRequest, TwinDelta, TwinNode
from agent.project_twin.store import SqliteProjectTwinStore

NOW = datetime(2026, 6, 9, tzinfo=timezone.utc)


def _node(node_type, ref, label, confidence=0.9) -> TwinNode:
    return TwinNode(
        node_id=ref, project_id="p1", domain="structural", node_type=node_type,
        canonical_ref=ref, label=label, source_kind="git", source_ref="mod.py",
        derivation="deterministic_static", confidence=confidence, status="declared",
        valid_from=NOW, created_at=NOW, updated_at=NOW,
    )


@pytest.fixture()
def populated_store():
    s = SqliteProjectTwinStore(":memory:")
    nodes = [_node("requirement", "requirement://r1", "must support login with email and password")]
    nodes += [_node("function", f"py://mod.py#f{i}", f"function_number_{i}_request_handler") for i in range(60)]
    s.apply_delta(TwinDelta(project_id="p1", idempotency_key="k1", trigger_type="seed", nodes=nodes))
    yield s
    s.close()


def _request(**over) -> TwinContextRequest:
    base = dict(project_id="p1", objective="add login", phase="planning", token_budget=4000)
    base.update(over)
    return TwinContextRequest(**base)


def test_slice_stays_within_budget_and_reports_truncation(populated_store):
    broker = TwinContextBroker(populated_store)
    sl = broker.build_slice(_request(token_budget=256))
    assert sl.used_tokens <= 256
    assert sl.truncated is True
    assert any(e.get("reason") == "token_budget" for e in sl.excluded)


def test_requirements_are_not_dropped_under_pressure(populated_store):
    broker = TwinContextBroker(populated_store)
    sl = broker.build_slice(_request(token_budget=256))
    # The requirement (essential) survives even though most symbols are excluded.
    assert any(it.canonical_ref == "requirement://r1" for it in sl.requirements)


def test_target_ref_gets_inclusion_reason(populated_store):
    broker = TwinContextBroker(populated_store)
    sl = broker.build_slice(_request(token_budget=4000, target_refs=["py://mod.py#f3"]))
    target = next(it for it in sl.symbols if it.canonical_ref == "py://mod.py#f3")
    assert "target_ref" in target.inclusion_reason


def test_disabled_broker_returns_empty_slice(populated_store):
    broker = TwinContextBroker(populated_store, enabled=False)
    sl = broker.build_slice(_request())
    assert sl.used_tokens == 0
    assert sl.requirements == [] and sl.symbols == []
    assert any(e.get("reason") == "broker_disabled" for e in sl.excluded)


# --- pilot adapters depend only on the port ----------------------------------

def test_planner_adapter_augments_when_enabled(populated_store):
    adapter = PlannerContextAdapter(TwinContextBroker(populated_store))
    out = adapter.augment(project_id="p1", objective="add login", baseline_context="BASE")
    assert out["twin_applied"] is True
    assert "BASE" in out["context_text"]
    assert "Project Twin context (planning)" in out["context_text"]
    assert "must support login" in out["context_text"]


def test_disabled_broker_preserves_baseline(populated_store):
    adapter = PatchContextAdapter(TwinContextBroker(populated_store, enabled=False))
    out = adapter.augment(project_id="p1", objective="x", baseline_context="ORIGINAL")
    assert out["twin_applied"] is False
    assert out["context_text"] == "ORIGINAL"
    assert out["used_tokens"] == 0


def test_adapter_holds_only_the_port_not_the_store(populated_store):
    adapter = PlannerContextAdapter(TwinContextBroker(populated_store))
    # The adapter must not expose or hold a direct store reference.
    assert not hasattr(adapter, "_store")
    assert hasattr(adapter, "_port")
