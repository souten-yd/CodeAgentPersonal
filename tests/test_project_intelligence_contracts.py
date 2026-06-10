"""PI-1 contract tests — versioned public contracts and coarse facades.

Asserts:
- contract families are versioned and stable;
- public DTOs serialize deterministically and round-trip;
- compatibility readers accept atlas.project_twin.v1;
- the four facades satisfy their Protocols and never fabricate success when disabled;
- no facade exposes a private store object;
- the typed error model is present and no error is silently swallowed into success.
"""

from __future__ import annotations

import pytest

from agent.architecture_blueprint.contracts import (
    ArchitectureBlueprintModule,
    BlueprintActivationRequest,
    BlueprintCreateRequest,
    BlueprintGetRequest,
    BlueprintGetRevisionRequest,
)
from agent.architecture_blueprint.facade import DisabledArchitectureBlueprintModule
from agent.project_convergence.contracts import (
    ConvergenceDecisionRequest,
    ConvergenceGetRequest,
    ConvergenceModule,
    ConvergenceRequest,
)
from agent.project_convergence.facade import DisabledConvergenceModule
from agent.project_intelligence.contracts import (
    ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION,
    DIGITAL_TWIN_CONTRACT_VERSION,
    PROJECT_CONVERGENCE_CONTRACT_VERSION,
    PROJECT_INTELLIGENCE_CONTRACT_VERSION,
    ApplyResultRequest,
    GenerationContextRequest,
    IntelligenceError,
    IntelligenceErrorCode,
    PlanningContextRequest,
    PrepareProjectRequest,
    ProgressRequest,
    ProjectIdentity,
    ProjectIntelligenceModule,
    ProjectMode,
    VerificationResultRequest,
)
from agent.project_intelligence.facade import DisabledProjectIntelligenceModule
from agent.project_twin.facade import (
    DigitalTwinModule,
    DisabledDigitalTwinModule,
    OpenTwinRequest,
    RuntimeIngestRequest,
    TwinContextRequest,
    TwinHealthRequest,
    TwinQueryRequest,
    TwinReadiness,
    accepts_twin_contract_version,
    context_item_from_v1_slice_item,
)
from agent.project_intelligence.contracts import RuntimeObservationRecord


def _identity() -> ProjectIdentity:
    return ProjectIdentity(project_id="p1", workspace_id="w1", project_path="/tmp/p1")


# --- Contract version constants ----------------------------------------------

def test_contract_families_are_versioned() -> None:
    assert PROJECT_INTELLIGENCE_CONTRACT_VERSION == "atlas.project_intelligence.v1"
    assert DIGITAL_TWIN_CONTRACT_VERSION == "atlas.digital_twin.v2"
    assert ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION == "atlas.architecture_blueprint.v1"
    assert PROJECT_CONVERGENCE_CONTRACT_VERSION == "atlas.project_convergence.v1"


# --- Deterministic serialization + round trip --------------------------------

def test_planning_package_serializes_deterministically() -> None:
    m = DisabledProjectIntelligenceModule()
    pkg = m.prepare_planning_context(PlanningContextRequest(project=_identity(), objective="x"))
    a = pkg.model_dump_json()
    b = pkg.model_dump_json()
    assert a == b
    assert pkg.contract_version == PROJECT_INTELLIGENCE_CONTRACT_VERSION


def test_generation_package_round_trips() -> None:
    from agent.project_intelligence.contracts import GenerationContextPackage

    m = DisabledProjectIntelligenceModule()
    pkg = m.prepare_generation_context(
        GenerationContextRequest(project=_identity(), plan_pool_id="pp", plan_item_id="pi")
    )
    restored = GenerationContextPackage.model_validate_json(pkg.model_dump_json())
    assert restored == pkg


def test_twin_context_package_serializes_deterministically() -> None:
    twin = DisabledDigitalTwinModule()
    pkg = twin.build_context(TwinContextRequest(project_id="p1", workspace_id="w1", phase="planning"))
    assert pkg.model_dump_json() == pkg.model_dump_json()
    assert pkg.contract_version == DIGITAL_TWIN_CONTRACT_VERSION


# --- Compatibility readers accept atlas.project_twin.v1 ----------------------

def test_twin_facade_reads_v1_and_v2_versions() -> None:
    assert accepts_twin_contract_version("atlas.project_twin.v1") is True
    assert accepts_twin_contract_version("atlas.digital_twin.v2") is True
    assert accepts_twin_contract_version("atlas.unknown.v9") is False


def test_v1_context_item_adapter_preserves_status_and_confidence() -> None:
    # A v1 inferred fact must stay inferred; the adapter never upgrades it.
    item = context_item_from_v1_slice_item(
        {"ref": "py://m.f", "node_type": "function", "status": "inferred", "confidence": 0.4}
    )
    assert item.ref == "py://m.f"
    assert item.kind == "function"
    assert item.status == "inferred"
    assert item.confidence == 0.4


# --- Facade Protocol conformance ---------------------------------------------

