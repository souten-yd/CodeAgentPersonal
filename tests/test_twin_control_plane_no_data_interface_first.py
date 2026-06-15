from __future__ import annotations

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.project_intelligence.contracts import ProjectMode
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinInjectionLevel,
    default_hard_constraints,
)
from agent.twin_control_plane.genesis import GenesisKind, classify_genesis
from agent.twin_control_plane.instruction_compiler import compile_model_instruction
from agent.twin_control_plane.interface_first_generator import (
    apply_interface_first_plan,
    generate_interface_first_plan,
)
from agent.twin_control_plane.no_data_bootstrap_gate import (
    BootstrapCondition,
    evaluate_no_data_bootstrap,
)


def _interface_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_id="policy-interface-first",
        route=ForgeRoute.GREENFIELD_SKELETON,
        model_id="local-coder",
        instruction_style=InstructionStyle.INTERFACE_FIRST,
        model_capability_mode=ModelCapabilityMode.WEAK_LOCAL,
        twin_injection_level=TwinInjectionLevel.STRICT_INTERFACE_AND_REPAIR,
        required_twin_modules=["TwinBrief", "NoDataBootstrapGate", "InterfaceFirstGenerator"],
        required_gates=["SafeApplyBoundary", "NoDataBootstrapGate", "TwinProof"],
        hard_constraints=default_hard_constraints(),
        confidence=0.8,
    )


def test_empty_project_creates_bootstrap_requirements_instead_of_assuming_data() -> None:
    assessment = evaluate_no_data_bootstrap(
        genesis_kind=GenesisKind.PROJECT,
        project_mode=ProjectMode.EMPTY,
        has_persisted_state=False,
        prior_runtime_evidence_refs=[],
        prior_test_refs=[],
    )

    assert assessment.bootstrap_required is True
    assert assessment.accept_implementation_without_bootstrap is False
    assert BootstrapCondition.EMPTY_PROJECT in assessment.conditions
    assert BootstrapCondition.MISSING_PERSISTED_STATE in assessment.conditions
    assert BootstrapCondition.NO_RUNTIME_EVIDENCE in assessment.conditions
    assert BootstrapCondition.NO_PRIOR_TESTS in assessment.conditions
    assert any(req.test_ref == "bootstrap://empty_project_clean_workspace" for req in assessment.requirements)
    assert any("must not assume existing files" in req.description for req in assessment.requirements)


def test_feature_with_new_persistence_requires_create_read_reload_proof() -> None:
    classification = classify_genesis(ProjectMode.EXISTING, task_category="feature")
    assessment = evaluate_no_data_bootstrap(
        genesis_kind=classification.genesis_kind,
        project_mode=ProjectMode.EXISTING,
        has_persisted_state=False,
        prior_runtime_evidence_refs=["runtime://smoke"],
        prior_test_refs=["tests/test_existing.py"],
    )
    plan = generate_interface_first_plan(
        classification,
        persistence_schemas=["persistence://proposal_store"],
        bootstrap=assessment,
    )

    assert BootstrapCondition.MISSING_PERSISTED_STATE in assessment.conditions
    assert "Persistence create/read/reload proof." in plan.proof_requirements
    assert "Record create/read/reload evidence and schema expectations." in plan.proof_requirements
    assert "persistence://proposal_store" in plan.required_interfaces


def test_partially_known_project_requires_bootstrap_discovery_without_failure_state() -> None:
    assessment = evaluate_no_data_bootstrap(
        genesis_kind=GenesisKind.FEATURE,
        project_mode=ProjectMode.IMPORTED_UNKNOWN,
        has_persisted_state=True,
        prior_runtime_evidence_refs=[],
        prior_test_refs=[],
    )

    assert assessment.bootstrap_required is True
    assert assessment.accept_implementation_without_bootstrap is False
    assert BootstrapCondition.PARTIALLY_KNOWN_PROJECT in assessment.conditions
    assert BootstrapCondition.NO_RUNTIME_EVIDENCE in assessment.conditions
    assert BootstrapCondition.NO_PRIOR_TESTS in assessment.conditions
    assert not any("passed" in req.proof_requirement.lower() for req in assessment.requirements)
    assert any(req.test_ref == "bootstrap://partial_project_discovery" for req in assessment.requirements)


def test_complete_bootstrap_evidence_allows_implementation_acceptance() -> None:
    assessment = evaluate_no_data_bootstrap(
        genesis_kind=GenesisKind.FEATURE,
        project_mode=ProjectMode.EXISTING,
        has_persisted_state=True,
        prior_runtime_evidence_refs=["runtime://smoke"],
        prior_test_refs=["tests/test_existing.py"],
    )

    assert assessment.bootstrap_required is False
    assert assessment.accept_implementation_without_bootstrap is True
    assert assessment.requirements == []


def test_new_ui_projection_requires_backend_to_ui_state_proof() -> None:
    classification = classify_genesis(
        ProjectMode.EXISTING,
        task_category="ui",
        required_interfaces=["ui://proposal.status_projection"],
    )
    plan = generate_interface_first_plan(
        classification,
        ui_projection_contracts=["ui://proposal.status_projection"],
    )

    assert classification.genesis_kind == GenesisKind.MODULE
    assert "Backend-state-to-UI-state projection proof." in plan.proof_requirements
    ui_section = next(section for section in plan.sections if section.kind.value == "ui_projection")
    assert "Require proof that UI controls do not contradict backend authority." in ui_section.contract_steps


def test_generated_instruction_includes_interface_schema_test_sections_before_implementation() -> None:
    classification = classify_genesis(ProjectMode.EMPTY, task_category="greenfield")
    assessment = evaluate_no_data_bootstrap(
        genesis_kind=classification.genesis_kind,
        project_mode=ProjectMode.EMPTY,
        has_persisted_state=False,
        prior_runtime_evidence_refs=[],
        prior_test_refs=[],
    )
    plan = generate_interface_first_plan(
        classification,
        public_interfaces=["api://todo.create"],
        service_boundaries=["service://todo.command"],
        artifact_schemas=["artifact://todo.snapshot"],
        ui_projection_contracts=["ui://todo.list"],
        persistence_schemas=["persistence://todo_store"],
        test_fixture_contracts=["test://todo.fixture.empty"],
        bootstrap=assessment,
    )
    brief = apply_interface_first_plan(
        TwinBrief(brief_id="brief-interface", goal="create todo app", mode=classification.genesis_kind.value),
        plan,
    )

    instruction = compile_model_instruction(brief, _interface_policy()).text

    public_idx = instruction.index("public_interface")
    persistence_idx = instruction.index("persistence_schema")
    test_idx = instruction.index("test_fixture")
    implementation_idx = instruction.index("Implementation steps")

    assert public_idx < persistence_idx < test_idx < implementation_idx
    assert "api://todo.create" in instruction
    assert "persistence://todo_store" in instruction
    assert "bootstrap://empty_project_clean_workspace" in instruction
    assert "Clean-workspace create/build/test evidence" not in instruction
    assert "Record clean-workspace create/build/test evidence before accepting implementation." in instruction
