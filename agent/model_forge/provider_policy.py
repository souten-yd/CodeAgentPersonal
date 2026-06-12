"""Provider health + Source Mode / privacy selection policy (PFG-12).

Centralizes the constraints that decide whether a provider may be selected for a
request: provider health, the request's Source Mode (local vs external), and the
privacy mode (what may be sent to an external provider). Produces API-ready,
evidence-style decisions so the UI can show, and the run record can store, exactly why
a provider was or was not selectable. An external provider can never be selected when
the policy forbids it (Local Only, or a privacy mode the provider cannot honour).
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.model_forge.provider_base import HealthState
from agent.model_forge.provider_registry import ProviderRegistry
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel, PrivacyMode, ProviderDescriptor, SourceClass
from agent.model_forge.source_policy import SourceMode

_LOCAL_CLASSES = frozenset({SourceClass.LOCAL, SourceClass.SELF_HOSTED})


class ProviderPolicyDecision(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    provider_id: str
    source_class: SourceClass
    health_state: HealthState
    source_mode: SourceMode
    privacy_mode: PrivacyMode
    source_allowed: bool
    privacy_allowed: bool
    healthy: bool
    selectable: bool
    reasons: list[str] = []
    decided_at: str = ""


def source_class_allowed(source_mode: SourceMode | str, source_class: SourceClass | str) -> bool:
    """Whether a provider of this source class may be used under this Source Mode."""
    mode = SourceMode(source_mode)
    klass = SourceClass(source_class)
    if mode == SourceMode.LOCAL_ONLY:
        return klass in _LOCAL_CLASSES
    if mode == SourceMode.FRONTIER_ONLY:
        return klass == SourceClass.EXTERNAL_CLOUD
    # local_preferred / hybrid / frontier_preferred allow both local and external.
    return True


def privacy_allowed_for_provider(descriptor: ProviderDescriptor, privacy_mode: PrivacyMode | str) -> bool:
    """Local/self-hosted providers keep data on-prem, so privacy mode never blocks them.
    External providers must declare support for the requested privacy mode."""
    if descriptor.source_class in _LOCAL_CLASSES:
        return True
    return PrivacyMode(privacy_mode) in set(descriptor.privacy_capabilities)


def resolve_provider_policy(
    registry: ProviderRegistry,
    provider_id: str,
    *,
    source_mode: SourceMode | str,
    privacy_mode: PrivacyMode | str,
) -> ProviderPolicyDecision:
    provider = registry.get(provider_id)
    health = registry.health(provider_id)
    descriptor = provider.descriptor if provider is not None else None
    source_class = descriptor.source_class if descriptor is not None else SourceClass.EXTERNAL_CLOUD

    healthy = health.state == HealthState.READY
    src_allowed = source_class_allowed(source_mode, source_class)
    priv_allowed = privacy_allowed_for_provider(descriptor, privacy_mode) if descriptor is not None else False

    reasons: list[str] = []
    if provider is None:
        reasons.append("provider_not_registered")
    if not healthy:
        reasons.append(f"health_{health.state.value}")
    if not src_allowed:
        reasons.append("source_mode_forbids_provider")
    if not priv_allowed:
        reasons.append("privacy_mode_unsupported")

    return ProviderPolicyDecision(
        provider_id=provider_id,
        source_class=source_class,
        health_state=health.state,
        source_mode=SourceMode(source_mode),
        privacy_mode=PrivacyMode(privacy_mode),
        source_allowed=src_allowed,
        privacy_allowed=priv_allowed,
        healthy=healthy,
        selectable=bool(provider is not None and healthy and src_allowed and priv_allowed),
        reasons=reasons,
        decided_at=datetime.now(timezone.utc).isoformat(),
    )


def provider_availability_matrix(
    registry: ProviderRegistry,
    *,
    source_mode: SourceMode | str,
    privacy_mode: PrivacyMode | str,
) -> list[ProviderPolicyDecision]:
    """API-ready, per-provider selectability decisions for the Forge UI."""
    return [
        resolve_provider_policy(registry, descriptor.provider_id, source_mode=source_mode, privacy_mode=privacy_mode)
        for descriptor in registry.descriptors()
    ]


def select_eligible_provider_ids(
    registry: ProviderRegistry,
    *,
    source_mode: SourceMode | str,
    privacy_mode: PrivacyMode | str,
) -> list[str]:
    return [d.provider_id for d in provider_availability_matrix(registry, source_mode=source_mode, privacy_mode=privacy_mode) if d.selectable]
