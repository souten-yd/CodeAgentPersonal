"""Model Forge core (PFG-5+).

Schema and taxonomy foundation for provider/model/route evaluation and selection.
Off by default: this package contains data shapes and taxonomy helpers only and must
not perform provider execution or change production routing on import.
"""
from __future__ import annotations

from agent.model_forge.arena_runner import (
    ArenaCandidateSpec,
    ArenaRunner,
    ArenaRunRecord,
)
from agent.model_forge.benchmark_presets import (
    get_preset,
    load_presets,
    preset_listing,
    validate_preset,
)
from agent.model_forge.candidate_evaluator import (
    VERDICT_ELIGIBLE,
    VERDICT_REJECTED,
    CandidateEvaluation,
    CandidateEvaluationInput,
    CandidateEvaluator,
    EvaluatorOutcome,
    EvaluatorResult,
)
from agent.model_forge.profile_store import (
    ProfileObservation,
    ProfileStore,
    profile_key,
)
from agent.model_forge.stage_matrix import (
    StageCandidate,
    StageMatrix,
    StagePolicyEntry,
    StageSelection,
    StageSelector,
    stage_dimension,
)
from agent.model_forge.provider_base import (
    ForgeProvider,
    HealthState,
    ProviderDisabledError,
    ProviderError,
    ProviderHealth,
    ProviderUnavailableError,
    redact_for_log,
)
from agent.model_forge.provider_policy import (
    ProviderPolicyDecision,
    privacy_allowed_for_provider,
    provider_availability_matrix,
    resolve_provider_policy,
    select_eligible_provider_ids,
    source_class_allowed,
)
from agent.model_forge.provider_registry import ProviderRegistry
from agent.model_forge.providers.legacy_atlas import (
    LEGACY_ATLAS_PROVIDER_ID,
    LegacyAtlasProvider,
    legacy_atlas_descriptor,
)
from agent.model_forge.providers.local_openai_compatible import (
    LOCAL_OPENAI_PROVIDER_ID,
    LocalOpenAICompatibleProvider,
    local_openai_compatible_descriptor,
)
from agent.model_forge.providers.openrouter_config import (
    OPENROUTER_PROVIDER_ID,
    OpenRouterConfig,
    OpenRouterGate,
    build_openrouter_headers,
    check_openrouter_allowed,
    live_smoke_enabled,
    openrouter_api_key,
    openrouter_credentials_available,
    openrouter_descriptor,
    redact_openrouter_headers,
)
from agent.model_forge.providers.openrouter_client import OpenRouterProvider
from agent.model_forge.providers.openrouter_catalog import (
    OpenRouterCatalog,
    OpenRouterCatalogResult,
)
from agent.model_forge.route_taxonomy import ForgeRoute, all_routes, is_valid_route
from agent.model_forge.schema import (
    FORGE_SCHEMA_VERSION,
    AdoptionState,
    ArenaCandidate,
    BenchmarkPreset,
    CandidateScore,
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeUsage,
    ModelDescriptor,
    ModelProfile,
    ProviderDescriptor,
    ProviderSupport,
    SourceClass,
)
from agent.model_forge.source_policy import (
    PrivacyMode,
    SourceMode,
    allows_external_providers,
    default_privacy_for_stage,
    is_privacy_raise,
    is_valid_privacy_mode,
    is_valid_source_mode,
    privacy_rank,
)
from agent.model_forge.stage_taxonomy import (
    ForgeStage,
    StageMode,
    all_stages,
    changes_production_routing,
    default_stage_mode,
    is_valid_stage,
    is_valid_stage_mode,
)

__all__ = [
    "FORGE_SCHEMA_VERSION",
    "AdoptionState",
    "ArenaCandidate",
    "BenchmarkPreset",
    "CandidateScore",
    "ForgeExecutionRequest",
    "ForgeExecutionResult",
    "ForgeUsage",
    "ModelDescriptor",
    "ModelProfile",
    "ProviderDescriptor",
    "ProviderSupport",
    "SourceClass",
    "PrivacyMode",
    "SourceMode",
    "allows_external_providers",
    "default_privacy_for_stage",
    "is_privacy_raise",
    "is_valid_privacy_mode",
    "is_valid_source_mode",
    "privacy_rank",
    "ForgeStage",
    "StageMode",
    "all_stages",
    "changes_production_routing",
    "default_stage_mode",
    "is_valid_stage",
    "is_valid_stage_mode",
    "ForgeRoute",
    "all_routes",
    "is_valid_route",
    "ForgeProvider",
    "HealthState",
    "ProviderHealth",
    "ProviderError",
    "ProviderDisabledError",
    "ProviderUnavailableError",
    "redact_for_log",
    "ProviderRegistry",
    "LegacyAtlasProvider",
    "legacy_atlas_descriptor",
    "LEGACY_ATLAS_PROVIDER_ID",
    "LocalOpenAICompatibleProvider",
    "local_openai_compatible_descriptor",
    "LOCAL_OPENAI_PROVIDER_ID",
    "OPENROUTER_PROVIDER_ID",
    "OpenRouterConfig",
    "OpenRouterGate",
    "openrouter_descriptor",
    "openrouter_api_key",
    "openrouter_credentials_available",
    "check_openrouter_allowed",
    "live_smoke_enabled",
    "build_openrouter_headers",
    "redact_openrouter_headers",
    "OpenRouterProvider",
    "OpenRouterCatalog",
    "OpenRouterCatalogResult",
    "ProviderPolicyDecision",
    "source_class_allowed",
    "privacy_allowed_for_provider",
    "resolve_provider_policy",
    "provider_availability_matrix",
    "select_eligible_provider_ids",
    "load_presets",
    "get_preset",
    "preset_listing",
    "validate_preset",
    "ArenaCandidateSpec",
    "ArenaRunRecord",
    "ArenaRunner",
    "EvaluatorOutcome",
    "EvaluatorResult",
    "CandidateEvaluationInput",
    "CandidateEvaluation",
    "CandidateEvaluator",
    "VERDICT_ELIGIBLE",
    "VERDICT_REJECTED",
    "ProfileStore",
    "ProfileObservation",
    "profile_key",
    "StageCandidate",
    "StagePolicyEntry",
    "StageSelection",
    "StageMatrix",
    "StageSelector",
    "stage_dimension",
]
