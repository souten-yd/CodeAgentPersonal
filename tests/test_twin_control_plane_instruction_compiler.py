from __future__ import annotations

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    GitPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinInjectionLevel,
    default_hard_constraints,
)
from agent.twin_control_plane.instruction_compiler import compile_model_instruction


def _brief() -> TwinBrief:
    return TwinBrief(
        brief_id="brief1",
        goal="add proposal summary",
        mode="feature_genesis",
        allowed_refs=["file://agent/example.py", "test://example"],
        forbidden_refs=["file://secrets.env"],
        hard_constraints=[
            *default_hard_constraints(),
            TwinConstraint(
                constraint_id="preserve_runtime_evidence",
                text="Unavailable runtime evidence must remain unavailable.",
                refs=["RuntimeEvidence"],
            ),
        ],
        advisory_context=["impact:agent/example.py:confidence=medium"],
        contracts_to_preserve=["contract://proposal.safe_apply"],
        required_interfaces=["api://proposal.summary"],
        impacted_refs=["py://agent.example.summarize"],
        required_tests=["tests/test_example.py::test_summary"],
        proof_requirements=["prove safe apply remains the mutation boundary"],
    )


def _policy(
    *,
    mode: ModelCapabilityMode = ModelCapabilityMode.WEAK_LOCAL,
    style: InstructionStyle = InstructionStyle.CONSTRAINED_PATCH,
) -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_id=f"policy-{mode.value}-{style.value}",
        route=ForgeRoute.BLUEPRINT_SLICE,
        model_id="local-coder",
        instruction_style=style,
        model_capability_mode=mode,
        twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
        required_twin_modules=["TwinBrief", "TwinProof"],
        required_gates=["SafeApplyBoundary", "TwinProof", "NoTestWeakening"],
        git_policy=GitPolicy(local_branch_required=True, local_commit_required=True),
        hard_constraints=default_hard_constraints(),
        advisory_context=["route_candidates=blueprint_slice,test_first"],
        reasons=["test"],
        confidence=0.8,
    )


def test_weak_local_instruction_includes_refs_gates_tests_and_proof_requirements() -> None:
    instruction = compile_model_instruction(_brief(), _policy()).text

    assert "mode=weak_local" in instruction
    assert "Use constrained implementation steps" in instruction
    assert "file://agent/example.py" in instruction
    assert "file://secrets.env" in instruction
    assert "tests/test_example.py::test_summary" in instruction
    assert "prove safe apply remains the mutation boundary" in instruction
    assert "SafeApplyBoundary" in instruction
    assert "TwinProof" in instruction
    assert "Remote publication and remote mutation require explicit approval" in instruction
    assert "Stale tests are retirement candidates only" in instruction


def test_frontier_assisted_instruction_supports_twin_challenge_but_preserves_hard_constraints() -> None:
    instruction = compile_model_instruction(
        _brief(),
        _policy(mode=ModelCapabilityMode.FRONTIER_ASSISTED, style=InstructionStyle.FREEFORM_DESIGN),
    ).text

    assert "mode=frontier_assisted" in instruction
    assert "Twin Challenge is allowed only as advisory critique with evidence" in instruction
    assert "File mutation must remain behind the Atlas Safe Apply boundary" in instruction
    assert "Remote publication or remote mutation requires approval" in instruction
    assert "## Advisory Context (Non-Authoritative)" in instruction
    assert "impact:agent/example.py:confidence=medium" in instruction


def test_audit_only_instruction_does_not_imply_file_mutation_authority() -> None:
    instruction = compile_model_instruction(
        _brief(),
        _policy(mode=ModelCapabilityMode.AUDIT_ONLY, style=InstructionStyle.AUDIT_ONLY),
    ).text

    assert "Audit only. Do not mutate files" in instruction
    assert "## Audit Obligations" in instruction
    assert "Return findings and suggested repairs only" in instruction
    assert "## Implementation Obligations" not in instruction


def test_audit_only_style_is_non_mutating_even_for_standard_model_mode() -> None:
    instruction = compile_model_instruction(
        _brief(),
        _policy(mode=ModelCapabilityMode.STANDARD, style=InstructionStyle.AUDIT_ONLY),
    ).text

    assert "Audit only. Do not mutate files" in instruction
    assert "## Audit Obligations" in instruction
    assert "## Implementation Obligations" not in instruction


def test_instruction_compiler_output_is_deterministic_for_same_input() -> None:
    brief = _brief()
    policy = _policy()

    first = compile_model_instruction(brief, policy)
    second = compile_model_instruction(brief, policy)

    assert first.instruction_id == second.instruction_id
    assert first.text == second.text
    assert first.sections == second.sections


def test_interface_first_instruction_orders_contract_steps_before_implementation() -> None:
    instruction = compile_model_instruction(_brief(), _policy(style=InstructionStyle.INTERFACE_FIRST)).text

    interface_idx = instruction.index("Public interfaces and API contracts")
    persistence_idx = instruction.index("Persistence and artifact schemas")
    state_idx = instruction.index("Backend-to-UI or runtime state contracts")
    test_idx = instruction.index("Test contracts and fixtures")
    implementation_idx = instruction.index("Implementation steps")

    assert interface_idx < persistence_idx < state_idx < test_idx < implementation_idx
    assert "api://proposal.summary" in instruction
