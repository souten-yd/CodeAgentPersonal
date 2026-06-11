"""Model Forge core (PFG-5+).

Schema and taxonomy foundation for provider/model/route evaluation and selection.
Off by default: this package contains data shapes and taxonomy helpers only and must
not perform provider execution or change production routing on import.
"""
from __future__ import annotations

from agent.model_forge.provider_base import (
    ForgeProvider,
    HealthState,
    ProviderDisabledError,
    ProviderError,
    ProviderHealth,
    ProviderUnavailableError,
    redact_for_log,
)
from agent.model_forge.provider_registry import ProviderRegistry
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
]
