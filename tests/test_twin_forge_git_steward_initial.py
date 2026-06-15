from __future__ import annotations

from agent.git_steward.contracts import DEFAULT_EXCLUDE_PATTERNS, GitOperationClass, classify_git_operation
from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.project_intelligence.contracts import (
    ContextManifest,
    GenerationContextPackage,
    InterfaceSummary,
    SourceExcerpt,
    SourceFileContext,
    SymbolSummary,
    VerificationRequirement,
)
from agent.twin_control_plane.contracts import (
    InstructionStyle,
    ModelCapabilityMode,
    TwinInjectionLevel,
)
from agent.twin_control_plane.twin_brief import compile_generation_twin_brief


def test_execution_policy_preserves_route_matrix_safety_for_large_change() -> None:
    selector = ExecutionPolicySelector()
    profile = ModelCapabilityProfile(model_id="local-coder", mode=ModelCapabilityMode.WEAK_LOCAL)

    policy = selector.select(
        ChangeClass.LARGE,
        task_category="feature",
        requested_route=ForgeRoute.MICRO_PATCH,
        model_profile=profile,
        twin_risk="high",
    )

    assert policy.route != ForgeRoute.MICRO_PATCH
    assert policy.route in {ForgeRoute.SLICED_IMPACT, ForgeRoute.BLUEPRINT_SLICE, ForgeRoute.TEST_FIRST}
    assert policy.twin_injection_level >= TwinInjectionLevel.CONSTRAINED_WITH_TESTS
    assert "PatchImpactGate" in policy.required_gates
    assert policy.git_policy.local_branch_required is True
    assert policy.git_policy.remote_publication_requires_approval is True


def test_frontier_assisted_model_gets_lower_injection_and_design_freedom() -> None:
    selector = ExecutionPolicySelector()
    profile = ModelCapabilityProfile(
        model_id="frontier-reviewer",
        mode=ModelCapabilityMode.FRONTIER_ASSISTED,
        capability_scores={
            "impact_analysis": 0.82,
            "contract_preservation": 0.8,
            "test_generation": 0.78,
            "stale_test_judgment": 0.7,
            "flag_reasoning": 0.7,
        },
    )

    policy = selector.select(ChangeClass.SMALL, task_category="design", model_profile=profile, twin_risk="low")

    assert policy.model_capability_mode == ModelCapabilityMode.FRONTIER_ASSISTED
    assert policy.twin_injection_level <= TwinInjectionLevel.CONTRACTS_AND_IMPACT
    assert policy.instruction_style in {InstructionStyle.FREEFORM_DESIGN, InstructionStyle.PATCH_DSL}
    assert "RemotePublishApprovalGate" in policy.required_gates


def test_weak_model_with_flag_weakness_gets_flag_baseline_gate() -> None:
    selector = ExecutionPolicySelector()
    profile = ModelCapabilityProfile(
        model_id="weak-local",
        mode=ModelCapabilityMode.WEAK_LOCAL,
        capability_scores={"flag_reasoning": 0.2},
        known_weaknesses=["flag_reasoning", "stale_test_judgment"],
    )

    policy = selector.select(ChangeClass.MEDIUM, task_category="feature", model_profile=profile)

    assert policy.twin_injection_level >= TwinInjectionLevel.CONSTRAINED_WITH_TESTS
    assert "FeatureFlagBaseline" in policy.required_gates
    assert "TwinProof" in policy.required_twin_modules


def test_twin_brief_compiles_project_intelligence_generation_context() -> None:
    package = GenerationContextPackage(
        project_id="p1",
        workspace_id="w1",
        plan_pool_id="pool1",
        plan_item_id="item1",
        actual_twin_revision_id="twin1",
        blueprint_revision_id="bp1",
        target_files=[
            SourceFileContext(
                path="agent/example.py",
                ref="file://agent/example.py",
                excerpts=[SourceExcerpt(ref="py://agent.example.f", path="agent/example.py", start_line=1, end_line=3)],
            )
        ],
        actual_symbols=[SymbolSummary(ref="py://agent.example.f", name="f", kind="function")],
        required_interfaces=[InterfaceSummary(ref="api://example.create", name="create")],
        preserve_behaviors=["behavior://existing"],
        prohibited_divergences=["contract://api.response"],
        verification_requirements=[
            VerificationRequirement(requirement_id="test://example", description="prove example behavior")
        ],
        context_manifest=ContextManifest(manifest_id="m1", project_id="p1", workspace_id="w1", phase="generation"),
    )

    brief = compile_generation_twin_brief(package, goal="add example", mode="feature_genesis")

    assert brief.goal == "add example"
    assert brief.mode == "feature_genesis"
    assert brief.actual_twin_revision_id == "twin1"
    assert "file://agent/example.py" in brief.allowed_refs
    assert "api://example.create" in brief.required_interfaces
    assert "py://agent.example.f" in brief.impacted_refs
    assert "test://example" in brief.required_tests
    assert "contract://api.response" in brief.contracts_to_preserve
    assert any(c.constraint_id == "safe_apply_required" for c in brief.hard_constraints)


def test_git_steward_local_and_remote_authority_boundaries() -> None:
    assert classify_git_operation("init").allowed_without_approval is True
    assert classify_git_operation("commit").allowed_without_approval is True
    assert classify_git_operation("fetch").allowed_without_approval is True
    assert classify_git_operation("pull").allowed_without_approval is True

    push = classify_git_operation("push")
    assert push.operation_class == GitOperationClass.REMOTE_PUBLICATION
    assert push.approval_required is True

    local_outside_scope = classify_git_operation("commit", atlas_owned_scope=False)
    assert local_outside_scope.approval_required is True


def test_git_steward_default_excludes_sensitive_and_large_artifacts() -> None:
    assert ".env" in DEFAULT_EXCLUDE_PATTERNS
    assert "*.gguf" in DEFAULT_EXCLUDE_PATTERNS
    assert "*.safetensors" in DEFAULT_EXCLUDE_PATTERNS
    assert "ca_data/" in DEFAULT_EXCLUDE_PATTERNS