def test_facades_conform_to_protocols() -> None:
    assert isinstance(DisabledProjectIntelligenceModule(), ProjectIntelligenceModule)
    assert isinstance(DisabledDigitalTwinModule(), DigitalTwinModule)
    assert isinstance(DisabledArchitectureBlueprintModule(), ArchitectureBlueprintModule)
    assert isinstance(DisabledConvergenceModule(), ConvergenceModule)


# --- Disabled facades never fabricate success --------------------------------

def test_disabled_project_intelligence_is_inert() -> None:
    ident = _identity()
    m = DisabledProjectIntelligenceModule()
    assert m.prepare_project(PrepareProjectRequest(project=ident)).twin_readiness == "disabled"
    assert m.prepare_project(PrepareProjectRequest(project=ident)).project_mode == ProjectMode.IMPORTED_UNKNOWN
    assert m.record_apply_result(
        ApplyResultRequest(project=ident, plan_pool_id="pp", plan_item_id="pi", success=True)
    ).accepted is False
    assert m.evaluate_progress(ProgressRequest(project=ident)).complete is False


def test_disabled_twin_never_fabricates_revision_or_passed() -> None:
    twin = DisabledDigitalTwinModule()
    state = twin.open_project(OpenTwinRequest(project=_identity()))
    assert state.readiness == TwinReadiness.DISABLED
    assert state.twin_revision_id is None
    # Unavailable observations are counted as unavailable, never ingested as passed.
    obs = RuntimeObservationRecord(
        observation_id="o1", project_id="p1", workspace_id="w1", result="unavailable"
    )
    res = twin.ingest_runtime(RuntimeIngestRequest(project=_identity(), observations=[obs]))
    assert res.ingested_count == 0
    assert res.unavailable_count == 1
    assert res.twin_revision_id is None
    q = twin.query(TwinQueryRequest(project_id="p1", workspace_id="w1"))
    assert q.items == []
    assert twin.health(TwinHealthRequest(project_id="p1", workspace_id="w1")).readiness == TwinReadiness.DISABLED


def test_disabled_convergence_does_not_synthesize_completion() -> None:
    conv = DisabledConvergenceModule()
    dec = conv.decide(ConvergenceDecisionRequest(project_id="p1", workspace_id="w1", report_id="r"))
    assert dec.action == "halt_unsafe"
    assert conv.get_latest(ConvergenceGetRequest(project_id="p1", workspace_id="w1")) is None
    rep = conv.evaluate(
        ConvergenceRequest(
            project_id="p1", workspace_id="w1",
            blueprint_revision_id="b1", actual_twin_revision_id="t1",
        )
    )
    assert rep.element_results == []
    assert rep.diagnostics and rep.diagnostics[0].code == IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE


def test_disabled_blueprint_never_fabricates_activation() -> None:
    bp = DisabledArchitectureBlueprintModule()
    assert bp.get_active(BlueprintGetRequest(project_id="p1")) is None
    assert bp.create(BlueprintCreateRequest(project_id="p1")).status == "unavailable"
    # Activation/get_revision raise typed errors rather than fabricate a revision.
    with pytest.raises(IntelligenceError):
        bp.activate(BlueprintActivationRequest(project_id="p1", blueprint_id="b", revision_id="r"))
    with pytest.raises(IntelligenceError):
        bp.get_revision(BlueprintGetRevisionRequest(project_id="p1", blueprint_id="b", revision_id="r"))


# --- No facade exposes a private store object --------------------------------

def test_facades_expose_no_private_store() -> None:
    # ADR-PI-015: SQLite is an adapter, not the public architecture. The disabled facades
    # hold no store reference at all; the PI coordinator holds only the three sub-facades.
    twin = DisabledDigitalTwinModule()
    bp = DisabledArchitectureBlueprintModule()
    conv = DisabledConvergenceModule()
    for facade in (twin, bp, conv):
        for attr in vars(facade).values():
            assert attr is None or not _looks_like_store(attr)

    pi = DisabledProjectIntelligenceModule()
    held = list(vars(pi).values())
    # Only the three module facades are held — no store / PlanPool / connection.
    assert all(_is_module_facade(v) for v in held)


def _looks_like_store(obj: object) -> bool:
    name = type(obj).__name__.lower()
    return "store" in name or "connection" in name or "sqlite" in name or "session" in name


def _is_module_facade(obj: object) -> bool:
    return isinstance(
        obj,
        (DisabledDigitalTwinModule, DisabledArchitectureBlueprintModule, DisabledConvergenceModule),
    )


# --- Typed error model -------------------------------------------------------

def test_error_model_is_typed_and_not_silent() -> None:
    assert IntelligenceErrorCode.CONVERGENCE_UNAVAILABLE.value == "convergence_unavailable"
    err = IntelligenceError(IntelligenceErrorCode.STALE_TWIN_REVISION, "old")
    assert err.code == IntelligenceErrorCode.STALE_TWIN_REVISION
    assert "stale_twin_revision" in str(err)


def test_unknown_enum_value_is_rejected() -> None:
    # No consumer may infer success from an unknown enum value (contracts doc §1).
    with pytest.raises(ValueError):
        IntelligenceErrorCode("definitely_not_a_real_code")
