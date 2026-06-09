"""PDT-1 contract tests for agent.project_twin.

Covers the mandatory contract behaviors that are testable without a store:
deterministic round-trip serialization, invalid-value rejection, bound enforcement,
version compatibility, event envelope, port importability, no storage dependency, and
the skill-safety / truthful-collector invariants.
"""

from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent.project_twin import (
    CONTRACT_VERSION,
    EVENT_TYPES,
    ContextItem,
    ImpactRequest,
    IntentTracePort,
    ProjectTwinPort,
    RuntimeObservation,
    SkillActivation,
    StaticAnalysisPort,
    TwinContextPort,
    TwinContextRequest,
    TwinDelta,
    TwinEdge,
    TwinEvidence,
    TwinMemoryPort,
    TwinNode,
    TwinQuery,
    TwinSkillPort,
    TwinEventEnvelope,
    assert_supported_version,
    is_compatible_version,
    make_event_envelope,
    parse_contract_version,
)
from agent.project_twin.contracts import RuntimeObservationPort

NOW = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)


def _node(**over) -> TwinNode:
    base = dict(
        node_id="n1",
        project_id="p1",
        domain="structural",
        node_type="function",
        canonical_ref="py://mod.f",
        label="f",
        source_kind="git",
        source_ref="mod.py",
        derivation="deterministic_static",
        confidence=0.9,
        status="declared",
        valid_from=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(over)
    return TwinNode(**base)


def _edge(**over) -> TwinEdge:
    base = dict(
        edge_id="e1",
        project_id="p1",
        domain="structural",
        source_node_id="n1",
        target_node_id="n2",
        edge_type="calls",
        source_kind="git",
        source_ref="mod.py",
        derivation="deterministic_static",
        confidence=0.8,
        status="declared",
        valid_from=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(over)
    return TwinEdge(**base)


def _evidence(**over) -> TwinEvidence:
    base = dict(
        evidence_id="ev1",
        project_id="p1",
        evidence_type="test_run",
        source_kind="pytest",
        source_ref="tests/test_x.py::t",
        summary="passed",
        confidence=1.0,
        created_at=NOW,
    )
    base.update(over)
    return TwinEvidence(**base)


# --- round-trip + determinism ------------------------------------------------

@pytest.mark.parametrize("factory", [_node, _edge, _evidence])
def test_round_trip_serialization(factory):
    model = factory()
    payload = model.model_dump_json()
    restored = type(model).model_validate_json(payload)
    assert restored == model
    # deterministic: repeated dumps are byte-identical and field order is stable
    assert model.model_dump_json() == payload


def test_node_carries_contract_version():
    assert _node().contract_version == CONTRACT_VERSION


def test_delta_round_trip_with_nested_collections():
    delta = TwinDelta(
        project_id="p1",
        idempotency_key="k1",
        trigger_type="workspace.changed",
        nodes=[_node()],
        edges=[_edge()],
        evidence=[_evidence()],
        observations=[
            RuntimeObservation(
                observation_id="o1",
                project_id="p1",
                collector="pytest",
                collector_version="1",
                observation_type="test",
                subject_refs=["py://mod.f"],
                timestamp=NOW,
                result="passed",
                summary="ok",
            )
        ],
    )
    restored = TwinDelta.model_validate_json(delta.model_dump_json())
    assert restored == delta


# --- invalid value rejection -------------------------------------------------

@pytest.mark.parametrize("bad_conf", [-0.1, 1.1, 2.0])
def test_invalid_confidence_rejected(bad_conf):
    with pytest.raises(ValidationError):
        _node(confidence=bad_conf)


def test_invalid_status_rejected():
    with pytest.raises(ValidationError):
        _node(status="totally_made_up")


def test_invalid_domain_rejected():
    with pytest.raises(ValidationError):
        _node(domain="nonsense")


def test_query_limit_and_depth_bounds():
    with pytest.raises(ValidationError):
        TwinQuery(project_id="p1", limit=0)
    with pytest.raises(ValidationError):
        TwinQuery(project_id="p1", limit=10_000)
    with pytest.raises(ValidationError):
        TwinQuery(project_id="p1", max_depth=99)


def test_context_budget_bounds():
    with pytest.raises(ValidationError):
        TwinContextRequest(project_id="p1", objective="o", phase="planning", token_budget=10)
    ok = TwinContextRequest(project_id="p1", objective="o", phase="planning", token_budget=4000)
    assert ok.token_budget == 4000


def test_impact_request_requires_changed_refs():
    with pytest.raises(ValidationError):
        ImpactRequest(project_id="p1", change_kind="signature")  # type: ignore[call-arg]


# --- versioning --------------------------------------------------------------

def test_version_helpers():
    assert is_compatible_version(CONTRACT_VERSION)
    assert parse_contract_version(CONTRACT_VERSION) == 1
    assert not is_compatible_version("atlas.project_twin.v2")
    assert not is_compatible_version("garbage")
    assert_supported_version(CONTRACT_VERSION)
    with pytest.raises(ValueError):
        assert_supported_version("atlas.project_twin.v9")


# --- events ------------------------------------------------------------------

def test_event_envelope_defaults_and_catalog():
    env = make_event_envelope(
        event_id="ev",
        event_type="workspace.changed",
        project_id="p1",
        source="workspace",
        idempotency_key="idem",
    )
    assert isinstance(env, TwinEventEnvelope)
    assert env.contract_version == CONTRACT_VERSION
    assert env.occurred_at is not None
    assert "safe_apply.completed" in EVENT_TYPES


# --- ports importable & structurally checkable -------------------------------

def test_ports_are_runtime_checkable_protocols():
    class _Stub:
        def get_health(self, project_id): ...
        def get_snapshot(self, project_id, revision_id=None): ...
        def apply_delta(self, delta): ...
        def query(self, query): ...
        def trace_path(self, request): ...
        def assess_impact(self, request): ...

    assert isinstance(_Stub(), ProjectTwinPort)
    # each port is importable
    for port in (
        StaticAnalysisPort,
        RuntimeObservationPort,
        IntentTracePort,
        TwinContextPort,
        TwinMemoryPort,
        TwinSkillPort,
    ):
        assert port is not None


# --- no storage dependency in the contract package ---------------------------

FORBIDDEN_IMPORTS = ("sqlite3", "storage", "fastapi", "requests", "httpx")


@pytest.mark.parametrize(
    "module_name",
    [
        "agent.project_twin.types",
        "agent.project_twin.versioning",
        "agent.project_twin.events",
        "agent.project_twin.contracts",
    ],
)
def test_contract_modules_have_no_storage_dependency(module_name):
    mod = importlib.import_module(module_name)
    src = inspect.getsource(mod)
    for token in FORBIDDEN_IMPORTS:
        assert f"import {token}" not in src, f"{module_name} must not import {token}"
        assert f"from {token}" not in src, f"{module_name} must not import from {token}"


# --- safety invariants at the contract level ---------------------------------

def test_skill_activation_has_no_authority_fields():
    # A skill activation records selection/version/outcome only; it cannot carry
    # allowed paths, commands, or approval — it must not be able to expand authority.
    fields = set(SkillActivation.model_fields)
    for forbidden in ("allowed_paths", "commands", "approval", "authority", "allow_commands"):
        assert forbidden not in fields


def test_runtime_observation_supports_unavailable_truthfully():
    obs = RuntimeObservation(
        observation_id="o",
        project_id="p1",
        collector="playwright",
        collector_version="1",
        observation_type="browser",
        subject_refs=[],
        timestamp=NOW,
        result="unavailable",
        summary="browser not installed",
    )
    assert obs.result == "unavailable"
    with pytest.raises(ValidationError):
        RuntimeObservation(
            observation_id="o",
            project_id="p1",
            collector="playwright",
            collector_version="1",
            observation_type="browser",
            subject_refs=[],
            timestamp=NOW,
            result="success",  # not a valid result literal
            summary="x",
        )


def test_context_item_requires_inclusion_reason():
    with pytest.raises(ValidationError):
        ContextItem(
            item_type="symbol",
            canonical_ref="py://mod.f",
            summary="f",
            status="declared",
            confidence=0.5,
            estimated_tokens=10,
        )  # type: ignore[call-arg]
