"""Atlas Twin Control Plane integration layer.

This package contains the contracts and pure policy helpers that connect Project
Intelligence, Project Twin, Forge route/model policy, and Git Steward execution
state.  It is intentionally dependency-light so it can be used by planning,
generation, verification, and future rollout adapters without becoming an
execution authority.
"""

from agent.twin_control_plane.contracts import (
    ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION,
    ExecutionPolicy,
    GitPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinInjectionLevel,
)
from agent.twin_control_plane.anti_pattern_memory import (
    AntiPatternEntry,
    AntiPatternMemory,
    AntiPatternSource,
    GuardrailHint,
    GuardrailStrength,
    guardrail_hints,
    record_anti_pattern,
    record_from_proof_ledger,
    record_from_repair_compass,
)
from agent.twin_control_plane.assumption_breaker import (
    AssumptionBreakerBrief,
    AssumptionBreakerCase,
    generate_assumption_breaker_briefs,
)
from agent.twin_control_plane.blast_map import BlastMap, BlastMapEntry, build_blast_map
from agent.twin_control_plane.contract_sentinel import (
    ContractFinding,
    ContractSentinelReport,
    evaluate_contracts,
)
from agent.twin_control_plane.genesis import (
    GenesisClassification,
    GenesisKind,
    GenesisRun,
    adapt_greenfield_session,
    classify_genesis,
    safe_apply_required_for_slice,
)
from agent.twin_control_plane.instruction_compiler import CompiledInstruction, compile_model_instruction
from agent.twin_control_plane.integration_impact_gate import (
    IntegrationImpactReport,
    IntegrationPoint,
    assess_integration_impact,
)
from agent.twin_control_plane.interface_first_generator import (
    InterfaceFirstPlan,
    InterfaceFirstSection,
    InterfaceSectionKind,
    apply_interface_first_plan,
    generate_interface_first_plan,
)
from agent.twin_control_plane.no_data_bootstrap_gate import (
    BootstrapCondition,
    BootstrapRequirement,
    NoDataBootstrapAssessment,
    evaluate_no_data_bootstrap,
)
from agent.twin_control_plane.patch_impact_gate import (
    PatchGateDecision,
    PatchImpactReport,
    VerificationEvidence,
    evaluate_patch_impact,
)
from agent.twin_control_plane.proof_ledger import (
    ProofLedger,
    ProofLedgerEntry,
    append_proof_entry,
    create_proof_ledger_entry,
)
from agent.twin_control_plane.repair_compass import (
    RepairCategory,
    RepairCompassReport,
    RepairInstruction,
    build_repair_compass,
)
from agent.twin_control_plane.schema_guardian import (
    SchemaCompatibility,
    SchemaField,
    SchemaFinding,
    SchemaGuardianReport,
    SchemaSnapshot,
    SchemaSurface,
    compare_schema_snapshots,
)
from agent.twin_control_plane.state_mirror import (
    StateMirrorFinding,
    StateMirrorReport,
    StateObservation,
    StateSurface,
    compare_state_mirror,
)
from agent.twin_control_plane.twinproof import (
    ProofGap,
    TestClassification,
    TestInventoryItem,
    TwinProofReport,
    build_twinproof,
)
from agent.twin_control_plane.shadow_integration import (
    TwinShadowMode,
    TwinShadowOrchestrator,
    TwinShadowReport,
    TwinShadowStore,
)
from agent.twin_control_plane.real_llm_eval import (
    AdversarialPrompt,
    ModelChatResponse,
    RealLLMCaseResult,
    RealLLMEvaluationReport,
    build_local_model_chat,
    default_adversarial_prompts,
    run_real_llm_evaluation,
)
from agent.twin_control_plane.active_integration import (
    ActiveIntegrationOrchestrator,
    ActivePipelineResult,
    ApplyOutcome,
    AttemptRecord,
    PipelineHooks,
    PipelineMode,
    PipelineStatus,
    ProposalDraft,
)
from agent.twin_control_plane.acceptance_harness import (
    LocalAcceptanceHooks,
    extract_code_block,
)

__all__ = [
    "ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION",
    "AntiPatternEntry",
    "AntiPatternMemory",
    "AntiPatternSource",
    "AssumptionBreakerBrief",
    "AssumptionBreakerCase",
    "BlastMap",
    "BlastMapEntry",
    "BootstrapCondition",
    "BootstrapRequirement",
    "CompiledInstruction",
    "ContractFinding",
    "ContractSentinelReport",
    "ExecutionPolicy",
    "GenesisClassification",
    "GenesisKind",
    "GenesisRun",
    "GitPolicy",
    "GuardrailHint",
    "GuardrailStrength",
    "InstructionStyle",
    "IntegrationImpactReport",
    "IntegrationPoint",
    "InterfaceFirstPlan",
    "InterfaceFirstSection",
    "InterfaceSectionKind",
    "ModelCapabilityMode",
    "NoDataBootstrapAssessment",
    "PatchGateDecision",
    "PatchImpactReport",
    "ProofLedger",
    "ProofLedgerEntry",
    "ProofGap",
    "RepairCategory",
    "RepairCompassReport",
    "RepairInstruction",
    "SchemaCompatibility",
    "SchemaField",
    "SchemaFinding",
    "SchemaGuardianReport",
    "SchemaSnapshot",
    "SchemaSurface",
    "StateMirrorFinding",
    "StateMirrorReport",
    "StateObservation",
    "StateSurface",
    "TestClassification",
    "TestInventoryItem",
    "TwinBrief",
    "TwinConstraint",
    "TwinInjectionLevel",
    "TwinProofReport",
    "TwinShadowMode",
    "TwinShadowOrchestrator",
    "TwinShadowReport",
    "TwinShadowStore",
    "AdversarialPrompt",
    "ModelChatResponse",
    "RealLLMCaseResult",
    "RealLLMEvaluationReport",
    "build_local_model_chat",
    "default_adversarial_prompts",
    "run_real_llm_evaluation",
    "ActiveIntegrationOrchestrator",
    "ActivePipelineResult",
    "ApplyOutcome",
    "AttemptRecord",
    "PipelineHooks",
    "PipelineMode",
    "PipelineStatus",
    "ProposalDraft",
    "LocalAcceptanceHooks",
    "extract_code_block",
    "VerificationEvidence",
    "adapt_greenfield_session",
    "apply_interface_first_plan",
    "assess_integration_impact",
    "build_blast_map",
    "build_repair_compass",
    "build_twinproof",
    "classify_genesis",
    "compile_model_instruction",
    "compare_schema_snapshots",
    "compare_state_mirror",
    "guardrail_hints",
    "append_proof_entry",
    "create_proof_ledger_entry",
    "evaluate_no_data_bootstrap",
    "evaluate_patch_impact",
    "evaluate_contracts",
    "generate_assumption_breaker_briefs",
    "generate_interface_first_plan",
    "record_anti_pattern",
    "record_from_proof_ledger",
    "record_from_repair_compass",
    "safe_apply_required_for_slice",
]
